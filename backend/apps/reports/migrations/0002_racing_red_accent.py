from django.db import migrations, models

OLD, NEW = "#e5383b", "#ef233c"


def to_new(apps, schema_editor):
    """Templates still on the old default move to Racing Red. Custom accents are left alone."""
    apps.get_model("reports", "ReportTemplate").objects.filter(accent=OLD).update(accent=NEW)


def to_old(apps, schema_editor):
    apps.get_model("reports", "ReportTemplate").objects.filter(accent=NEW).update(accent=OLD)


class Migration(migrations.Migration):
    dependencies = [("reports", "0001_initial")]
    operations = [
        migrations.AlterField("reporttemplate", "accent", models.CharField(default=NEW, max_length=7)),
        migrations.RunPython(to_new, to_old),
    ]
