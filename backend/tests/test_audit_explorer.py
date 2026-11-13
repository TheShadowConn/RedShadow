"""Phase 6A: audit explorer scoping, filters, integrity runs and CSV export."""

import csv
import hashlib
import io

import pytest
from django.db import connection

from apps.audit import export as audit_export
from apps.audit import service as audit
from apps.audit import tasks
from apps.audit.models import AuditEvent, IntegrityCheck
from apps.engagements.models import EngagementMembership
from tests.conftest import make_role, make_user, signed_in
from tests.test_findings import API, furl, make, publish
from tests.test_findings_extras import up
from tests.world import build_world

EV = f"{API}/audit/events"


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)


@pytest.fixture
def w(admin):
    return build_world(admin)


@pytest.fixture
def p1c(w):
    return signed_in(w.p1)


@pytest.fixture
def r1c(w):
    return signed_in(w.r1)


def rows(client, query=""):
    r = client.get(f"{EV}{query}")
    assert r.status_code == 200, r.content
    return r.json()["results"]


def actions(client, query=""):
    return [e["action"] for e in rows(client, query)]


def tamper(sql, params=()):
    with connection.cursor() as cur:
        cur.execute("ALTER TABLE audit_auditevent DISABLE TRIGGER audit_auditevent_no_update_delete")
        cur.execute(sql, params)
        cur.execute("ALTER TABLE audit_auditevent ENABLE TRIGGER audit_auditevent_no_update_delete")


@pytest.mark.django_db
class TestScope:
    def test_admin_sees_everything_including_platform_events(self, w, admin_client, p1c):
        audit.record("test.platform_event", actor_label="system")
        got = rows(admin_client, "?page_size=200")
        assert any(e["action"] == "test.platform_event" and e["engagement"] is None for e in got)
        assert {e["engagement"]["ref"] for e in got if e["engagement"]} >= {w.eng_a.ref, w.eng_b.ref}

    def test_pentester_sees_only_own_engagement_and_no_platform_events(self, w, p1c):
        audit.record("test.platform_event", actor_label="system")
        make(p1c, w.eng_a, title="In A")
        got = rows(p1c, "?page_size=200")
        refs = {e["engagement"]["ref"] for e in got if e["engagement"]}
        assert refs == {w.eng_a.ref}
        assert all(e["engagement"] for e in got)  # nothing without an engagement
        assert "finding.created" in [e["action"] for e in got]

    def test_other_engagement_pentester_sees_nothing_of_a(self, w, p1c):
        make(p1c, w.eng_a, title="Only in A")
        got = rows(signed_in(w.p2), "?page_size=200")
        assert all(e["engagement"]["ref"] == w.eng_b.ref for e in got)

    def test_detail_is_scoped(self, w, p1c, admin_client):
        make(p1c, w.eng_a)
        other = AuditEvent.objects.filter(engagement_id=w.eng_b.pk).first()
        mine = AuditEvent.objects.filter(engagement_id=w.eng_a.pk).first()
        assert p1c.get(f"{EV}/{other.id}").status_code == 404
        assert p1c.get(f"{EV}/{mine.id}").status_code == 200
        platform = audit.record("test.platform_event", actor_label="system")
        assert p1c.get(f"{EV}/{platform.id}").status_code == 404
        assert admin_client.get(f"{EV}/{platform.id}").status_code == 200

    def test_ip_agent_and_hashes_are_admin_only(self, w, p1c, admin_client):
        make(p1c, w.eng_a)
        mine = rows(p1c)[0]
        assert not {"actor_ip", "user_agent", "hash", "prev_hash"} & set(mine)
        assert {"actor_ip", "user_agent", "hash", "prev_hash"} <= set(rows(admin_client)[0])

    def test_remediation_never_sees_drafts_or_foreign_findings(self, w, p1c, r1c):
        secret = make(p1c, w.eng_a, title="Secret draft title")
        mine = publish(p1c, make(p1c, w.eng_a, title="Assigned finding"))
        p1c.patch(furl(mine), {"version": mine["version"], "remediation_owner": str(w.r1.pk)}, format="json")
        other = publish(p1c, make(p1c, w.eng_a, title="Unassigned published"))
        p1c.post(furl(mine, "/notes"), {"kind": "technical", "body": "internal only"}, format="json")
        got = rows(r1c, "?page_size=200")
        labels = " ".join(e["entity_label"] for e in got)
        assert "Secret draft title" not in labels and "Unassigned published" not in labels
        assert "Assigned finding" in labels
        assert not [e for e in got if e["action"] == "finding.technical_note_added"]
        mine_actions = [e["action"] for e in got if e["entity_id"] == mine["id"]]
        assert "finding.published" in mine_actions and "finding.created" not in mine_actions  # starts at publish
        assert secret["id"] not in {e["entity_id"] for e in got} and other["id"] not in {e["entity_id"] for e in got}

    def test_remediation_does_not_see_evidence_events(self, w, p1c, r1c, admin_client):
        f = publish(p1c, make(p1c, w.eng_a, title="With evidence"))
        p1c.patch(furl(f), {"version": f["version"], "remediation_owner": str(w.r1.pk)}, format="json")
        assert up(p1c, f, name="secret-screenshot.png").status_code == 201
        assert [e for e in rows(p1c, "?entity_type=attachment") if e["metadata"].get("kind") == "evidence"]
        got = rows(r1c, "?page_size=200")
        assert "secret-screenshot.png" not in str(got)
        assert not [e for e in got if e["metadata"].get("kind") == "evidence"]

    def test_user_without_audit_permissions_is_refused(self, w):
        nobody = make_user("nobody@example.com", make_role("Nobody", ["engagements.view"]))
        assert signed_in(nobody).get(EV).status_code == 403

    def test_facets_only_list_visible_things(self, w, p1c, admin_client):
        make(p1c, w.eng_a)
        signed_in(w.p2).get(f"{API}/engagements")  # a request by someone else changes nothing here
        facets = p1c.get(f"{API}/audit/facets").json()
        assert [e["ref"] for e in facets["engagements"]] == [w.eng_a.ref]
        assert "finding.created" in facets["actions"] and "auth.login" not in facets["actions"]
        assert "finding" in facets["entity_types"]
        assert str(w.p2.pk) not in {a["id"] for a in facets["actors"]}
        admin_facets = admin_client.get(f"{API}/audit/facets").json()
        assert len(admin_facets["engagements"]) == 2


@pytest.mark.django_db
class TestFilters:
    def test_action_exact_prefix_and_list(self, w, p1c):
        f = publish(p1c, make(p1c, w.eng_a))
        assert set(actions(p1c, "?action=finding.published")) == {"finding.published"}
        pref = set(actions(p1c, "?action=finding.*&page_size=200"))
        assert {"finding.created", "finding.published"} <= pref
        both = set(actions(p1c, "?action=finding.created,finding.published"))
        assert both == {"finding.created", "finding.published"}
        assert f["id"]

    def test_entity_actor_engagement_and_request_filters(self, w, p1c, admin_client):
        f = publish(p1c, make(p1c, w.eng_a))
        by_entity = rows(p1c, f"?entity_type=finding&entity_id={f['id']}")
        assert by_entity and all(e["entity_id"] == f["id"] for e in by_entity)
        assert all(e["actor_id"] == str(w.p1.pk) for e in rows(p1c, f"?actor={w.p1.pk}&entity_type=finding"))
        assert rows(admin_client, f"?engagement={w.eng_b.pk}&entity_type=finding") == []
        rid = by_entity[0]["request_id"]
        if rid:
            assert all(e["request_id"] == rid for e in rows(p1c, f"?request_id={rid}"))

    def test_outcome_filter_finds_denials(self, w, p1c, r1c):
        f = publish(p1c, make(p1c, w.eng_a))
        p1c.patch(furl(f), {"version": f["version"], "remediation_owner": str(w.r1.pk)}, format="json")
        r1c.post(furl(f, "/transition"), {"to": "closed", "version": 3, "note": "not allowed here"}, format="json")
        denied = rows(p1c, "?outcome=denied")
        assert denied and all(e["outcome"] == "denied" for e in denied)
        assert any(e["action"] == "finding.closed_denied" for e in denied)

    def test_date_range(self, w, p1c):
        make(p1c, w.eng_a)
        today = AuditEvent.objects.filter(engagement_id=w.eng_a.pk).first().occurred_at.date().isoformat()
        assert rows(p1c, f"?from={today}&to={today}")
        assert rows(p1c, "?to=2000-01-01") == []
        assert rows(p1c, "?from=2999-01-01") == []

    @pytest.mark.parametrize(
        "query", ["?from=yesterday", "?to=31-12-2026", "?actor=nope", "?engagement=x", "?before=abc"]
    )
    def test_bad_values_are_400(self, w, p1c, query):
        assert p1c.get(f"{EV}{query}").status_code == 400

    def test_keyset_paging_walks_everything_once(self, w, p1c):
        for i in range(5):
            make(p1c, w.eng_a, title=f"Finding {i}")
        seen, cursor = [], ""
        while True:
            body = p1c.get(f"{EV}?page_size=3{cursor}").json()
            seen += [e["id"] for e in body["results"]]
            if not body["has_more"]:
                break
            cursor = f"&before={body['next_before']}"
        total = AuditEvent.objects.filter(engagement_id=w.eng_a.pk).count()
        assert len(seen) == len(set(seen)) == total and seen == sorted(seen, reverse=True)


@pytest.mark.django_db
class TestIntegrity:
    def test_verify_reports_intact_chain(self, w, admin_client):
        r = admin_client.post(f"{API}/audit/verify", {}, format="json")
        assert r.status_code == 202
        got = admin_client.get(f"{API}/audit/integrity").json()
        assert got["broken"] is False and got["last_finished"]["status"] == "ok" and got["last_finished"]["checked"] > 0
        assert AuditEvent.objects.filter(action="audit.verify_requested").exists()

    def test_tamper_turns_status_broken_and_is_logged_once(self, w, admin_client, p1c):
        make(p1c, w.eng_a)
        victim = AuditEvent.objects.filter(action="finding.created").first()
        tamper("UPDATE audit_auditevent SET actor_label = 'someone-else' WHERE id = %s", [victim.id])
        admin_client.post(f"{API}/audit/verify", {}, format="json")
        got = admin_client.get(f"{API}/audit/integrity").json()
        assert got["broken"] is True and got["last_finished"]["first_bad_id"] == victim.id
        assert AuditEvent.objects.filter(action="audit.integrity_failed").count() == 1
        admin_client.post(f"{API}/audit/verify", {}, format="json")
        assert AuditEvent.objects.filter(action="audit.integrity_failed").count() == 1  # same break, no new alarm

    def test_a_recent_unfinished_run_is_reused(self, w, admin_client):
        running = IntegrityCheck.objects.create(trigger="manual")
        r = admin_client.post(f"{API}/audit/verify", {}, format="json")
        assert r.status_code == 202 and r.json()["id"] == running.id
        assert IntegrityCheck.objects.count() == 1

    def test_stale_run_is_closed_as_error(self, w, admin_client):
        stale = IntegrityCheck.objects.create(trigger="manual")
        IntegrityCheck.objects.filter(pk=stale.pk).update(started_at="2000-01-01T00:00:00Z")
        admin_client.post(f"{API}/audit/verify", {}, format="json")
        stale.refresh_from_db()
        assert stale.status == "error"

    def test_nightly_task_runs_and_records(self, w):
        assert tasks.verify_integrity() == "ok"
        assert IntegrityCheck.objects.first().trigger == "nightly"

    def test_check_that_cannot_run_is_never_reported_ok(self, w, monkeypatch):
        monkeypatch.setattr(tasks.service, "verify_chain", lambda: (_ for _ in ()).throw(RuntimeError("db down")))
        assert tasks.verify_integrity() == "error"
        assert IntegrityCheck.objects.first().reason.startswith("RuntimeError")

    def test_only_super_admin(self, w, p1c, r1c):
        for c in (p1c, r1c):
            assert c.post(f"{API}/audit/verify", {}, format="json").status_code == 403
            assert c.get(f"{API}/audit/integrity").status_code == 403

    def test_tasks_are_scheduled_nightly(self):
        from django.conf import settings

        names = {v["task"]: v["schedule"] for v in settings.CELERY_BEAT_SCHEDULE.values()}
        assert names["audit.verify_integrity"] == 86400.0


@pytest.mark.django_db
class TestExport:
    def get(self, client, query=""):
        r = client.get(f"{API}/audit/export{query}")
        assert r.status_code == 200, r.content
        return r, b"".join(r.streaming_content)

    def test_csv_matches_filters_and_is_hashed_in_the_log(self, w, admin_client, p1c):
        make(p1c, w.eng_a, title="Exported finding")
        r, body = self.get(admin_client, "?action=finding.created")
        assert r["Content-Type"].startswith("text/csv") and "attachment" in r["Content-Disposition"]
        assert r["Cache-Control"] == "no-store"
        table = list(csv.reader(io.StringIO(body.decode())))
        assert table[0] == audit_export.COLUMNS and len(table) == 2 and table[1][4] == "finding.created"
        ev = AuditEvent.objects.filter(action="audit.exported").first()
        assert ev.metadata["sha256"] == hashlib.sha256(body).hexdigest() and ev.metadata["rows"] == 1
        assert ev.metadata["filters"] == {"action": "finding.created"}

    def test_formula_cells_are_neutralised(self, w, admin_client):
        audit.record("test.formula", actor_label="=cmd|' /C calc'!A0", entity_label="+SUM(1)")
        _, body = self.get(admin_client, "?action=test.formula")
        row = list(csv.reader(io.StringIO(body.decode())))[1]
        assert row[2].startswith("'=") and row[8].startswith("'+")

    def test_safe_cell_unit(self):
        assert audit_export.safe_cell("@x") == "'@x" and audit_export.safe_cell("-1+1") == "'-1+1"
        assert audit_export.safe_cell("plain") == "plain" and audit_export.safe_cell(12) == 12

    def test_too_many_rows_is_refused(self, w, admin_client, monkeypatch):
        monkeypatch.setattr(audit_export, "MAX_ROWS", 1)
        audit.record("test.a", actor_label="x")
        audit.record("test.b", actor_label="x")
        assert admin_client.get(f"{API}/audit/export?action=test.*").status_code == 409

    def test_only_super_admin(self, w, p1c, r1c):
        assert p1c.get(f"{API}/audit/export").status_code == 403
        assert r1c.get(f"{API}/audit/export").status_code == 403


@pytest.mark.django_db
def test_membership_does_not_grant_view_all(w, admin):
    extra = make_user("extra@example.com", "pentester")
    EngagementMembership.objects.create(engagement=w.eng_a, user=extra, added_by=admin)
    got = rows(signed_in(extra), "?page_size=200")
    assert got and all(e["engagement"] for e in got)
