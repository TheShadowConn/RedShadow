"""Attachment writes. Blobs are written before the row and removed if the row fails."""

import hashlib
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit import service as audit
from apps.core.errors import Conflict, PayloadTooLarge
from apps.core.storage import get_storage
from apps.engagements.models import Engagement, EngagementScenario
from apps.findings.models import Finding
from apps.organisations.models import Organisation
from apps.rbac.authz import has_engagement_perm
from apps.rbac.guards import deny

from .models import Attachment
from .validation import IMAGE_KINDS, UploadRejected, clean_name, inspect_upload


def _read_upload(uploaded) -> bytes:
    if uploaded.size > settings.ATTACHMENT_MAX_BYTES:
        raise PayloadTooLarge(f"The file is larger than {settings.ATTACHMENT_MAX_BYTES // (1024 * 1024)} MB.")
    data = uploaded.read(settings.ATTACHMENT_MAX_BYTES + 1)
    if len(data) > settings.ATTACHMENT_MAX_BYTES:
        raise PayloadTooLarge(f"The file is larger than {settings.ATTACHMENT_MAX_BYTES // (1024 * 1024)} MB.")
    return data


def _store(
    request, actor, uploaded, *, kind, engagement=None, organisation=None, finding=None, scenario=None,
    allowed_kinds=None,
) -> Attachment:
    name = clean_name(uploaded.name)
    try:
        inspected = inspect_upload(name, _read_upload(uploaded), allowed_kinds)
    except UploadRejected as exc:
        raise ValidationError({"file": [str(exc)]}) from None
    storage = get_storage()
    key = storage.save(inspected.data)
    try:
        with transaction.atomic():
            att = Attachment.objects.create(
                kind=kind, engagement=engagement, organisation=organisation, finding=finding, scenario=scenario,
                original_name=name,
                storage_key=key, mime=inspected.mime, size=len(inspected.data),
                sha256=hashlib.sha256(inspected.data).hexdigest(), uploaded_by=actor,
            )  # fmt: skip
            audit.record(
                "attachment.uploaded", request=request, entity=att, engagement=engagement,
                metadata={
                    "kind": kind, "size": att.size, "sha256": att.sha256,
                    "organisation": organisation.name if organisation else None,
                    "finding_id": str(finding.pk) if finding else None,
                    "finding": finding.ref if finding else None,
                    "scenario_id": str(scenario.pk) if scenario else None,
                },
            )  # fmt: skip
    except Exception:
        storage.delete(key)
        raise
    return att


def upload_document(request, actor, engagement: Engagement, uploaded) -> Attachment:
    if not has_engagement_perm(actor, engagement.pk, "documents.upload"):
        deny(request, "attachment.upload_denied", "You do not have permission to upload documents.", engagement)
    if engagement.is_archived:
        raise Conflict("This engagement is archived. Unarchive it to make changes.")
    return _store(request, actor, uploaded, kind="document", engagement=engagement)


def delete_document(request, actor, att: Attachment) -> None:
    if att.kind != "document":
        raise Conflict("Only engagement documents are deleted here.")
    if not has_engagement_perm(actor, att.engagement_id, "documents.delete"):
        deny(request, "attachment.delete_denied", "You do not have permission to delete documents.", att)
    with transaction.atomic():
        att = Attachment.objects.select_for_update(of=("self",)).select_related("engagement").get(pk=att.pk)
        if att.engagement.is_archived:
            raise Conflict("This engagement is archived. Unarchive it to make changes.")
        att.deleted_at = timezone.now()
        att.save(update_fields=["deleted_at", "updated_at"])
        audit.record("attachment.deleted", request=request, entity=att, engagement=att.engagement)


MAX_EVIDENCE_PER_FINDING = 50


def upload_evidence(request, actor, finding: Finding, uploaded) -> Attachment:
    eng = finding.engagement
    if not has_engagement_perm(actor, eng.pk, "evidence.upload"):
        deny(request, "evidence.upload_denied", "You do not have permission to upload evidence.", finding,
             engagement=eng)  # fmt: skip
    if eng.is_archived:
        raise Conflict("This engagement is archived. Unarchive it to make changes.")
    if Attachment.objects.filter(finding=finding, deleted_at__isnull=True).count() >= MAX_EVIDENCE_PER_FINDING:
        raise Conflict(f"A finding can hold at most {MAX_EVIDENCE_PER_FINDING} evidence files.")
    return _store(request, actor, uploaded, kind="evidence", engagement=eng, finding=finding)


def delete_evidence(request, actor, att: Attachment) -> None:
    """Uploaders with evidence.delete_own remove their own files; findings.delete holders remove any."""
    eng = att.engagement
    own = att.uploaded_by_id == actor.pk and has_engagement_perm(actor, eng.pk, "evidence.delete_own")
    if not own and not has_engagement_perm(actor, eng.pk, "findings.delete"):
        deny(request, "evidence.delete_denied", "You can only delete your own evidence.", att, engagement=eng)
    with transaction.atomic():
        att = Attachment.objects.select_for_update(of=("self",)).select_related("engagement").get(pk=att.pk)
        if att.engagement.is_archived:
            raise Conflict("This engagement is archived. Unarchive it to make changes.")
        att.deleted_at = timezone.now()
        att.save(update_fields=["deleted_at", "updated_at"])
        audit.record("attachment.deleted", request=request, entity=att, engagement=att.engagement,
                     metadata={"kind": "evidence", "finding_id": str(att.finding_id)})  # fmt: skip


MAX_IMAGES_PER_SCENARIO = 10


def upload_scenario_image(request, actor, scenario: EngagementScenario, uploaded) -> Attachment:
    eng = scenario.engagement
    if not has_engagement_perm(actor, eng.pk, "engagement_scenarios.manage"):
        deny(request, "attachment.upload_denied", "You do not have permission to change scenarios.", eng)
    if eng.is_archived:
        raise Conflict("This engagement is archived. Unarchive it to make changes.")
    if Attachment.objects.filter(scenario=scenario, deleted_at__isnull=True).count() >= MAX_IMAGES_PER_SCENARIO:
        raise Conflict(f"A scenario can hold at most {MAX_IMAGES_PER_SCENARIO} pictures.")
    return _store(request, actor, uploaded, kind="scenario_image", engagement=eng, scenario=scenario,
                  allowed_kinds=IMAGE_KINDS)  # fmt: skip


def delete_scenario_image(request, actor, att: Attachment) -> None:
    if att.kind != "scenario_image":
        raise Conflict("Only scenario pictures are deleted here.")
    if not has_engagement_perm(actor, att.engagement_id, "engagement_scenarios.manage"):
        deny(request, "attachment.delete_denied", "You do not have permission to change scenarios.", att)
    with transaction.atomic():
        att = Attachment.objects.select_for_update(of=("self",)).select_related("engagement").get(pk=att.pk)
        if att.engagement.is_archived:
            raise Conflict("This engagement is archived. Unarchive it to make changes.")
        att.deleted_at = timezone.now()
        att.save(update_fields=["deleted_at", "updated_at"])
        audit.record("attachment.deleted", request=request, entity=att, engagement=att.engagement,
                     metadata={"kind": "scenario_image", "scenario_id": str(att.scenario_id)})  # fmt: skip


def set_logo(request, actor, org: Organisation, uploaded) -> Attachment:
    if org.is_archived:
        raise Conflict("This organisation is archived. Unarchive it to make changes.")
    att = _store(request, actor, uploaded, kind="logo", organisation=org, allowed_kinds=IMAGE_KINDS)
    with transaction.atomic():
        org = Organisation.objects.select_for_update().get(pk=org.pk)
        old = org.logo_id
        org.logo = att
        org.save(update_fields=["logo", "updated_at"])
        if old:
            Attachment.objects.filter(pk=old).update(deleted_at=timezone.now())
        audit.record("organisation.logo_set", request=request, entity=org, metadata={"attachment": str(att.pk)})
    return att


def remove_logo(request, actor, org: Organisation) -> None:
    if org.is_archived:
        raise Conflict("This organisation is archived. Unarchive it to make changes.")
    with transaction.atomic():
        org = Organisation.objects.select_for_update().get(pk=org.pk)
        if org.logo_id:
            Attachment.objects.filter(pk=org.logo_id).update(deleted_at=timezone.now())
            org.logo = None
            org.save(update_fields=["logo", "updated_at"])
            audit.record("organisation.logo_removed", request=request, entity=org)


def purge_deleted(retention_days: int | None = None) -> int:
    """Remove blobs of attachments soft-deleted longer ago than the retention period."""
    days = settings.ATTACHMENT_RETENTION_DAYS if retention_days is None else retention_days
    cutoff = timezone.now() - timedelta(days=days)
    storage = get_storage()
    count = 0
    for att in Attachment.objects.filter(deleted_at__lte=cutoff, purged_at__isnull=True):
        storage.delete(att.storage_key)
        att.purged_at = timezone.now()
        att.save(update_fields=["purged_at", "updated_at"])
        count += 1
    return count
