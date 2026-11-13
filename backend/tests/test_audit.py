import pytest
from django.core.management import call_command
from django.db import DatabaseError, connection, transaction

from apps.audit import service as audit
from apps.audit.models import GENESIS_HASH, AuditEvent
from apps.audit.redact import redact
from tests.conftest import make_user


def make_events(n=4):
    return [audit.record(f"test.event{i}", actor_label="tester", metadata={"i": i}) for i in range(n)]


@pytest.mark.django_db
class TestChain:
    def test_chain_links_and_verifies(self):
        events = make_events()
        assert events[0].prev_hash == GENESIS_HASH
        assert all(b.prev_hash == a.hash for a, b in zip(events, events[1:], strict=False))
        result = audit.verify_chain()
        assert result.ok and result.checked == 4

    def test_events_survive_db_roundtrip(self, admin):
        audit.record("test.roundtrip", actor=admin, changes={"a": [1, 2]}, metadata={"nested": {"k": ["v"]}})
        assert audit.verify_chain().ok

    def test_content_tamper_detected(self):
        events = make_events()
        with connection.cursor() as cur:
            cur.execute("ALTER TABLE audit_auditevent DISABLE TRIGGER audit_auditevent_no_update_delete")
            cur.execute("UPDATE audit_auditevent SET actor_label = 'someone-else' WHERE id = %s", [events[1].id])
            cur.execute("ALTER TABLE audit_auditevent ENABLE TRIGGER audit_auditevent_no_update_delete")
        result = audit.verify_chain()
        assert not result.ok and result.first_bad_id == events[1].id

    def test_deleted_event_detected(self):
        events = make_events()
        with connection.cursor() as cur:
            cur.execute("ALTER TABLE audit_auditevent DISABLE TRIGGER audit_auditevent_no_update_delete")
            cur.execute("DELETE FROM audit_auditevent WHERE id = %s", [events[1].id])
            cur.execute("ALTER TABLE audit_auditevent ENABLE TRIGGER audit_auditevent_no_update_delete")
        result = audit.verify_chain()
        assert not result.ok and result.first_bad_id == events[2].id

    def test_verify_command_exit_code(self, capsys):
        make_events(2)
        call_command("verify_audit")
        events = list(AuditEvent.objects.all())
        with connection.cursor() as cur:
            cur.execute("ALTER TABLE audit_auditevent DISABLE TRIGGER audit_auditevent_no_update_delete")
            cur.execute("UPDATE audit_auditevent SET outcome = 'failure' WHERE id = %s", [events[0].id])
            cur.execute("ALTER TABLE audit_auditevent ENABLE TRIGGER audit_auditevent_no_update_delete")
        with pytest.raises(SystemExit) as exc:
            call_command("verify_audit")
        assert exc.value.code == 1


@pytest.mark.django_db
class TestImmutability:
    def test_update_blocked_by_database(self):
        make_events(1)
        with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
            AuditEvent.objects.update(action="hacked")

    def test_delete_blocked_by_database(self):
        make_events(1)
        with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
            AuditEvent.objects.all().delete()

    def test_truncate_blocked_by_database(self):
        with pytest.raises(DatabaseError, match="append-only"), transaction.atomic(), connection.cursor() as cur:
            cur.execute("TRUNCATE audit_auditevent")

    def test_runtime_role_lacks_update_delete_truncate(self):
        with connection.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = 'redshadow_app'")
            if cur.fetchone() is None:
                pytest.skip("redshadow_app role not present")
            for priv in ("UPDATE", "DELETE", "TRUNCATE"):
                cur.execute("SELECT has_table_privilege('redshadow_app', 'audit_auditevent', %s)", [priv])
                assert cur.fetchone()[0] is False, priv


@pytest.mark.django_db
class TestRecording:
    def test_redaction(self):
        e = audit.record(
            "test.secret",
            changes={"password": ["old", "new"], "ok": 1},
            metadata={"api_token": "abc", "mfa_enabled": True},
        )
        e.refresh_from_db()
        assert "old" not in str(e.changes) and "abc" not in str(e.metadata)
        assert e.changes["ok"] == 1 and e.metadata["mfa_enabled"] is True
        assert redact({"nested": {"secret": "x"}})["nested"]["secret"] == "[REDACTED]"

    def test_same_transaction_rollback_leaves_no_event(self):
        before = AuditEvent.objects.count()
        with pytest.raises(RuntimeError), transaction.atomic():
            audit.record("test.rolled_back")
            raise RuntimeError("boom")
        assert AuditEvent.objects.count() == before

    def test_request_context_captured(self, admin, rf):
        request = rf.get("/x", HTTP_X_FORWARDED_FOR="10.1.2.3", HTTP_USER_AGENT="pytest-agent" * 40)
        request.user = admin
        e = audit.record("test.ctx", request=request)
        assert e.actor_id == admin.pk and e.actor_label == admin.email
        assert e.actor_ip == "10.1.2.3" and len(e.user_agent) == 255

    def test_invalid_ip_is_dropped_not_crashed(self, rf):
        request = rf.get("/x", HTTP_X_FORWARDED_FOR="not-an-ip")
        assert audit.record("test.badip", request=request).actor_ip is None

    def test_auth_and_admin_events_form_valid_chain(self, admin_client, pentester):
        admin_client.post(f"/api/v1/users/{pentester.pk}/reset-password")
        admin_client.post(f"/api/v1/users/{admin_client.get('/api/v1/auth/me').json()['id']}/deactivate")
        make_user("x@example.com", "pentester")
        assert AuditEvent.objects.count() >= 3
        assert audit.verify_chain().ok
