from django.db import models

GENESIS_HASH = "0" * 64


class AuditEvent(models.Model):
    """Append-only, hash-chained audit record.

    No foreign keys on purpose: events must survive deletion of anything they describe.
    The database enforces append-only (trigger + revoked privileges, see migration 0002).
    """

    OUTCOMES = [("success", "Success"), ("denied", "Denied"), ("failure", "Failure")]

    id = models.BigAutoField(primary_key=True)
    occurred_at = models.DateTimeField()
    actor_id = models.UUIDField(null=True, blank=True)
    actor_label = models.CharField(max_length=254, blank=True)
    actor_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    request_id = models.CharField(max_length=64, blank=True)
    action = models.CharField(max_length=80, db_index=True)
    entity_type = models.CharField(max_length=60, blank=True)
    entity_id = models.CharField(max_length=64, blank=True)
    entity_label = models.CharField(max_length=255, blank=True)
    engagement_id = models.UUIDField(null=True, blank=True)
    engagement_ref = models.CharField(max_length=40, blank=True)
    changes = models.JSONField(default=dict)
    metadata = models.JSONField(default=dict)
    outcome = models.CharField(max_length=10, choices=OUTCOMES, default="success")
    prev_hash = models.CharField(max_length=64)
    hash = models.CharField(max_length=64)

    class Meta:
        ordering = ["id"]
        indexes = [
            models.Index(fields=["entity_type", "entity_id"]),
            models.Index(fields=["actor_id"]),
            models.Index(fields=["engagement_id"]),
            models.Index(fields=["occurred_at"]),
        ]


class IntegrityCheck(models.Model):
    """One run of the hash-chain verification (manual or nightly). Mutable status row, not part of the chain."""

    STATUSES = [("running", "Running"), ("ok", "Intact"), ("failed", "Broken"), ("error", "Error")]

    id = models.BigAutoField(primary_key=True)
    status = models.CharField(max_length=10, choices=STATUSES, default="running")
    trigger = models.CharField(max_length=10, default="manual")  # manual | nightly
    requested_by_label = models.CharField(max_length=254, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    checked = models.PositiveBigIntegerField(default=0)
    first_bad_id = models.BigIntegerField(null=True, blank=True)
    reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-id"]
