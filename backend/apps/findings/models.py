from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector
from django.db import models
from django.db.models import F, Q

from apps.core.models import BaseModel, SoftDeleteModel

# All nine states are driven by the state machine in lifecycle.py.
STATUSES = [
    ("draft", "Draft"), ("open", "Open"), ("in_progress", "In progress"),
    ("pending_verification", "Pending verification"), ("reopened", "Reopened"), ("closed", "Closed"),
    ("risk_accepted", "Risk accepted"), ("false_positive", "False positive"), ("duplicate", "Duplicate"),
]  # fmt: skip
SEVERITIES = [("critical", "Critical"), ("high", "High"), ("medium", "Medium"), ("low", "Low"), ("info", "Info")]
SEVERITY_ORDER = {key: rank for rank, (key, _) in enumerate(reversed(SEVERITIES))}  # info 0 .. critical 4


class CWE(models.Model):
    """Curated weakness list, seeded by migration from data/cwe.json."""

    id = models.PositiveIntegerField(primary_key=True)
    name = models.CharField(max_length=300)

    class Meta:
        ordering = ["id"]
        verbose_name = "CWE"

    def __str__(self) -> str:
        return f"CWE-{self.id}"


class FindingCounter(models.Model):
    """Single row (pk 1), locked with SELECT ... FOR UPDATE so refs never collide."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    last = models.PositiveBigIntegerField(default=0)


class Finding(BaseModel, SoftDeleteModel):
    SOURCES = [("manual", "Manual"), ("template", "Template"), ("import", "CSV import")]

    ref = models.CharField(max_length=16, unique=True)
    engagement = models.ForeignKey("engagements.Engagement", on_delete=models.PROTECT, related_name="findings")
    asset = models.ForeignKey("organisations.Asset", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    technical_details = models.TextField(blank=True)
    poc = models.TextField(blank=True)
    recommendation = models.TextField(blank=True)
    references = models.JSONField(default=list, blank=True)
    severity = models.CharField(max_length=8, choices=SEVERITIES)
    cvss_version = models.CharField(max_length=3, blank=True)
    cvss_vector = models.CharField(max_length=200, blank=True)
    cvss_score = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    cwe = models.ForeignKey(CWE, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    endpoint = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=24, choices=STATUSES, default="draft")
    reported_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    assigned_pentester = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    remediation_owner = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    discovered_at = models.DateField()
    dedupe_hash = models.CharField(max_length=64)
    duplicate_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="duplicates")
    source = models.CharField(max_length=12, choices=SOURCES, default="manual")
    import_job = models.ForeignKey(
        "imports.ImportJob", null=True, blank=True, on_delete=models.PROTECT, related_name="findings"
    )
    due_date = models.DateField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    closed_at = models.DateTimeField(null=True, blank=True)
    risk_accepted_until = models.DateField(null=True, blank=True)
    risk_acceptance_reason = models.TextField(blank=True)
    sla_breached_at = models.DateTimeField(null=True, blank=True)  # set once by the hourly SLA sweep
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(cvss_score__isnull=True) | (Q(cvss_score__gte=0) & Q(cvss_score__lte=10)),
                name="finding_cvss_score_0_10",
            ),
            models.CheckConstraint(condition=~Q(duplicate_of=F("id")), name="finding_not_duplicate_of_self"),
            models.CheckConstraint(
                condition=~Q(status="duplicate") | Q(duplicate_of__isnull=False), name="finding_duplicate_has_target"
            ),
        ]
        indexes = [
            models.Index(fields=["engagement", "status"], name="finding_eng_status"),
            models.Index(fields=["engagement", "severity"], name="finding_eng_severity"),
            models.Index(fields=["remediation_owner", "status"], name="finding_owner_status"),
            models.Index(fields=["dedupe_hash"], name="finding_dedupe"),
            models.Index(fields=["status", "due_date"], name="finding_status_due"),
            GinIndex(SearchVector("title", "description", config="english"), name="finding_fts"),
        ]

    def audit_label(self) -> str:
        return f"{self.ref} {self.title}"

    def __str__(self) -> str:
        return self.ref


class FindingNote(BaseModel):
    """Append-only. A database trigger rejects UPDATE and DELETE (migration 0003)."""

    # technical and remediation are written by hand; verification and retest are written by lifecycle transitions.
    KINDS = [
        ("technical", "Technical (testing team only)"), ("remediation", "Remediation"),
        ("verification", "Verification"), ("retest", "Retest"),
    ]  # fmt: skip
    MANUAL_KINDS = ("technical", "remediation")

    finding = models.ForeignKey(Finding, on_delete=models.PROTECT, related_name="notes")
    author = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    kind = models.CharField(max_length=12, choices=KINDS)
    body = models.TextField()

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["finding", "kind"], name="findingnote_finding_kind")]

    @property
    def visibility(self) -> str:
        return "team" if self.kind == "technical" else "all"


class FindingTemplate(BaseModel):
    """Reusable finding text. Platform level: templates.view reads, templates.manage writes."""

    name = models.CharField(max_length=160, unique=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    recommendation = models.TextField(blank=True)
    severity = models.CharField(max_length=8, choices=SEVERITIES, blank=True)
    cvss_vector = models.CharField(max_length=200, blank=True)
    cwe = models.ForeignKey(CWE, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    references = models.JSONField(default=list, blank=True)
    created_by = models.ForeignKey("accounts.User", null=True, on_delete=models.PROTECT, related_name="+")
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["name"]

    def audit_label(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name


class RemediationActivity(BaseModel):
    """User-facing remediation timeline. The audit log stays the tamper-evident record."""

    ACTIONS = [
        ("published", "Published"), ("started", "Started"), ("paused", "Paused"), ("fix_deployed", "Fix deployed"),
        ("mitigated", "Mitigated"), ("submitted_for_verification", "Submitted for verification"),
        ("verification_passed", "Verification passed"), ("verification_failed", "Verification failed"),
        ("closed", "Closed"), ("reopened", "Reopened"), ("risk_accepted", "Risk accepted"),
        ("false_positive", "Marked false positive"), ("duplicate", "Marked duplicate"), ("comment", "Comment"),
        ("retest_requested", "Retest requested"), ("sla_breached", "SLA breached"),
    ]  # fmt: skip

    finding = models.ForeignKey(Finding, on_delete=models.PROTECT, related_name="activities")
    actor = models.ForeignKey("accounts.User", null=True, on_delete=models.PROTECT, related_name="+")
    action = models.CharField(max_length=32, choices=ACTIONS)
    note = models.TextField(blank=True)
    evidence_ids = models.JSONField(default=list, blank=True)
    from_status = models.CharField(max_length=24, blank=True)
    to_status = models.CharField(max_length=24, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["finding", "created_at"], name="activity_finding_time")]


class RetestRound(BaseModel):
    """A batch of findings in pending verification, assigned to one assessor."""

    STATUSES = [("queued", "Queued"), ("in_progress", "In progress"), ("completed", "Completed"),
                ("cancelled", "Cancelled")]  # fmt: skip
    ACTIVE = ("queued", "in_progress")

    engagement = models.ForeignKey("engagements.Engagement", on_delete=models.PROTECT, related_name="retest_rounds")
    number = models.PositiveIntegerField()
    requested_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    assessor = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=12, choices=STATUSES, default="queued")
    note = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)  # set on completion or cancellation
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["engagement", "number"], name="retest_round_number")]
        indexes = [models.Index(fields=["engagement", "status"], name="retest_round_eng_status")]

    @property
    def ref(self) -> str:
        return f"{self.engagement.ref}-R{self.number}"

    def audit_label(self) -> str:
        return self.ref

    def __str__(self) -> str:
        return self.ref


class RetestItem(BaseModel):
    RESULTS = [("pending", "Pending"), ("passed", "Passed"), ("failed", "Failed"), ("not_tested", "Not tested")]

    round = models.ForeignKey(RetestRound, on_delete=models.PROTECT, related_name="items")
    finding = models.ForeignKey(Finding, on_delete=models.PROTECT, related_name="retest_items")
    result = models.CharField(max_length=12, choices=RESULTS, default="pending")
    note = models.TextField(blank=True)
    evidence_ids = models.JSONField(default=list, blank=True)
    tested_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    tested_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [models.UniqueConstraint(fields=["round", "finding"], name="retest_item_once_per_round")]
        indexes = [models.Index(fields=["finding", "result"], name="retest_item_finding_result")]
