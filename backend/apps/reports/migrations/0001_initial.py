import uuid

import django.db.models.deletion
from django.db import migrations, models

import apps.reports.models

SECTIONS = [
    "document_control", "executive_summary", "engagement_info", "scope", "methodology", "summary_table",
    "severity_distribution", "findings", "remediation_roadmap", "retest_summary", "appendix",
]  # fmt: skip


def seed_default_template(apps, schema_editor):
    template = apps.get_model("reports", "ReportTemplate")
    template.objects.get_or_create(
        name="RedShadow standard",
        defaults={"sections": SECTIONS, "accent": "#e5383b", "font": "geist", "is_default": True},
    )


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("accounts", "0001_initial"),
        ("engagements", "0003_asset_org_trigger"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReportTemplate",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=120, unique=True)),
                ("sections", models.JSONField(default=apps.reports.models.default_sections)),
                ("accent", models.CharField(default="#e5383b", max_length=7)),
                ("font", models.CharField(choices=[("geist", "Geist (sans-serif)"), ("serif", "DejaVu Serif")], default="geist", max_length=10)),
                ("footer_text", models.CharField(blank=True, max_length=160)),
                ("logo_key", models.CharField(blank=True, max_length=64)),
                ("is_default", models.BooleanField(default=False)),
                ("version", models.PositiveIntegerField(default=1)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="accounts.user")),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="ReportJob",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("template_name", models.CharField(blank=True, max_length=120)),
                ("format", models.CharField(choices=[("pdf", "PDF"), ("csv", "CSV")], max_length=3)),
                ("audience", models.CharField(choices=[("client", "Client-facing"), ("internal", "Internal (with technical detail)")], default="client", max_length=8)),
                ("title", models.CharField(blank=True, max_length=160)),
                ("version_label", models.CharField(default="1.0", max_length=20)),
                ("classification", models.CharField(default="Confidential", max_length=40)),
                ("filters", models.JSONField(default=dict)),
                ("status", models.CharField(choices=[("queued", "Queued"), ("rendering", "Building"), ("done", "Ready"), ("failed", "Failed")], default="queued", max_length=10)),
                ("error", models.CharField(blank=True, max_length=300)),
                ("finding_count", models.PositiveIntegerField(default=0)),
                ("page_count", models.PositiveIntegerField(blank=True, null=True)),
                ("storage_key", models.CharField(blank=True, max_length=64)),
                ("file_name", models.CharField(blank=True, max_length=160)),
                ("size", models.PositiveBigIntegerField(default=0)),
                ("sha256", models.CharField(blank=True, max_length=64)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("file_purged_at", models.DateTimeField(blank=True, null=True)),
                ("engagement", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="report_jobs", to="engagements.engagement")),
                ("requested_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to="accounts.user")),
                ("template", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="jobs", to="reports.reporttemplate")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="reporttemplate",
            constraint=models.UniqueConstraint(condition=models.Q(("is_default", True)), fields=("is_default",), name="one_default_report_template"),
        ),
        migrations.AddIndex(
            model_name="reportjob",
            index=models.Index(fields=["engagement", "status"], name="reportjob_eng_status"),
        ),
        migrations.RunPython(seed_default_template, migrations.RunPython.noop),
    ]
