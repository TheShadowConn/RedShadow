from django.core.management.base import BaseCommand

from apps.audit import service as audit


class Command(BaseCommand):
    help = (
        "Record that a backup finished (called by scripts/backup.sh). The About page shows the newest one to Super "
        "Admins so a missing or old backup is noticed. Writes one audit event, nothing else."
    )

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True, help="Backup folder name, e.g. 20261126-140500")
        parser.add_argument("--bytes", type=int, default=0, help="Total size of the backup folder")
        parser.add_argument("--parts", default="db,media,secrets", help="What the backup holds")

    def handle(self, *args, **options):
        audit.record(
            "system.backup_completed",
            actor_label="system",
            entity_type="backup",
            entity_label=options["name"][:80],
            metadata={"name": options["name"][:80], "size_bytes": max(options["bytes"], 0),
                      "parts": options["parts"][:80]},
        )  # fmt: skip
        self.stdout.write(f"record_backup: recorded backup {options['name']}")
