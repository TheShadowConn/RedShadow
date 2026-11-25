from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel

# Sections a report can contain. "cover" and "findings" are always present; the rest can be switched off and
# reordered in a template. The renderer places the cover first and the contents page right after it.
SECTIONS = [
    ("document_control", "Document control"),
    ("executive_summary", "Executive summary"),
    ("engagement_info", "Engagement overview"),
    ("scope", "Scope"),
    ("scenarios", "Test scenarios"),
    ("methodology", "Methodology and rating scale"),
    ("summary_table", "Findings at a glance"),
    ("severity_distribution", "Severity and status distribution"),
    ("findings", "Detailed findings"),
    ("remediation_roadmap", "Remediation roadmap"),
    ("retest_summary", "Retest results"),
    ("appendix", "Appendix"),
]
SECTION_KEYS = [key for key, _ in SECTIONS]
REQUIRED_SECTIONS = ("findings",)
FONTS = [("geist", "Geist (sans-serif)"), ("serif", "DejaVu Serif")]


def default_sections() -> list[str]:
    return list(SECTION_KEYS)


class ReportTemplate(BaseModel):
    """Look and content of a PDF report. Fonts come from a fixed allow-list; the logo is a re-encoded PNG."""

    name = models.CharField(max_length=120, unique=True)
    sections = models.JSONField(default=default_sections)  # ordered list of SECTION_KEYS
    accent = models.CharField(max_length=7, default="#ef233c")
    font = models.CharField(max_length=10, choices=FONTS, default="geist")
    footer_text = models.CharField(max_length=160, blank=True)
    logo_key = models.CharField(max_length=64, blank=True)
    is_default = models.BooleanField(default=False)
    created_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_default"], condition=Q(is_default=True), name="one_default_report_template"
            )
        ]

    def audit_label(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name


class ReportJob(BaseModel):
    """One request for a report file. The worker builds it from the requester's own finding scope."""

    FORMATS = [("pdf", "PDF"), ("csv", "CSV")]
    AUDIENCES = [("client", "Client-facing"), ("internal", "Internal (with technical detail)")]
    STATUSES = [("queued", "Queued"), ("rendering", "Building"), ("done", "Ready"), ("failed", "Failed")]
    WORKING = ("queued", "rendering")

    engagement = models.ForeignKey("engagements.Engagement", on_delete=models.PROTECT, related_name="report_jobs")
    requested_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    template = models.ForeignKey(ReportTemplate, null=True, blank=True, on_delete=models.SET_NULL, related_name="jobs")
    template_name = models.CharField(max_length=120, blank=True)  # kept when the template is deleted
    format = models.CharField(max_length=3, choices=FORMATS)
    audience = models.CharField(max_length=8, choices=AUDIENCES, default="client")
    title = models.CharField(max_length=160, blank=True)
    version_label = models.CharField(max_length=20, default="1.0")
    classification = models.CharField(max_length=40, default="Confidential")
    filters = models.JSONField(default=dict)  # {"severities": [...], "statuses": [...]}
    status = models.CharField(max_length=10, choices=STATUSES, default="queued")
    error = models.CharField(max_length=300, blank=True)
    finding_count = models.PositiveIntegerField(default=0)
    page_count = models.PositiveIntegerField(null=True, blank=True)
    storage_key = models.CharField(max_length=64, blank=True)
    file_name = models.CharField(max_length=160, blank=True)
    size = models.PositiveBigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    file_purged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["engagement", "status"], name="reportjob_eng_status")]

    @property
    def file_available(self) -> bool:
        return self.status == "done" and bool(self.storage_key) and self.file_purged_at is None

    def audit_label(self) -> str:
        return f"{self.format.upper()} report for {self.engagement.ref}"

    def __str__(self) -> str:
        return self.audit_label()
