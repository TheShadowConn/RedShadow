from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel


class Attachment(BaseModel):
    """File metadata. The bytes live in core.storage under a random key, never under the name."""

    KINDS = [("document", "Engagement document"), ("logo", "Organisation logo"), ("evidence", "Finding evidence")]

    kind = models.CharField(max_length=16, choices=KINDS)
    engagement = models.ForeignKey(
        "engagements.Engagement", null=True, blank=True, on_delete=models.PROTECT, related_name="attachments"
    )
    finding = models.ForeignKey(
        "findings.Finding", null=True, blank=True, on_delete=models.PROTECT, related_name="evidence"
    )
    organisation = models.ForeignKey(
        "organisations.Organisation", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    original_name = models.CharField(max_length=120)
    storage_key = models.CharField(max_length=64, unique=True)
    mime = models.CharField(max_length=100)
    size = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)
    uploaded_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    purged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(kind="document", engagement__isnull=False, organisation__isnull=True, finding__isnull=True)
                )
                | (Q(kind="logo", engagement__isnull=True, organisation__isnull=False, finding__isnull=True))
                | (Q(kind="evidence", engagement__isnull=False, organisation__isnull=True, finding__isnull=False)),
                name="attachment_owner_matches_kind",
            )
        ]
        indexes = [
            models.Index(fields=["engagement", "deleted_at"]),
            models.Index(fields=["finding", "deleted_at"]),
        ]

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def audit_label(self) -> str:
        return self.original_name
