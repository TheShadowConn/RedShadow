from celery import shared_task

from . import services


@shared_task(name="reports.build", time_limit=150, soft_time_limit=120)
def build_report(job_id: str) -> None:
    services.build_job(job_id)


@shared_task(name="reports.cleanup")
def cleanup() -> dict:
    return services.cleanup()
