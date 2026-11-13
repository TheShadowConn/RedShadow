import pytest
from django.core.management import CommandError, call_command

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from tests.conftest import make_user


@pytest.mark.django_db
class TestBootstrapAdmin:
    def test_creates_super_admin_with_generated_password_once(self, capsys, monkeypatch):
        monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", "Boss@Example.com")
        monkeypatch.delenv("BOOTSTRAP_ADMIN_PASSWORD_FILE", raising=False)
        call_command("bootstrap_admin")
        out = capsys.readouterr().out
        user = User.objects.get(email="boss@example.com")
        assert user.role.system_key == "super_admin" and user.must_change_password
        password = [line.split("password:")[1].strip() for line in out.splitlines() if "password:" in line][0]
        assert user.check_password(password)
        event = AuditEvent.objects.get(action="user.bootstrap")
        assert password not in str(event.metadata)

    def test_idempotent(self, capsys, admin):
        call_command("bootstrap_admin")
        assert User.objects.filter(role__system_key="super_admin").count() == 1
        assert "nothing to do" in capsys.readouterr().out

    def test_password_from_file_is_not_printed(self, capsys, tmp_path, monkeypatch):
        f = tmp_path / "pw"
        f.write_text("Filed-Secret-Passphrase-42\n")
        monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD_FILE", str(f))
        monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", "filed@example.com")
        call_command("bootstrap_admin")
        assert "Filed-Secret" not in capsys.readouterr().out
        assert User.objects.get(email="filed@example.com").check_password("Filed-Secret-Passphrase-42")

    def test_weak_file_password_rejected(self, tmp_path, monkeypatch):
        f = tmp_path / "pw"
        f.write_text("password1234\n")
        monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD_FILE", str(f))
        with pytest.raises(CommandError):
            call_command("bootstrap_admin")
        assert not User.objects.filter(role__system_key="super_admin").exists()

    def test_other_users_do_not_count_as_admin(self, capsys, monkeypatch):
        make_user("pen@example.com", "pentester")
        monkeypatch.delenv("BOOTSTRAP_ADMIN_PASSWORD_FILE", raising=False)
        call_command("bootstrap_admin")
        assert User.objects.filter(role__system_key="super_admin").count() == 1
