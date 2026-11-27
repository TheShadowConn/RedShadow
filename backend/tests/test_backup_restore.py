"""Backup file format, restore into an emptied installation, and who may use either."""

import io

import pyotp
import pytest
from cryptography.fernet import Fernet
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts import crypto
from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.audit.service import verify_chain
from apps.core import backup, restore_jobs
from apps.core.storage import get_storage
from apps.organisations.models import Asset, Organisation
from tests.conftest import PASSWORD, signed_in
from tests.test_findings import API
from tests.world import build_world

PHRASE = "correct horse battery"


@pytest.fixture(autouse=True)
def folders(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path / "media")
    settings.BACKUP_STAGING_DIR = str(tmp_path / "staging")


def bundle(phrase=PHRASE) -> bytes:
    out = io.BytesIO()
    backup.write_bundle(phrase, out)
    return out.getvalue()


def unpacked(data: bytes, tmp_path, phrase=PHRASE):
    where = tmp_path / "out"
    where.mkdir(exist_ok=True)
    return backup.unpack(io.BytesIO(data), phrase, where), where


class TestFileFormat:
    def seal(self, tmp_path, payload: bytes) -> bytes:
        source = tmp_path / "plain"
        source.write_bytes(payload)
        out = io.BytesIO()
        backup.encrypt_file(source, out, PHRASE)
        return out.getvalue()

    def open(self, data: bytes, phrase=PHRASE) -> bytes:
        out = io.BytesIO()
        backup.decrypt_file(io.BytesIO(data), out, phrase)
        return out.getvalue()

    @pytest.mark.parametrize("size", [0, 10, backup.CHUNK, backup.CHUNK * 2 + 5])
    def test_round_trip(self, tmp_path, size):
        payload = (b"abc" * size)[:size]
        sealed = self.seal(tmp_path, payload)
        assert self.open(sealed) == payload
        if size > 100:
            assert payload[:100] not in sealed

    def test_wrong_passphrase_changes_and_truncation_are_refused(self, tmp_path):
        sealed = self.seal(tmp_path, b"x" * (backup.CHUNK + 10))
        changed = bytearray(sealed)
        changed[-1] ^= 1
        first_chunk_only = sealed[: len(backup.MAGIC) + 24 + 5 + backup.CHUNK + 16]
        for data, phrase in (
            (sealed, "wrong passphrase!"),
            (bytes(changed), PHRASE),
            (sealed[:-3], PHRASE),
            (first_chunk_only, PHRASE),
            (sealed + b"x", PHRASE),
            (b"not a backup", PHRASE),
        ):
            with pytest.raises(backup.BackupError):
                self.open(data, phrase)


@pytest.mark.django_db
class TestRestore:
    def test_everything_comes_back_and_two_step_still_works(self, admin, settings, tmp_path, monkeypatch):
        build_world(admin)
        admin.mfa_secret = "JBSWY3DPEHPK3PXP"
        admin.mfa_enabled = True
        admin.save()
        key = get_storage().save(b"evidence bytes")
        before = (Organisation.objects.count(), Asset.objects.count(), User.objects.count(), AuditEvent.objects.count())
        data = bundle()

        # A different installation: its own key, no files, other rows.
        settings.MEDIA_ROOT = str(tmp_path / "new-media")
        settings.MFA_ENCRYPTION_KEY = Fernet.generate_key().decode()
        crypto._fernet.cache_clear()
        Asset.objects.filter(name="Acme shop").update(name="changed")
        monkeypatch.setattr(backup, "is_empty", lambda: True)
        try:
            manifest, where = unpacked(data, tmp_path)
            backup.load(where, manifest)
            after = (
                Organisation.objects.count(),
                Asset.objects.count(),
                User.objects.count(),
                AuditEvent.objects.count(),
            )
            assert after == before
            assert Asset.objects.filter(name="Acme shop").exists()
            assert User.objects.get(pk=admin.pk).mfa_secret == "JBSWY3DPEHPK3PXP"
            assert get_storage().read(key) == b"evidence bytes"
            assert (tmp_path / "new-media" / key).stat().st_mode & 0o044 == 0o044  # readable by nginx
            # New rows must not collide with restored ones, and the audit chain must still verify.
            Organisation.objects.create(name="After restore", slug="after-restore")
            restore_jobs.audit.record("system.restore_completed", entity_type="system", entity_label="Restore")
            assert verify_chain().ok
        finally:
            crypto._fernet.cache_clear()

    def test_refused_when_there_is_data(self, admin, tmp_path):
        build_world(admin)
        manifest, where = unpacked(bundle(), tmp_path)
        with pytest.raises(backup.BackupError, match="already holds data"):
            backup.load(where, manifest)

    def test_refused_for_another_database_layout(self, admin, tmp_path):
        manifest, where = unpacked(bundle(), tmp_path)
        manifest["migrations"] = manifest["migrations"][:-1]
        with pytest.raises(backup.BackupError, match="database layout"):
            backup.load(where, manifest)


def code_for_admin() -> str:
    """A fresh two-step code for the signed-in Super Admin (a code can be used only once)."""
    user = User.objects.get(role__system_key="super_admin")
    if not user.mfa_enabled:
        return ""
    User.objects.filter(pk=user.pk).update(mfa_last_step=0)
    return pyotp.TOTP(user.mfa_secret).now()


@pytest.mark.django_db
class TestApi:
    def test_two_step_code_is_asked_again(self, admin_client):
        r = self.post(admin_client, code="000000")
        assert r.status_code == 400 and "code" in r.json()["error"]["fields"], r.content

    def post(self, client, **extra):
        body = {"password": PASSWORD, "passphrase": PHRASE, "code": code_for_admin(), **extra}
        return client.post(f"{API}/system/backup", body, format="json")

    def test_super_admin_downloads(self, admin_client):
        r = self.post(admin_client)
        assert r.status_code == 200, r.content
        data = b"".join(r.streaming_content)
        assert data.startswith(backup.MAGIC)
        assert AuditEvent.objects.filter(action="system.backup_completed").exists()

    def test_password_and_passphrase_are_checked(self, admin_client):
        assert self.post(admin_client, password="nope").status_code == 400
        assert self.post(admin_client, passphrase="short").status_code == 400

    def test_others_are_refused(self, admin):
        w = build_world(admin)
        for user in (w.p1, w.r1):
            client = signed_in(user)
            assert self.post(client).status_code == 403
            assert client.get(f"{API}/system/overview").status_code == 403

    def test_restore_is_off_once_there_is_data(self, admin, admin_client):
        build_world(admin)
        r = admin_client.post(
            f"{API}/system/restore",
            {
                "password": PASSWORD,
                "passphrase": PHRASE,
                "code": code_for_admin(),
                "file": SimpleUploadedFile("a.rsbk", b"x"),
            },
            format="multipart",
        )
        assert r.status_code == 409, r.content

    def test_restore_is_queued_on_an_empty_installation(self, admin_client):
        data = bundle()
        for phrase, expected in (("wrong passphrase!", 400), (PHRASE, 202)):
            r = admin_client.post(
                f"{API}/system/restore",
                {
                    "password": PASSWORD,
                    "passphrase": phrase,
                    "code": code_for_admin(),
                    "file": SimpleUploadedFile("a.rsbk", data),
                },
                format="multipart",
            )
            assert r.status_code == expected, r.content
        assert restore_jobs.status()["state"] == "queued"
