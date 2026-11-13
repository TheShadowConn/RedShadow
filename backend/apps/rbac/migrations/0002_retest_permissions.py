from django.db import migrations

# code -> description, granted to the system roles on an existing database.
# (A fresh database gets the same grants from seed_rbac when the roles are first created.)
NEW = {
    "retests.view": "View retest rounds",
    "retests.create": "Request retest rounds and choose the assessor",
    "retests.record": "Record retest results (only the assigned assessor can)",
    "retests.manage": "Reassign or cancel any retest round",
}
GRANTS = {
    "super_admin": list(NEW),
    "pentester": ["retests.view", "retests.create", "retests.record"],
    "remediation": ["retests.view"],
}


def add(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")
    for code, description in NEW.items():
        module, _, action = code.partition(".")
        Permission.objects.update_or_create(
            code=code,
            defaults={"module": module, "action": action, "scope": "engagement", "description": description},
        )
    for key, codes in GRANTS.items():
        role = Role.objects.filter(system_key=key).first()
        if role is None:
            continue
        for code in codes:
            RolePermission.objects.get_or_create(role=role, permission_id=code)


class Migration(migrations.Migration):
    dependencies = [("rbac", "0001_initial")]
    operations = [migrations.RunPython(add, migrations.RunPython.noop)]
