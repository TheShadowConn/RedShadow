"""Scoped audit reads. Every audit read starts at ``scope_audit`` (never ``AuditEvent.objects``).

Rules, matching the history tabs on engagements and findings:
- ``audit.view_all`` (Super Admin) sees everything, including platform events with no engagement.
- ``audit.view_engagement`` sees events of engagements where the user holds it, and nothing else.
- Where the user lacks ``findings.view_draft``: finding events only for findings they can see and
  only from the publish event on, and no evidence events (so draft text and evidence names stay
  with the testing team).
- Where the user lacks ``finding_notes.technical``: no technical-note events.
"""

from django.db.models import CharField, OuterRef, Q, Subquery
from django.db.models.functions import Cast

from apps.engagements.selectors import scope_engagements
from apps.findings.selectors import scope_findings
from apps.rbac.authz import user_permissions

from .models import AuditEvent


def can_view_all(user) -> bool:
    return "audit.view_all" in user_permissions(user)


def scope_audit(user):
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return AuditEvent.objects.none()
    if can_view_all(user):
        return AuditEvent.objects.all()
    engagements = set(scope_engagements(user, "audit.view_engagement").values_list("pk", flat=True))
    if not engagements:
        return AuditEvent.objects.none()
    drafts = set(scope_engagements(user, "findings.view_draft").values_list("pk", flat=True))
    technical = set(scope_engagements(user, "finding_notes.technical").values_list("pk", flat=True))

    visible_findings = scope_findings(user).annotate(_s=Cast("pk", CharField())).values("_s")
    published = (
        AuditEvent.objects.filter(entity_type="finding", entity_id=OuterRef("entity_id"), action="finding.published")
        .order_by("id")
        .values("id")[:1]
    )
    not_finding_or_evidence = ~Q(entity_type="finding") & ~Q(metadata__kind="evidence")
    published_and_visible = (
        Q(entity_type="finding") & Q(entity_id__in=visible_findings) & Q(id__gte=Subquery(published))
    )
    qs = AuditEvent.objects.filter(engagement_id__in=engagements).filter(
        Q(engagement_id__in=drafts) | not_finding_or_evidence | published_and_visible
    )
    hidden_technical = engagements - technical
    if hidden_technical:
        qs = qs.exclude(engagement_id__in=hidden_technical, action="finding.technical_note_added")
    return qs
