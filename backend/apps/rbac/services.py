from django.db import IntegrityError, transaction
from django.db.models import F
from rest_framework.exceptions import ValidationError

from apps.accounts.models import User
from apps.audit import service as audit
from apps.core.errors import Conflict

from .authz import user_permissions
from .guards import deny
from .models import Permission, Role, RolePermission

ROLE_FIELDS = ("name", "description", "all_engagements", "finding_scope", "mfa_required")


def _snapshot(role: Role) -> dict:
    data = {f: getattr(role, f) for f in ROLE_FIELDS}
    data["permissions"] = sorted(role.role_permissions.values_list("permission_id", flat=True))
    return data


def _check_permission_codes(codes: list[str]) -> set[str]:
    found = set(Permission.objects.filter(code__in=codes).values_list("code", flat=True))
    unknown = set(codes) - found
    if unknown:
        raise ValidationError({"permissions": [f"Unknown permission: {c}" for c in sorted(unknown)]})
    return found


def _assert_grantable(request, actor, role_flags: dict, codes: set[str], action: str, entity=None):
    missing = codes - user_permissions(actor)
    if missing:
        deny(
            request, action, "You cannot grant permissions you do not hold.", entity,
            {"permissions": sorted(missing)},
        )  # fmt: skip
    if role_flags.get("all_engagements") and not actor.role.all_engagements:
        deny(request, action, "You cannot grant access to all engagements.", entity)


def create_role(request, actor, data: dict) -> Role:
    codes = _check_permission_codes(data.get("permissions", []))
    _assert_grantable(request, actor, data, codes, "role.create_denied")
    try:
        with transaction.atomic():
            role = Role.objects.create(**{f: data[f] for f in ROLE_FIELDS if f in data})
            RolePermission.objects.bulk_create([RolePermission(role=role, permission_id=c) for c in codes])
            audit.record("role.created", request=request, entity=role, changes={"after": _snapshot(role)})
    except IntegrityError as exc:
        raise ValidationError({"name": ["A role with this name already exists."]}) from exc
    return role


def update_role(request, actor, role: Role, data: dict) -> Role:
    if role.system_key == "super_admin":
        deny(request, "role.update_denied", "The Super Admin role cannot be modified.", role)
    if role.pk == actor.role_id:
        deny(request, "role.update_denied", "You cannot edit your own role.", role)
    if role.is_system and "name" in data and data["name"] != role.name:
        deny(request, "role.update_denied", "System roles cannot be renamed.", role)

    new_codes = _check_permission_codes(data["permissions"]) if "permissions" in data else None
    before = _snapshot(role)
    added = set(new_codes) - set(before["permissions"]) if new_codes is not None else set()
    _assert_grantable(request, actor, data if "all_engagements" in data else {}, added, "role.update_denied", role)

    try:
        with transaction.atomic():
            role = Role.objects.select_for_update().get(pk=role.pk)
            for field in ROLE_FIELDS:
                if field in data:
                    setattr(role, field, data[field])
            role.save()
            if new_codes is not None:
                role.role_permissions.exclude(permission_id__in=new_codes).delete()
                have = set(role.role_permissions.values_list("permission_id", flat=True))
                RolePermission.objects.bulk_create(
                    [RolePermission(role=role, permission_id=c) for c in new_codes - have]
                )
            after = _snapshot(role)
            if after != before:
                # Role/permission changes force re-login of everyone holding the role.
                User.objects.filter(role=role).update(session_version=F("session_version") + 1)
                changes = {k: [before[k], after[k]] for k in after if before[k] != after[k]}
                audit.record("role.updated", request=request, entity=role, changes=changes)
    except IntegrityError as exc:
        raise ValidationError({"name": ["A role with this name already exists."]}) from exc
    return role


def delete_role(request, actor, role: Role) -> None:
    if role.is_system:
        deny(request, "role.delete_denied", "System roles cannot be deleted.", role)
    if role.pk == actor.role_id:
        deny(request, "role.delete_denied", "You cannot delete your own role.", role)
    if role.users.exists():
        raise Conflict("This role is assigned to users. Reassign them first.")
    with transaction.atomic():
        snapshot = _snapshot(role)
        audit.record("role.deleted", request=request, entity=role, changes={"before": snapshot})
        role.delete()
