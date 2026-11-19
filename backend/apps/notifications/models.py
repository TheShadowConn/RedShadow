from django.db import models

from apps.core.models import BaseModel


class Notification(BaseModel):
    """One message for one user. Created inside the same transaction as the change it announces.

    Holds no finding content beyond the reference and a short title, so it can never reveal more than the
    recipient could already read. ``link`` is an in-app path, never an external URL."""

    recipient = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="notifications")
    actor = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    kind = models.CharField(max_length=40)
    title = models.CharField(max_length=200)
    body = models.CharField(max_length=400, blank=True)
    link = models.CharField(max_length=200, blank=True)
    engagement_id = models.UUIDField(null=True, blank=True)
    dedupe_key = models.CharField(max_length=80, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "read_at", "-created_at"], name="notif_recipient_unread")]


class NotificationPreference(BaseModel):
    """Per-user choices. ``muted`` holds group names (see services.GROUPS); email is opt-in."""

    user = models.OneToOneField("accounts.User", on_delete=models.CASCADE, related_name="notification_preference")
    muted = models.JSONField(default=list, blank=True)
    email_enabled = models.BooleanField(default=False)
