"""Scoped reads. Every engagement-bound read starts here (never ``Engagement.objects`` directly)."""

import uuid

from django.db.models import BooleanField, Case, Q, Value, When
from django.utils import timezone

from apps.rbac.authz import engagement_permissions, role_permission_codes, user_permissions

from .models import OPEN_STATUSES, Engagement, EngagementMembership, EngagementNote

# Holding any of these platform permissions means "applies everywhere", so the holder must
# be able to reach every engagement to use them.
PLATFORM_ENGAGEMENT_CODES = (
    "engagements.create", "engagements.update", "engagements.archive",
    "engagements.delete", "engagements.schedule",
)  # fmt: skip


def _active(user) -> bool:
    return bool(getattr(user, "is_authenticated", False) and user.is_active)


def membership_role(user, engagement_id):
    """Membership provider for apps.rbac.authz: role held on one engagement, or None."""
    try:
        eid = uuid.UUID(str(engagement_id))
    except ValueError:
        return None
    member = (
        EngagementMembership.objects.filter(engagement_id=eid, user_id=user.pk).select_related("role_override").first()
    )
    if member is None:
        return None
    return member.role_override or user.role


def membership_roles(user):
    """Roles held across all memberships (coarse action gate in authz.has_perm_somewhere)."""
    roles = {}
    for m in EngagementMembership.objects.filter(user_id=user.pk).select_related("role_override"):
        role = m.role_override or user.role
        roles[role.pk] = role
    return list(roles.values())


def sees_everything(user, code: str, platform_codes: tuple[str, ...] = ()) -> bool:
    """Roles reaching every engagement (and holders of the platform write codes) see all rows."""
    if not _active(user):
        return False
    perms = user_permissions(user)
    if user.role.all_engagements and code in perms:
        return True
    return any(c in perms for c in platform_codes)


def engagement_ids_with(user, code: str) -> set:
    """Ids of engagements on which the user holds ``code`` through a membership."""
    if not _active(user):
        return set()
    cache: dict = {}
    ids = set()
    for m in EngagementMembership.objects.filter(user_id=user.pk).select_related("role_override"):
        role = m.role_override or user.role
        if role.pk not in cache:
            cache[role.pk] = role_permission_codes(role.pk)
        if code in cache[role.pk]:
            ids.add(m.engagement_id)
    return ids


def scope_engagements(user, code: str = "engagements.view"):
    if not _active(user):
        return Engagement.objects.none()
    platform = PLATFORM_ENGAGEMENT_CODES if code == "engagements.view" else ()
    if sees_everything(user, code, platform):
        return Engagement.objects.all()
    return Engagement.objects.filter(id__in=engagement_ids_with(user, code))


def with_overdue(qs):
    today = timezone.localdate()
    return qs.annotate(
        overdue=Case(
            When(Q(end_date__lt=today, status__in=OPEN_STATUSES), then=Value(True)),
            default=Value(False),
            output_field=BooleanField(),
        )
    )


def visible_notes(user, engagement: Engagement):
    codes = engagement_permissions(user, engagement.pk)
    levels = []
    if "engagement_notes.view_team" in codes:
        levels += ["team", "all"]
    elif "engagement_notes.view_shared" in codes:
        levels.append("all")
    return EngagementNote.objects.filter(engagement=engagement, visibility__in=levels).select_related("author")
