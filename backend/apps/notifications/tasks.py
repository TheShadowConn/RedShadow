"""Housekeeping for notifications."""

from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from .models import Notification

RETENTION_DAYS = 90


@shared_task(name="notifications.prune")
def prune() -> int:
    """Delete read notifications older than the retention period. Unread ones are kept."""
    cutoff = timezone.now() - timedelta(days=RETENTION_DAYS)
    deleted, _ = Notification.objects.filter(read_at__isnull=False, created_at__lt=cutoff).delete()
    return deleted
