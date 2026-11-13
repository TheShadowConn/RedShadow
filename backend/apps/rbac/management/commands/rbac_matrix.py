import sys
from pathlib import Path

from django.core.management.base import BaseCommand

from apps.rbac.catalogue import matrix_markdown


class Command(BaseCommand):
    help = "Print the RBAC permission matrix as Markdown, or --check a file against the catalogue."

    def add_arguments(self, parser):
        parser.add_argument("--check", metavar="FILE", help="Exit 1 if FILE differs from the catalogue.")

    def handle(self, *args, **options):
        generated = matrix_markdown()
        if options["check"]:
            if Path(options["check"]).read_text(encoding="utf-8") != generated:
                self.stderr.write("RBAC matrix doc is out of date: run `manage.py rbac_matrix`.")
                sys.exit(1)
            self.stdout.write("RBAC matrix doc is up to date")
            return
        self.stdout.write(generated, ending="")
