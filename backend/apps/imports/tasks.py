from celery import shared_task

from . import services


@shared_task(name="imports.parse")
def parse_job(job_id: str) -> None:
    services.parse_job(job_id)


@shared_task(name="imports.validate")
def validate_job(job_id: str) -> None:
    services.validate_job(job_id)


@shared_task(name="imports.run", time_limit=900, soft_time_limit=840)
def run_import(job_id: str) -> None:
    services.run_import(job_id)


@shared_task(name="imports.cleanup")
def cleanup() -> dict:
    return services.cleanup()
