from django.db.models import Q

from apps.engagements.selectors import _active, engagement_ids_with, sees_everything
from apps.findings.selectors import scope_findings
from apps.organisations.selectors import scope_organisations

from .models import Attachment


def scope_attachments(user):
    """Live attachments the user may reach: documents of engagements where they hold documents.view,
    logos of organisations they can see, and evidence of findings they can see (evidence.view)."""
    if not _active(user):
        return Attachment.objects.none()
    orgs = scope_organisations(user)
    if sees_everything(user, "documents.view"):
        docs = Q(kind="document")
    else:
        docs = Q(kind="document", engagement_id__in=engagement_ids_with(user, "documents.view"))
    evidence = Q(kind="evidence", finding_id__in=scope_findings(user).values("id"))
    if not sees_everything(user, "evidence.view"):
        evidence &= Q(engagement_id__in=engagement_ids_with(user, "evidence.view"))
    return (
        Attachment.objects.filter(deleted_at__isnull=True)
        .filter(docs | Q(kind="logo", organisation__in=orgs) | evidence)
        .select_related("uploaded_by")
    )
