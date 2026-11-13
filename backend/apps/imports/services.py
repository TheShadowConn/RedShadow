"""CSV import: upload, map, validate, commit. Every step checks the caller's rights on the job's engagement.

Findings an import creates are always drafts. Heavy work (reading, checking, inserting) runs in the worker
on the ``imports`` queue; the functions ending in ``_job`` and ``run_import`` are what the tasks call.
"""

import datetime
import hashlib
import logging
import uuid
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.audit import service as audit
from apps.core.errors import Conflict
from apps.core.storage import get_storage
from apps.engagements.models import Engagement, EngagementAsset
from apps.findings import cvss
from apps.findings.models import Finding
from apps.findings.selectors import scope_findings
from apps.findings.services import reserve_refs
from apps.rbac.authz import has_engagement_perm

from . import parsing
from .mapping import clean_mapping
from .models import ImportJob, ImportMapping, ImportRow
from .validation import RowValidator

log = logging.getLogger(__name__)

CHUNK = 500
STALE = timedelta(minutes=30)
FILE_RETENTION = timedelta(days=30)


class ImportAbort(Exception):
    """Raised inside the commit transaction to roll everything back with a message for the user."""


def _enqueue(task_name: str, job_id) -> None:
    from . import tasks

    getattr(tasks, task_name).apply_async((str(job_id),), queue="imports")


def _deny(request, job_or_eng, action: str, reason: str, engagement=None):
    audit.record(
        action,
        request=request,
        entity=job_or_eng,
        engagement=engagement or getattr(job_or_eng, "engagement", job_or_eng),
        outcome="denied",
        metadata={"reason": reason},
    )
    raise PermissionDenied(reason)


def _require_create(request, actor, job: ImportJob, action: str) -> None:
    if not has_engagement_perm(actor, job.engagement_id, "imports.create"):
        _deny(request, job, action, "You do not have permission to import into this engagement.")


def _busy(engagement_id, exclude=None) -> bool:
    qs = ImportJob.objects.filter(
        engagement_id=engagement_id, status__in=ImportJob.WORKING, updated_at__gte=timezone.now() - STALE
    )
    return qs.exclude(pk=exclude).exists() if exclude else qs.exists()


# upload


def create_upload(request, actor, eng: Engagement, uploaded) -> ImportJob:
    if not has_engagement_perm(actor, eng.pk, "imports.create"):
        _deny(request, eng, "import.upload_denied", "You do not have permission to import into this engagement.", eng)
    if eng.is_archived:
        raise Conflict("This engagement is archived. Unarchive it to import.")
    name = (uploaded.name or "").rsplit("/", 1)[-1][:255]
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in parsing.EXTENSIONS:
        raise ValidationError({"file": ["Upload a .csv file."]})
    if uploaded.size > parsing.MAX_BYTES:
        raise ValidationError({"file": [f"The file is larger than {parsing.MAX_BYTES // (1024 * 1024)} MB."]})
    data = uploaded.read()
    if not data:
        raise ValidationError({"file": ["The file is empty."]})
    if _busy(eng.pk):
        raise Conflict("Another import into this engagement is still running. Wait for it to finish.")
    digest = hashlib.sha256(data).hexdigest()
    key = get_storage().save(data)
    with transaction.atomic():
        job = ImportJob.objects.create(
            engagement=eng,
            uploaded_by=actor,
            original_name=name,
            storage_key=key,
            file_sha256=digest,
            file_size=len(data),
            started_at=timezone.now(),
        )
        audit.record(
            "import.uploaded",
            request=request,
            entity=job,
            engagement=eng,
            metadata={"file": name, "size": len(data), "sha256": digest},
        )
    _enqueue("parse_job", job.pk)
    return job


def parse_job(job_id) -> None:
    """Worker: read the file, store its rows, and leave the job ready for mapping. Safe to run twice."""
    with transaction.atomic():
        job = ImportJob.objects.select_for_update().filter(pk=job_id).first()
        if job is None or job.status != "uploaded":
            return
        job.status = "parsing"
        job.save(update_fields=["status", "updated_at"])
    try:
        parsed = parsing.parse(get_storage().read(job.storage_key))
        sample, total, batch = [], 0, []
        with transaction.atomic():
            for line, cells in parsed.rows:
                total += 1
                if len(sample) < 5:
                    sample.append(cells[: len(parsed.headers)])
                batch.append(ImportRow(job=job, row_number=line, raw=cells))
                if len(batch) >= 1000:
                    ImportRow.objects.bulk_create(batch)
                    batch = []
            if batch:
                ImportRow.objects.bulk_create(batch)
        if total == 0:
            raise parsing.ParseError("The file has column names but no rows.")
        ImportJob.objects.filter(pk=job.pk).update(
            status="parsed",
            encoding=parsed.encoding,
            delimiter=parsed.delimiter,
            headers=parsed.headers,
            sample=sample,
            counts={"total": total},
            updated_at=timezone.now(),
        )
    except parsing.ParseError as exc:
        _fail(job, str(exc)[:300])
    except Exception:  # noqa: BLE001 - never leave a job stuck in "parsing"
        log.exception("import %s: parsing crashed", job_id)
        _fail(job, "The file could not be read.")


def _fail(job: ImportJob, message: str) -> None:
    ImportJob.objects.filter(pk=job.pk).update(
        status="failed", error=message, finished_at=timezone.now(), updated_at=timezone.now()
    )
    audit.record(
        "import.failed",
        actor=job.uploaded_by,
        entity=job,
        engagement=job.engagement,
        outcome="failure",
        metadata={"reason": message},
    )


# mapping and validation


def set_mapping(request, actor, job: ImportJob, column_map: dict, value_map: dict, save_as: str = "") -> ImportJob:
    _require_create(request, actor, job, "import.mapping_denied")
    with transaction.atomic():
        job = ImportJob.objects.select_for_update().select_related("engagement").get(pk=job.pk)
        if job.status not in ("parsed", "previewed"):
            raise Conflict("This import is not waiting for a mapping.")
        if job.engagement.is_archived:
            raise Conflict("This engagement is archived. Unarchive it to import.")
        if _busy(job.engagement_id, exclude=job.pk):
            raise Conflict("Another import into this engagement is still running. Wait for it to finish.")
        cleaned, values = clean_mapping(job.headers, column_map, value_map)
        job.mapping = {"column_map": cleaned, "value_map": values}
        job.status, job.started_at = "validating", timezone.now()
        job.version += 1
        job.save()
        job.rows.update(status="pending", mapped={}, errors=[], duplicate_of_finding=None, duplicate_of_line=None)
        if save_as.strip():
            ImportMapping.objects.update_or_create(
                owner=actor, name=save_as.strip()[:120], defaults={"column_map": cleaned, "value_map": values}
            )
        audit.record(
            "import.mapped",
            request=request,
            entity=job,
            engagement=job.engagement,
            metadata={"columns": sorted(cleaned), "saved_as": save_as.strip() or None},
        )
    _enqueue("validate_job", job.pk)
    return job


def validate_job(job_id) -> None:
    """Worker: check every row, mark duplicates, and leave the job ready to preview."""
    job = ImportJob.objects.select_related("engagement", "uploaded_by").filter(pk=job_id).first()
    if job is None or job.status != "validating":
        return
    try:
        maps = job.mapping
        validator = RowValidator(job.engagement, job.headers, maps["column_map"], maps.get("value_map", {}))
        first_seen: dict[str, tuple[int, int]] = {}  # hash -> (row id, line)
        by_hash: dict[str, list[int]] = {}
        dup_in_file: list[tuple[int, int]] = []  # (row id, line of the first occurrence)
        pending = []

        def flush():
            if pending:
                ImportRow.objects.bulk_update(pending, ["mapped", "errors", "status"])
                pending.clear()

        for row in job.rows.order_by("row_number", "id").iterator(chunk_size=1000):
            mapped, errors = validator.validate(row.raw)
            row.mapped, row.errors = mapped, errors
            row.status = "invalid" if errors else "valid"
            if not errors:
                h = mapped["dedupe_hash"]
                by_hash.setdefault(h, []).append(row.pk)
                if h in first_seen:
                    dup_in_file.append((row.pk, first_seen[h][1]))
                else:
                    first_seen[h] = (row.pk, row.row_number)
            pending.append(row)
            if len(pending) >= 1000:
                flush()
        flush()
        for row_id, line in dup_in_file:
            ImportRow.objects.filter(pk=row_id).update(status="duplicate", duplicate_of_line=line)
        hashes = list(first_seen)
        for i in range(0, len(hashes), 1000):
            existing = {}
            for fid, h in (
                scope_findings(job.uploaded_by)
                .filter(engagement=job.engagement, dedupe_hash__in=hashes[i : i + 1000])
                .order_by("-created_at")
                .values_list("pk", "dedupe_hash")
            ):
                existing[h] = fid
            for h, fid in existing.items():
                ImportRow.objects.filter(pk__in=by_hash[h]).update(status="duplicate", duplicate_of_finding=fid)
        counts = {s: job.rows.filter(status=s).count() for s in ("valid", "invalid", "duplicate")}
        counts["total"] = job.rows.count()
        ImportJob.objects.filter(pk=job.pk, status="validating").update(
            status="previewed", counts=counts, updated_at=timezone.now()
        )
        audit.record("import.validated", actor=job.uploaded_by, entity=job, engagement=job.engagement, metadata=counts)
    except Exception:  # noqa: BLE001
        log.exception("import %s: validation crashed", job_id)
        _fail(job, "The rows could not be checked.")


# commit


def commit(request, actor, job: ImportJob, mode: str, duplicates: str) -> ImportJob:
    _require_create(request, actor, job, "import.commit_denied")
    with transaction.atomic():
        job = ImportJob.objects.select_for_update().select_related("engagement").get(pk=job.pk)
        if job.status != "previewed":
            raise Conflict("This import is not ready to import.")
        if job.engagement.is_archived:
            raise Conflict("This engagement is archived. Unarchive it to import.")
        if _busy(job.engagement_id, exclude=job.pk):
            raise Conflict("Another import into this engagement is still running. Wait for it to finish.")
        c = job.counts
        if mode == "all_or_nothing" and c.get("invalid", 0) > 0:
            raise Conflict(f"{c['invalid']} rows have errors. Fix the file, or choose to import the valid rows only.")
        importable = c.get("valid", 0) + (c.get("duplicate", 0) if duplicates == "import" else 0)
        if importable == 0:
            raise Conflict("There is nothing to import.")
        job.status, job.mode, job.duplicates, job.started_at = "importing", mode, duplicates, timezone.now()
        job.version += 1
        job.save()
        audit.record(
            "import.commit_requested",
            request=request,
            entity=job,
            engagement=job.engagement,
            metadata={"mode": mode, "duplicates": duplicates, "rows": importable},
        )
    _enqueue("run_import", job.pk)
    return job


def run_import(job_id) -> None:
    """Worker: create the drafts in one transaction. Any failure rolls back to zero findings."""
    job = ImportJob.objects.select_related("engagement", "uploaded_by").filter(pk=job_id).first()
    if job is None or job.status != "importing":
        return
    try:
        with transaction.atomic():
            eng = Engagement.objects.select_for_update().get(pk=job.engagement_id)
            if eng.is_archived:
                raise ImportAbort("The engagement was archived before the import ran.")
            scope_assets = set(
                EngagementAsset.objects.filter(engagement=eng, in_scope=True).values_list("asset_id", flat=True)
            )
            want = ["valid"] + (["duplicate"] if job.duplicates == "import" else [])
            rows = job.rows.filter(status__in=want).order_by("row_number", "id")
            imported, lost, first_ref, last_ref = 0, 0, None, None
            batch: list[ImportRow] = []

            def insert(batch_rows):
                nonlocal imported, lost, first_ref, last_ref
                usable = []
                for r in batch_rows:
                    aid = r.mapped.get("asset_id")
                    if aid and uuid.UUID(str(aid)) not in scope_assets:
                        if job.mode == "all_or_nothing":
                            raise ImportAbort(
                                f"Line {r.row_number}: the asset is no longer in scope for this engagement."
                            )
                        r.status, r.errors = (
                            "invalid",
                            [
                                *r.errors,
                                {
                                    "field": "asset",
                                    "code": "unknown_asset",
                                    "message": "The asset is no longer in scope.",
                                },
                            ],
                        )
                        r.save(update_fields=["status", "errors"])
                        lost += 1
                        continue
                    usable.append(r)
                if not usable:
                    return
                refs = reserve_refs(len(usable))
                findings = [_finding(job, eng, r, ref) for r, ref in zip(usable, refs, strict=True)]
                Finding.objects.bulk_create(findings, batch_size=CHUNK)
                for r, f in zip(usable, findings, strict=True):
                    r.status, r.finding_id = "imported", f.pk
                ImportRow.objects.bulk_update(usable, ["status", "finding_id"])
                imported += len(usable)
                first_ref = first_ref or refs[0]
                last_ref = refs[-1]

            for row in rows.iterator(chunk_size=CHUNK):
                batch.append(row)
                if len(batch) >= CHUNK:
                    insert(batch)
                    batch = []
            if batch:
                insert(batch)
            skipped = 0
            if job.duplicates == "skip":
                skipped = job.rows.filter(status="duplicate").update(status="skipped")
            counts = {
                **job.counts,
                "imported": imported,
                "skipped": skipped,
                "invalid": job.rows.filter(status="invalid").count(),
            }
            ImportJob.objects.filter(pk=job.pk).update(
                status="completed", counts=counts, finished_at=timezone.now(), updated_at=timezone.now()
            )
            audit.record(
                "import.committed",
                actor=job.uploaded_by,
                entity=job,
                engagement=eng,
                metadata={
                    "imported": imported,
                    "skipped": skipped,
                    "invalid": counts["invalid"],
                    "mode": job.mode,
                    "first_ref": first_ref,
                    "last_ref": last_ref,
                    "sha256": job.file_sha256,
                    "lost_to_scope_change": lost,
                },
            )
    except ImportAbort as exc:
        _fail(job, f"Nothing was imported. {exc}"[:300])
    except Exception:  # noqa: BLE001
        log.exception("import %s: commit crashed", job_id)
        _fail(job, "Nothing was imported: the import failed and was rolled back.")


def _finding(job: ImportJob, eng: Engagement, row: ImportRow, ref: str) -> Finding:
    m = row.mapped
    extra = {}
    if m.get("cvss_vector"):
        version, score, severity = cvss.score_vector(m["cvss_vector"])
        extra = {"cvss_vector": m["cvss_vector"], "cvss_version": version, "cvss_score": score, "severity": severity}
    return Finding(
        ref=ref,
        engagement=eng,
        reported_by=job.uploaded_by,
        status="draft",
        source="import",
        import_job=job,
        title=m["title"],
        severity=extra.get("severity") or m["severity"],
        description=m.get("description", ""),
        recommendation=m.get("recommendation", ""),
        technical_details=m.get("technical_details", ""),
        poc=m.get("poc", ""),
        endpoint=m.get("endpoint", ""),
        asset_id=m.get("asset_id"),
        cwe_id=m.get("cwe_id"),
        references=m.get("references", []),
        discovered_at=datetime.date.fromisoformat(m["discovered_at"])
        if m.get("discovered_at")
        else timezone.localdate(),
        dedupe_hash=m["dedupe_hash"],
        **{k: v for k, v in extra.items() if k != "severity"},
    )


# cancel and housekeeping


def cancel(request, actor, job: ImportJob) -> ImportJob:
    _require_create(request, actor, job, "import.cancel_denied")
    with transaction.atomic():
        job = ImportJob.objects.select_for_update().select_related("engagement").get(pk=job.pk)
        if job.status not in ("uploaded", "parsed", "previewed"):
            raise Conflict("Only an import that has not started working can be cancelled.")
        job.status, job.finished_at = "cancelled", timezone.now()
        job.version += 1
        job.save()
        audit.record("import.cancelled", request=request, entity=job, engagement=job.engagement)
    _purge_file(job)
    return job


def _purge_file(job: ImportJob) -> None:
    if job.storage_key:
        try:
            get_storage().delete(job.storage_key)
        finally:
            ImportJob.objects.filter(pk=job.pk).update(storage_key="", file_purged_at=timezone.now())


def cleanup() -> dict:
    """Daily: close jobs stuck in a working state, and delete uploaded files of finished jobs after 30 days.
    Job and row history stay."""
    now = timezone.now()
    stuck = ImportJob.objects.filter(status__in=ImportJob.WORKING, updated_at__lt=now - STALE)
    stuck_count = 0
    for job in stuck.select_related("engagement", "uploaded_by"):
        _fail(job, "The import did not finish in time.")
        stuck_count += 1
    old = ImportJob.objects.filter(status__in=ImportJob.FINISHED, finished_at__lt=now - FILE_RETENTION).exclude(
        storage_key=""
    )
    purged = 0
    for job in old:
        _purge_file(job)
        purged += 1
    return {"stuck": stuck_count, "purged": purged}
