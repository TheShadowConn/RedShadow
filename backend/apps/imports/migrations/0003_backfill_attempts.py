"""Give every existing import job one attempt record so the new history view is complete."""

from django.db import migrations

OUTCOME = {"completed": "completed", "failed": "failed", "cancelled": "cancelled"}


def forwards(apps, schema_editor):
    ImportJob = apps.get_model("imports", "ImportJob")
    ImportAttempt = apps.get_model("imports", "ImportAttempt")
    batch = [
        ImportAttempt(
            job_id=j.pk,
            number=1,
            uploaded_by_id=j.uploaded_by_id,
            original_name=j.original_name,
            file_sha256=j.file_sha256,
            file_size=j.file_size,
            counts=j.counts,
            outcome=OUTCOME.get(j.status, "in_progress"),
            error=j.error,
            finished_at=j.finished_at,
        )
        for j in ImportJob.objects.all().iterator()
    ]
    ImportAttempt.objects.bulk_create(batch, batch_size=500)


class Migration(migrations.Migration):
    dependencies = [("imports", "0002_asset_identifiers")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
