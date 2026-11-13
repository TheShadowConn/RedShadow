import json
from pathlib import Path

from django.db import migrations

DATA = Path(__file__).resolve().parent.parent / "data" / "cwe.json"


def seed(apps, schema_editor):
    CWE = apps.get_model("findings", "CWE")
    for cwe_id, name in json.loads(DATA.read_text()):
        CWE.objects.update_or_create(id=cwe_id, defaults={"name": name})


class Migration(migrations.Migration):
    dependencies = [("findings", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
