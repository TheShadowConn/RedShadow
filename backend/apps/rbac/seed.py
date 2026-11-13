from django.db import transaction
from django.db.models import F

from .catalogue import PERMISSIONS, SYSTEM_ROLES, split
from .models import Permission, Role, RolePermission


def _adopt_custom_role(key: str, spec: dict) -> None:
    """A custom role that already uses a new system role's name (names are unique) becomes that system
    role, reset to its defaults. Its users get a new session version so the change applies at once."""
    if Role.objects.filter(system_key=key).exists():
        return
    legacy = Role.objects.filter(name=spec["name"], system_key__isnull=True).first()
    if legacy is None:
        return
    legacy.system_key = key
    legacy.description = spec["description"]
    legacy.all_engagements = spec["all_engagements"]
    legacy.finding_scope = spec["finding_scope"]
    legacy.mfa_required = spec["mfa_required"]
    legacy.save()
    legacy.role_permissions.all().delete()
    RolePermission.objects.bulk_create([RolePermission(role=legacy, permission_id=c) for c in spec["grants"]])
    legacy.users.update(session_version=F("session_version") + 1)


@transaction.atomic
def seed_rbac() -> None:
    """Idempotent. Keeps the catalogue in sync; creates system roles once.

    - Permissions: created or updated to match the catalogue (never deleted here).
    - Super Admin: always granted the full catalogue.
    - Pentester / Remediation: default grants only when the role is first created, so admin
      edits survive upgrades. New catalogue entries are not auto-granted to them.
    """
    for code, (scope, description) in PERMISSIONS.items():
        module, action = split(code)
        Permission.objects.update_or_create(
            code=code,
            defaults={"module": module, "action": action, "scope": scope, "description": description},
        )

    for key, spec in SYSTEM_ROLES.items():
        _adopt_custom_role(key, spec)
        role, created = Role.objects.get_or_create(
            system_key=key,
            defaults={
                "name": spec["name"],
                "description": spec["description"],
                "all_engagements": spec["all_engagements"],
                "finding_scope": spec["finding_scope"],
                "mfa_required": spec["mfa_required"],
            },
        )
        if created or key == "super_admin":
            existing = set(role.role_permissions.values_list("permission_id", flat=True))
            RolePermission.objects.bulk_create(
                [RolePermission(role=role, permission_id=c) for c in spec["grants"] if c not in existing]
            )
