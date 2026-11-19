"""Hourly SLA and risk-acceptance sweeps. Each finding is handled in its own transaction and both
tasks are idempotent, so a crashed or repeated run is harmless."""

import datetime
import logging

from celery import shared_task
from django.utils import timezone

from . import lifecycle, services
from .models import Finding

log = logging.getLogger(__name__)


def _sweep(queryset, handler) -> int:
    done = 0
    for finding in queryset.select_related("engagement").iterator():
        try:
            done += bool(handler(finding))
        except Exception:  # one bad finding must not stop the sweep
            log.exception("sweep failed for finding %s", finding.pk)
    return done


@shared_task(name="findings.sla_sweep")
def sla_sweep() -> int:
    """Record the first SLA breach of each finding (audit event and timeline entry, once)."""
    due = Finding.objects.filter(
        status__in=lifecycle.OVERDUE_STATUSES, due_date__lt=timezone.localdate(), sla_breached_at__isnull=True,
        engagement__archived_at__isnull=True,
    )  # fmt: skip
    return _sweep(due, services.system_flag_sla_breach)


@shared_task(name="findings.due_soon_sweep")
def due_soon_sweep() -> int:
    """Notify the people on findings due within the next 3 days (once per finding and due date)."""
    today = timezone.localdate()
    soon = Finding.objects.filter(
        status__in=lifecycle.OVERDUE_STATUSES, due_date__gte=today,
        due_date__lte=today + datetime.timedelta(days=services.DUE_SOON_DAYS), engagement__archived_at__isnull=True,
    )  # fmt: skip
    return _sweep(soon, services.system_notify_due_soon)


@shared_task(name="findings.expire_risk_acceptance")
def expire_risk_acceptance() -> int:
    """Reopen findings whose risk acceptance has run out."""
    expired = Finding.objects.filter(
        status="risk_accepted", risk_accepted_until__lt=timezone.localdate(), engagement__archived_at__isnull=True
    )  # fmt: skip
    return _sweep(expired, services.system_reopen_expired_risk)
