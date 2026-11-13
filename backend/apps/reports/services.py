"""Report requests, the worker that builds them, template management and retention.

A request is checked when it is made and again in the worker. The file is built from the requester's own finding
scope. Every build writes a ``report.generated`` audit event with the filters and the checksum of the file.
"""

import hashlib
import io
import logging
import re
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from PIL import Image
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from apps.accounts.models import User
from apps.audit import service as audit
from apps.core.errors import Conflict
from apps.core.storage import get_storage
from apps.engagements.models import Engagement
from apps.rbac.authz import has_engagement_perm

from . import builder, render
from .models import REQUIRED_SECTIONS, SECTION_KEYS, ReportJob, ReportTemplate

log = logging.getLogger(__name__)

STALE = timedelta(minutes=15)
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
LOGO_MAX_BYTES = 1024 * 1024
LOGO_MAX_EDGE = 2000
LOGO_FORMATS = {"PNG", "JPEG"}


class Gone(APIException):
    status_code = 410
    default_detail = "This report file has expired. Create a new one."
    default_code = "gone"


def _enqueue(job_id) -> None:
    from . import tasks

    tasks.build_report.apply_async((str(job_id),), queue="reports")


def _deny(request, entity, engagement, action: str, reason: str):
    audit.record(
        action, request=request, entity=entity, engagement=engagement, outcome="denied", metadata={"reason": reason}
    )
    raise PermissionDenied(reason)


def _needed(fmt: str) -> tuple[str, ...]:
    return ("reports.generate_pdf",) if fmt == "pdf" else ("reports.view", "exports.csv")


# requests


def create_job(request, actor, eng: Engagement, data: dict) -> ReportJob:
    fmt, audience = data["format"], data["audience"]
    for code in _needed(fmt):
        if not has_engagement_perm(actor, eng.pk, code):
            _deny(request, eng, eng, "report.request_denied", "You do not have permission to create this report.")
    if audience == "internal" and not has_engagement_perm(actor, eng.pk, "finding_notes.technical"):
        _deny(request, eng, eng, "report.request_denied", "Internal reports need access to technical details.")
    if eng.is_archived:
        raise Conflict("This engagement is archived. Unarchive it to create a report.")
    template = None
    if fmt == "pdf":
        template = data.get("template") or ReportTemplate.objects.filter(is_default=True).first()
    if ReportJob.objects.filter(
        engagement=eng, status__in=ReportJob.WORKING, updated_at__gte=timezone.now() - STALE
    ).exists():
        raise Conflict("A report for this engagement is still being built. Wait for it to finish.")
    with transaction.atomic():
        job = ReportJob.objects.create(
            engagement=eng,
            requested_by=actor,
            template=template,
            template_name=template.name if template else "",
            format=fmt,
            audience=audience,
            title=data.get("title", ""),
            version_label=data.get("version_label") or "1.0",
            classification=data.get("classification") or "Confidential",
            filters=builder.normalise_filters(data.get("filters")),
            started_at=timezone.now(),
        )
        audit.record(
            "report.requested", request=request, entity=job, engagement=eng,
            metadata={"format": fmt, "audience": audience, "filters": job.filters},
        )  # fmt: skip
    transaction.on_commit(lambda: _enqueue(job.pk))
    return job


def build_job(job_id) -> None:
    """Worker: collect, render, store. Safe to run twice (a finished or failed job is left alone)."""
    with transaction.atomic():
        job = (
            ReportJob.objects.select_for_update(of=("self",))
            .select_related("engagement", "template")
            .filter(pk=job_id)
            .first()
        )
        if job is None or job.status != "queued":
            return
        job.status = "rendering"
        job.started_at = timezone.now()
        job.save(update_fields=["status", "started_at", "updated_at"])
    try:
        actor = User.objects.select_related("role").get(pk=job.requested_by_id)
        if not actor.is_active:
            raise builder.ReportRefused("The requesting account is deactivated.")
        for code in _needed(job.format):
            if not has_engagement_perm(actor, job.engagement_id, code):
                raise builder.ReportRefused("The requester no longer has permission to create this report.")
        ctx = builder.collect(job, actor)
        ctx["custom_logo"] = _logo_uri(job.template)
        if job.format == "pdf":
            data, pages = render.render_pdf(ctx, job.template)
            suffix, count = "pdf", pages
        else:
            data, count = render.render_csv(ctx)
            suffix, pages = "csv", None
        digest = hashlib.sha256(data).hexdigest()
        key = get_storage().save(data)
        name = (
            f"{job.engagement.ref}-{'internal' if ctx['internal'] else 'report'}-{timezone.localdate():%Y%m%d}.{suffix}"
        )
        with transaction.atomic():
            ReportJob.objects.filter(pk=job.pk).update(
                status="done", storage_key=key, file_name=name, size=len(data), sha256=digest, page_count=pages,
                finding_count=len(ctx["findings"]), finished_at=timezone.now(), error="",
                expires_at=timezone.now() + timedelta(days=settings.REPORT_RETENTION_DAYS),
                updated_at=timezone.now(),
            )  # fmt: skip
            audit.record(
                "report.generated", actor=actor, entity=job, engagement=job.engagement,
                metadata={
                    "format": job.format,
                    "audience": job.audience,
                    "filters": job.filters,
                    "findings": len(ctx["findings"]),
                    "pages": pages, "size": len(data), "sha256": digest, "rows": count if job.format == "csv" else None,
                },
            )  # fmt: skip
    except builder.ReportRefused as exc:
        _fail(job, str(exc))
    except Exception:
        log.exception("report %s failed", job_id)
        _fail(job, "The report could not be built. Ask an administrator to check the worker log.")


def _fail(job: ReportJob, message: str) -> None:
    with transaction.atomic():
        ReportJob.objects.filter(pk=job.pk).update(
            status="failed", error=message[:300], finished_at=timezone.now(), updated_at=timezone.now()
        )
        audit.record(
            "report.failed", actor=job.requested_by, entity=job, engagement=job.engagement, outcome="failure",
            metadata={"reason": message[:300], "format": job.format},
        )  # fmt: skip


def read_file(request, actor, job: ReportJob) -> bytes:
    if not job.file_available:
        raise Gone()
    audit.record(
        "report.downloaded", request=request, entity=job, engagement=job.engagement,
        metadata={"sha256": job.sha256, "format": job.format},
    )  # fmt: skip
    return get_storage().read(job.storage_key)


def cleanup() -> dict:
    """Daily: fail jobs stuck in the worker, delete files past their expiry. Rows and audit stay."""
    now = timezone.now()
    stuck = ReportJob.objects.filter(status__in=ReportJob.WORKING, updated_at__lt=now - STALE)
    failed = 0
    for job in stuck.select_related("engagement", "requested_by"):
        _fail(job, "The report did not finish in time.")
        failed += 1
    purged = 0
    expired = ReportJob.objects.filter(expires_at__lt=now, file_purged_at__isnull=True).exclude(storage_key="")
    for job in expired:
        get_storage().delete(job.storage_key)
        ReportJob.objects.filter(pk=job.pk).update(file_purged_at=now)
        purged += 1
    return {"failed": failed, "purged": purged}


# templates


def _clean_sections(sections) -> list[str]:
    if not isinstance(sections, list) or not all(isinstance(s, str) for s in sections):
        raise ValidationError({"sections": ["Send a list of section names."]})
    if len(set(sections)) != len(sections) or any(s not in SECTION_KEYS for s in sections):
        raise ValidationError({"sections": ["Use each known section at most once."]})
    for needed in REQUIRED_SECTIONS:
        if needed not in sections:
            raise ValidationError({"sections": [f"The {needed} section cannot be removed."]})
    return sections


def save_template(request, actor, template: ReportTemplate | None, data: dict) -> ReportTemplate:
    fields = {}
    if "name" in data:
        fields["name"] = data["name"].strip()
    if "sections" in data:
        fields["sections"] = _clean_sections(data["sections"])
    if "accent" in data:
        if not HEX.match(data["accent"]):
            raise ValidationError({"accent": ["Use a colour like #e5383b."]})
        fields["accent"] = data["accent"].lower()
    for key in ("font", "footer_text"):
        if key in data:
            fields[key] = data[key]
    with transaction.atomic():
        try:
            if template is None:
                template = ReportTemplate.objects.create(created_by=actor, **fields)
                audit.record("report_template.created", request=request, entity=template, metadata=fields)
            else:
                locked = ReportTemplate.objects.select_for_update().get(pk=template.pk)
                if data.get("version") is not None and int(data["version"]) != locked.version:
                    raise Conflict("This template was changed by someone else. Reload and try again.")
                before = {k: getattr(locked, k) for k in fields}
                for k, v in fields.items():
                    setattr(locked, k, v)
                locked.version += 1
                locked.save()
                template = locked
                audit.record(
                    "report_template.updated", request=request, entity=template,
                    changes={k: [before[k], fields[k]] for k in fields if before[k] != fields[k]},
                )  # fmt: skip
            if data.get("is_default"):
                ReportTemplate.objects.exclude(pk=template.pk).filter(is_default=True).update(is_default=False)
                ReportTemplate.objects.filter(pk=template.pk).update(is_default=True)
                template.is_default = True
        except IntegrityError as exc:
            raise ValidationError({"name": ["A template with this name already exists."]}) from exc
    return template


def delete_template(request, template: ReportTemplate) -> None:
    if template.is_default:
        raise Conflict("The default template cannot be deleted. Make another template the default first.")
    with transaction.atomic():
        key = template.logo_key
        audit.record("report_template.deleted", request=request, entity=template)
        template.delete()
    if key:
        get_storage().delete(key)


def set_logo(request, template: ReportTemplate, uploaded) -> ReportTemplate:
    if uploaded.size > LOGO_MAX_BYTES:
        raise ValidationError({"logo": ["The logo is larger than 1 MB."]})
    try:
        with Image.open(uploaded) as img:
            if img.format not in LOGO_FORMATS:
                raise ValidationError({"logo": ["Upload a PNG or JPEG logo."]})
            if max(img.size) > LOGO_MAX_EDGE:
                raise ValidationError({"logo": [f"The logo is larger than {LOGO_MAX_EDGE} pixels on one side."]})
            frame = img.convert("RGBA")
            out = io.BytesIO()
            frame.save(out, "PNG", optimize=True)  # re-encoded: no metadata, no embedded payload
    except (OSError, Image.DecompressionBombError, ValueError) as exc:
        raise ValidationError({"logo": ["This file is not a usable image."]}) from exc
    storage = get_storage()
    with transaction.atomic():
        old = template.logo_key
        template.logo_key = storage.save(out.getvalue())
        template.version += 1
        template.save(update_fields=["logo_key", "version", "updated_at"])
        audit.record("report_template.logo_set", request=request, entity=template)
    if old:
        storage.delete(old)
    return template


def clear_logo(request, template: ReportTemplate) -> ReportTemplate:
    if not template.logo_key:
        return template
    old = template.logo_key
    with transaction.atomic():
        template.logo_key = ""
        template.version += 1
        template.save(update_fields=["logo_key", "version", "updated_at"])
        audit.record("report_template.logo_removed", request=request, entity=template)
    get_storage().delete(old)
    return template


def _logo_uri(template: ReportTemplate | None) -> str:
    if template is None or not template.logo_key:
        return ""
    import base64

    try:
        return "data:image/png;base64," + base64.b64encode(get_storage().read(template.logo_key)).decode()
    except Exception:  # noqa: BLE001 - a missing logo file falls back to the RedShadow wordmark
        return ""
