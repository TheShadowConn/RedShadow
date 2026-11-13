"""Anti-escalation rules (blueprint 5.2). Every refusal is written to the audit log first,
outside any transaction that will roll back, then raised as 403."""

from rest_framework.exceptions import PermissionDenied

from apps.audit import service as audit

from .authz import role_permission_codes, user_permissions
from .catalogue import SUPER_ADMIN


def deny(request, action: str, reason: str, entity=None, metadata: dict | None = None, engagement=None):
    audit.record(
        action,
        request=request,
        entity=entity,
        engagement=engagement,
        outcome="denied",
        metadata={"reason": reason, **(metadata or {})},
    )
    raise PermissionDenied(reason)


def assert_not_self(request, actor, target, action: str) -> None:
    if actor.pk == target.pk:
        deny(request, action, "You cannot change your own role, access or account state.", target)


def assert_outranks(request, actor, target, action: str) -> None:
    """Actor must hold every permission of the target's role (no managing a more powerful user)."""
    if not role_permission_codes(target.role_id) <= user_permissions(actor):
        deny(request, action, "You cannot manage a user with more access than you have.", target)


def assert_can_grant_role(request, actor, role, action: str, entity=None) -> None:
    """Assigning a role requires roles.assign and a role no broader than the actor's own."""
    if "roles.assign" not in user_permissions(actor):
        deny(request, action, "You do not have permission to assign roles.", entity)
    if not role_permission_codes(role.pk) <= user_permissions(actor):
        deny(request, action, "You cannot grant a role with more permissions than you have.", entity)
    if role.all_engagements and not actor.role.all_engagements:
        deny(request, action, "You cannot grant access to all engagements.", entity)


def active_super_admin_count() -> int:
    from apps.accounts.models import User

    return User.objects.filter(is_active=True, role__system_key=SUPER_ADMIN).count()


def assert_not_last_super_admin(request, target, action: str) -> None:
    if target.role.system_key == SUPER_ADMIN and target.is_active and active_super_admin_count() <= 1:
        deny(request, action, "The last active Super Admin cannot be demoted or deactivated.", target)
