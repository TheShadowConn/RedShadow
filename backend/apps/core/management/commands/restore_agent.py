import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from apps.core import restore_jobs


class Command(BaseCommand):
    help = "Maintenance service: waits for a restore request and carries it out."

    def handle(self, *args, **options):
        # A restore interrupted by a restart did not commit.
        if restore_jobs.status()["state"] == "running":
            restore_jobs.set_status("failed", "The restore was interrupted and nothing was changed. Try again.")
        while True:
            close_old_connections()
            restore_jobs.run_pending()
            time.sleep(2)
