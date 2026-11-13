import sys

from django.core.management.base import BaseCommand

from apps.audit.service import verify_chain


class Command(BaseCommand):
    help = "Verify the audit hash chain. Exit code 1 if tampering is detected."

    def handle(self, *args, **options):
        result = verify_chain()
        if result.ok:
            self.stdout.write(f"audit chain OK ({result.checked} events)")
            return
        self.stderr.write(
            f"AUDIT CHAIN BROKEN at event {result.first_bad_id}: {result.reason} "
            f"({result.checked} events verified before the break)"
        )
        sys.exit(1)
