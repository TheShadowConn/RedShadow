import os
import secrets
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User
from apps.accounts.services import normalize_email, validate_new_password
from apps.audit import service as audit
from apps.rbac.models import Role


class Command(BaseCommand):
    help = (
        "Create the first Super Admin when none exists. Idempotent. Password comes from "
        "BOOTSTRAP_ADMIN_PASSWORD_FILE if set, otherwise it is generated and printed once."
    )

    def handle(self, *args, **options):
        if User.objects.filter(role__system_key="super_admin").exists():
            self.stdout.write("bootstrap_admin: a Super Admin already exists, nothing to do")
            return
        email = normalize_email(os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "admin@redshadow.local"))
        pw_file = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD_FILE")
        generated = not (pw_file and Path(pw_file).is_file())
        password = secrets.token_urlsafe(18) if generated else Path(pw_file).read_text().strip()
        try:
            validate_new_password(password)
        except Exception as exc:
            raise CommandError(f"Bootstrap password rejected by the password policy: {exc}") from exc
        role = Role.objects.get(system_key="super_admin")
        with transaction.atomic():
            user = User(email=email, display_name="Administrator", role=role, must_change_password=True)
            user.set_password(password)
            user.save()
            audit.record("user.bootstrap", entity=user, actor_label="system",
                         metadata={"password_source": "generated" if generated else "file"})  # fmt: skip
        self.stdout.write(f"bootstrap_admin: created Super Admin {email}")
        if generated:
            self.stdout.write("=" * 64)
            self.stdout.write("FIRST LOGIN (shown once, change it at first sign-in):")
            self.stdout.write(f"  email:    {email}")
            self.stdout.write(f"  password: {password}")
            self.stdout.write("=" * 64)
