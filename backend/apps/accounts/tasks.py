from celery import shared_task
from django.core.management import call_command


@shared_task(name="accounts.cleanup_sessions")
def cleanup_sessions() -> None:
    """Delete expired server-side sessions."""
    call_command("clearsessions")
