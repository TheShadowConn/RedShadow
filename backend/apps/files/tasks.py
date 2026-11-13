from celery import shared_task

from . import services


@shared_task(name="files.purge_deleted")
def purge_deleted() -> int:
    return services.purge_deleted()
