"""The one permission resolver. Every access decision goes through this module.

Platform permissions come from the user's role. Engagement permissions come from the role
(all-engagement roles) or from a membership provider registered by the engagements app
(Phase 3). Per-request cache only (stored on the request-scoped user object), so a revoked
permission takes effect on the next request.
"""

from collections.abc import Callable
from typing import Any

from rest_framework.exceptions import PermissionDenied

from .catalogue import ENGAGEMENT, PERMISSIONS, PLATFORM
from .models import RolePermission

# provider(user, engagement_id) -> Role | None (the role the user holds on that engagement)
_PROVIDERS: list[Callable[[Any, Any], Any]] = []


def register_membership_provider(provider: Callable[[Any, Any], Any]) -> None:
    if provider not in _PROVIDERS:
        _PROVIDERS.append(provider)


def unregister_membership_provider(provider: Callable[[Any, Any], Any]) -> None:
    if provider in _PROVIDERS:
        _PROVIDERS.remove(provider)


# lister(user) -> iterable of Roles the user holds on any engagement (coarse action gate only)
_ROLE_LISTERS: list[Callable[[Any], Any]] = []


def register_membership_role_lister(lister: Callable[[Any], Any]) -> None:
    if lister not in _ROLE_LISTERS:
        _ROLE_LISTERS.append(lister)


def role_permission_codes(role_id) -> frozenset[str]:
    return frozenset(RolePermission.objects.filter(role_id=role_id).values_list("permission_id", flat=True))


def user_permissions(user) -> frozenset[str]:
    """All permission codes of the user's role (both scopes). Empty for inactive users."""
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return frozenset()
    cached = getattr(user, "_rs_perm_cache", None)
    if cached is None:
        cached = role_permission_codes(user.role_id)
        user._rs_perm_cache = cached
    return cached


def has_platform_perm(user, code: str) -> bool:
    if PERMISSIONS[code][0] != PLATFORM:
        raise ValueError(f"{code} is not a platform permission")
    return code in user_permissions(user)


def require_platform(user, code: str) -> None:
    if not has_platform_perm(user, code):
        raise PermissionDenied("You do not have permission to perform this action.")


def engagement_permissions(user, engagement_id) -> frozenset[str]:
    """Engagement-scoped permission codes the user holds on one engagement."""
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return frozenset()
    role = user.role
    if role.all_engagements:
        return frozenset(c for c in user_permissions(user) if PERMISSIONS[c][0] == ENGAGEMENT)
    for provider in _PROVIDERS:
        member_role = provider(user, engagement_id)
        if member_role is not None:
            return frozenset(c for c in role_permission_codes(member_role.pk) if PERMISSIONS[c][0] == ENGAGEMENT)
    return frozenset()


def has_perm_somewhere(user, code: str) -> bool:
    """Coarse gate for engagement-scoped codes: held through the user's role or any membership.

    Never sufficient on its own: object access still needs a scoped queryset or
    ``has_engagement_perm`` on the specific engagement.
    """
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return False
    if code in user_permissions(user):
        return True
    for lister in _ROLE_LISTERS:
        for role in lister(user):
            if code in role_permission_codes(role.pk):
                return True
    return False


def has_engagement_perm(user, engagement_id, code: str) -> bool:
    if PERMISSIONS[code][0] != ENGAGEMENT:
        raise ValueError(f"{code} is not an engagement permission")
    return code in engagement_permissions(user, engagement_id)
