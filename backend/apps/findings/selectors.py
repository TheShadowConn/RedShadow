"""Scoped reads. Every finding read starts at ``scope_findings`` (never ``Finding.objects``)."""

from django.db.models import Case, IntegerField, Q, Value, When

from apps.engagements.models import EngagementMembership
from apps.rbac.authz import engagement_permissions, role_permission_codes, user_permissions

from .models import SEVERITY_ORDER, Finding, FindingNote


def _active(user) -> bool:
    return bool(getattr(user, "is_authenticated", False) and user.is_active)


def _clause(user, ids, can_draft: bool, mode: str) -> Q:
    """mode: "all", "assigned" (assigned to the user) or "own" (reported by or assigned to the user)."""
    q = Q(engagement_id__in=ids) if ids is not None else Q()
    if not can_draft:
        q &= ~Q(status="draft")
    if mode == "assigned":
        q &= Q(remediation_owner=user) | Q(assigned_pentester=user)
    elif mode == "own":
        q &= Q(reported_by=user) | Q(remediation_owner=user) | Q(assigned_pentester=user)
    return q


def own_scope_restriction(user) -> tuple[bool, list]:
    """Where the user sees only their own work: (every engagement?, engagement ids). Used to narrow
    reads that are not findings (import jobs) the same way scope_findings narrows findings."""
    if not _active(user):
        return False, []
    if user.role.all_engagements:
        return user.role.finding_scope == "own", []
    ids = [
        m.engagement_id
        for m in EngagementMembership.objects.filter(user_id=user.pk).select_related("role_override")
        if (m.finding_scope or (m.role_override or user.role).finding_scope) == "own"
    ]
    return False, ids


def scope_findings(user):
    """Findings the user may see: findings.view on the engagement, drafts only with
    findings.view_draft, and only assigned findings when the finding scope is "assigned", only findings reported by or
    assigned to the user when it is "own" (External Vendor)."""
    if not _active(user):
        return Finding.objects.none()
    role = user.role
    if role.all_engagements:
        perms = user_permissions(user)
        if "findings.view" not in perms:
            return Finding.objects.none()
        return Finding.objects.filter(
            _clause(user, None, "findings.view_draft" in perms, role.finding_scope)
        )
    groups: dict[tuple[bool, str], list] = {}
    cache: dict = {}
    for m in EngagementMembership.objects.filter(user_id=user.pk).select_related("role_override"):
        member_role = m.role_override or role
        if member_role.pk not in cache:
            cache[member_role.pk] = role_permission_codes(member_role.pk)
        codes = cache[member_role.pk]
        if "findings.view" not in codes:
            continue
        scope = m.finding_scope or member_role.finding_scope
        groups.setdefault(("findings.view_draft" in codes, scope), []).append(m.engagement_id)
    if not groups:
        return Finding.objects.none()
    q = Q()
    for (can_draft, mode), ids in groups.items():
        q |= _clause(user, ids, can_draft, mode)
    return Finding.objects.filter(q)


def with_severity_rank(qs):
    return qs.annotate(
        severity_rank=Case(
            *[When(severity=k, then=Value(v)) for k, v in SEVERITY_ORDER.items()],
            default=Value(0),
            output_field=IntegerField(),
        )
    )


def visible_notes(user, finding: Finding):
    """Remediation, verification and retest notes for everyone who sees the finding; technical ones for the team."""
    kinds = ["remediation", "verification", "retest"]
    if "finding_notes.technical" in engagement_permissions(user, finding.engagement_id):
        kinds.append("technical")
    return FindingNote.objects.filter(finding=finding, kind__in=kinds).select_related("author")
