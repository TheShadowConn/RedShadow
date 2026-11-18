from django.db import models

from apps.core.models import BaseModel


class ImportMapping(BaseModel):
    """A column mapping a user saved to reuse on the next file."""

    name = models.CharField(max_length=120)
    owner = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="+")
    column_map = models.JSONField(default=dict)  # {field: header}
    value_map = models.JSONField(default=dict)  # {"severity": {"raw text": "critical"}}

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["owner", "name"], name="uniq_import_mapping_name")]


class ImportJob(BaseModel):
    """One uploaded CSV. A ``findings`` job goes into one engagement and creates draft findings.
    An ``assets`` job goes into one organisation and creates assets that are not onboarded yet.

    A corrected file can be uploaded into the same job again: that starts a new ``attempt``. Rows and
    attempt records of earlier attempts stay as history."""

    KINDS = [("findings", "Findings"), ("assets", "Assets")]

    STATUSES = [
        ("uploaded", "Uploaded"),
        ("parsing", "Reading file"),
        ("parsed", "Ready to map"),
        ("validating", "Checking rows"),
        ("previewed", "Ready to import"),
        ("importing", "Importing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    ]
    WORKING = ("parsing", "validating", "importing")
    FINISHED = ("completed", "failed", "cancelled")
    MODES = [("all_or_nothing", "All or nothing"), ("valid_rows_only", "Valid rows only")]
    DUPLICATES = [("skip", "Skip duplicates"), ("import", "Import duplicates anyway")]

    kind = models.CharField(max_length=10, choices=KINDS, default="findings")
    engagement = models.ForeignKey(
        "engagements.Engagement", null=True, blank=True, on_delete=models.PROTECT, related_name="import_jobs"
    )
    organisation = models.ForeignKey(
        "organisations.Organisation", null=True, blank=True, on_delete=models.PROTECT, related_name="import_jobs"
    )
    attempt = models.PositiveIntegerField(default=1)
    uploaded_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    original_name = models.CharField(max_length=255)
    storage_key = models.CharField(max_length=80, blank=True)
    file_sha256 = models.CharField(max_length=64)
    file_size = models.PositiveIntegerField()
    file_purged_at = models.DateTimeField(null=True, blank=True)
    encoding = models.CharField(max_length=16, blank=True)
    delimiter = models.CharField(max_length=2, blank=True)
    headers = models.JSONField(default=list)
    sample = models.JSONField(default=list)  # first rows as lists of cells
    status = models.CharField(max_length=12, choices=STATUSES, default="uploaded")
    mapping = models.JSONField(default=dict)  # {"column_map": {...}, "value_map": {...}}
    mode = models.CharField(max_length=16, choices=MODES, blank=True)
    duplicates = models.CharField(max_length=8, choices=DUPLICATES, default="skip")
    counts = models.JSONField(default=dict)  # total, valid, invalid, duplicate, imported, skipped
    error = models.CharField(max_length=300, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["engagement", "status"], name="importjob_eng_status"),
            models.Index(fields=["organisation", "status"], name="importjob_org_status"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(kind="findings", engagement__isnull=False, organisation__isnull=True)
                    | models.Q(kind="assets", organisation__isnull=False, engagement__isnull=True)
                ),
                name="importjob_target_matches_kind",
            )
        ]

    @property
    def target_label(self) -> str:
        return self.engagement.ref if self.engagement_id else self.organisation.name

    @property
    def rows_now(self):
        """Rows of the current attempt."""
        return self.rows.filter(attempt=self.attempt)

    def audit_label(self) -> str:
        return f"{self.original_name} into {self.target_label}"

    def __str__(self) -> str:
        return self.original_name


class ImportRow(models.Model):
    """One row of the file. Never dropped: invalid and duplicate rows stay visible for the error report."""

    STATUSES = [
        ("pending", "Pending"),
        ("valid", "Valid"),
        ("invalid", "Invalid"),
        ("duplicate", "Duplicate"),
        ("skipped", "Skipped"),
        ("imported", "Imported"),
    ]

    id = models.BigAutoField(primary_key=True)
    job = models.ForeignKey(ImportJob, on_delete=models.PROTECT, related_name="rows")
    attempt = models.PositiveIntegerField(default=1)
    row_number = models.PositiveIntegerField()  # line of the file the record ends on
    raw = models.JSONField(default=list)
    mapped = models.JSONField(default=dict)
    errors = models.JSONField(default=list)  # [{field, code, message}]
    status = models.CharField(max_length=10, choices=STATUSES, default="pending")
    duplicate_of_finding = models.UUIDField(null=True, blank=True)  # no FK: shown only if the viewer can see it
    duplicate_of_line = models.PositiveIntegerField(null=True, blank=True)
    finding_id = models.UUIDField(null=True, blank=True)
    asset_id = models.UUIDField(null=True, blank=True)  # asset created or matched by an assets import

    class Meta:
        ordering = ["row_number", "id"]
        indexes = [
            models.Index(fields=["job", "status", "row_number"], name="importrow_job_status"),
            models.Index(fields=["job", "attempt", "status"], name="importrow_job_attempt"),
        ]


class ImportAttempt(BaseModel):
    """History of one upload into a job: the file, what the check found and how it ended."""

    OUTCOMES = [
        ("in_progress", "In progress"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
        ("superseded", "Replaced by a corrected file"),
    ]

    job = models.ForeignKey(ImportJob, on_delete=models.PROTECT, related_name="attempts")
    number = models.PositiveIntegerField()
    uploaded_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    original_name = models.CharField(max_length=255)
    file_sha256 = models.CharField(max_length=64)
    file_size = models.PositiveIntegerField()
    counts = models.JSONField(default=dict)
    outcome = models.CharField(max_length=12, choices=OUTCOMES, default="in_progress")
    error = models.CharField(max_length=300, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-number"]
        constraints = [models.UniqueConstraint(fields=["job", "number"], name="uniq_import_attempt_number")]
