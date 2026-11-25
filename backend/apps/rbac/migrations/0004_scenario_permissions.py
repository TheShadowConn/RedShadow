from django.db import migrations

# code -> description, granted to the system roles on an existing database.
# (A fresh database gets the same grants from seed_rbac when the roles are first created.)
NEW = {
    "engagement_scenarios.view": "View engagement scenarios and their pictures",
    "engagement_scenarios.manage": "Add, edit, reschedule, cancel and reorder scenarios",
}
GRANTS = {
    "super_admin": list(NEW),
    "pentester": list(NEW),
    "remediation": ["engagement_scenarios.view"],
    "external_vendor": ["engagement_scenarios.view"],
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
    dependencies = [("rbac", "0003_alter_role_finding_scope")]
    operations = [migrations.RunPython(add, migrations.RunPython.noop)]
