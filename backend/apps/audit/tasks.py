from celery import shared_task
from django.utils import timezone

from . import service
from .models import IntegrityCheck


def run_check(check: IntegrityCheck) -> IntegrityCheck:
    """Verify the chain and store the outcome. A broken chain is itself written to the (still appendable) log,
    once per distinct break, so a nightly run does not repeat the same alarm."""
    previous = IntegrityCheck.objects.filter(pk__lt=check.pk, status__in=["ok", "failed"]).first()
    try:
        result = service.verify_chain()
    except Exception as exc:  # the check itself failed to run; keep the reason, never report "ok"
        check.status, check.reason = "error", f"{type(exc).__name__}: {exc}"[:255]
        check.finished_at = timezone.now()
        check.save()
        return check
    check.checked, check.finished_at = result.checked, timezone.now()
    if result.ok:
        check.status = "ok"
    else:
        check.status, check.first_bad_id, check.reason = "failed", result.first_bad_id, result.reason[:255]
    check.save()
    repeat = previous is not None and previous.status == "failed" and previous.first_bad_id == result.first_bad_id
    if not result.ok and not repeat:
        service.record(
            "audit.integrity_failed", actor_label="system", entity_type="auditevent",
            entity_id=str(result.first_bad_id), entity_label="Audit chain",
            metadata={"first_bad_id": result.first_bad_id, "reason": result.reason, "checked": result.checked},
            outcome="failure",
        )  # fmt: skip
    return check


@shared_task(name="audit.verify_integrity")
def verify_integrity(check_id: int | None = None, trigger: str = "nightly") -> str:
    check = IntegrityCheck.objects.filter(pk=check_id, status="running").first() if check_id else None
    if check is None:
        check = IntegrityCheck.objects.create(trigger=trigger)
    return run_check(check).status
