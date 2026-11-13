"""Phase 5A: finding state machine, remediation timeline, SLA due dates, risk acceptance."""

import datetime

import pytest
from django.db import IntegrityError, connection, transaction

from apps.audit.models import AuditEvent
from apps.audit.service import verify_chain
from apps.findings import lifecycle
from apps.findings.models import Finding, FindingNote, RemediationActivity
from tests.conftest import signed_in
from tests.test_findings import API, furl, make, publish
from tests.world import build_world

NOTE = "Verified against the staging build, fix confirmed."


@pytest.fixture
def w(admin):
    return build_world(admin)


@pytest.fixture
def p1c(w):
    return signed_in(w.p1)


@pytest.fixture
def r1c(w):
    return signed_in(w.r1)


@pytest.fixture
def live(w, p1c):
    """A published finding assigned to remediation user r1."""
    f = publish(p1c, make(p1c, w.eng_a))
    r = p1c.patch(furl(f), {"version": f["version"], "remediation_owner": str(w.r1.pk)}, format="json")
    assert r.status_code == 200, r.content
    return r.json()


def move(client, f, to, **kw):
    return client.post(furl(f, "/transition"), {"to": to, "version": f["version"], **kw}, format="json")


def go(client, f, to, **kw):
    r = move(client, f, to, **kw)
    assert r.status_code == 200, r.content
    return r.json()


@pytest.mark.django_db
class TestTable:
    def test_every_source_target_pair_is_unique_and_known(self):
        for rule in lifecycle.RULES:
            assert rule.target in lifecycle.STATUS_ORDER
            assert set(rule.sources) <= set(lifecycle.STATUS_ORDER)
            assert rule.perms

    def test_closed_findings_only_move_to_reopened(self):
        assert [r.target for r in lifecycle.RULES if "closed" in r.sources] == ["reopened"]

    def test_dead_ends_have_no_other_exit(self):
        for dead in ("false_positive", "duplicate"):
            assert [r.target for r in lifecycle.RULES if dead in r.sources] == ["reopened"]


@pytest.mark.django_db
class TestHappyPath:
    def test_full_remediation_cycle(self, w, p1c, r1c, live):
        f = go(r1c, live, "in_progress")
        assert f["status"] == "in_progress"
        f = go(r1c, f, "open")  # pause
        f = go(r1c, f, "in_progress")
        assert move(r1c, f, "pending_verification").status_code == 400  # note required
        assert move(r1c, f, "pending_verification", note="no").status_code == 400
        f = go(r1c, f, "pending_verification", note="Patched in release 2.4, parameters are now bound.")
        assert f["resolved_at"] and f["is_overdue"] is False
        f = go(p1c, f, "reopened", note="Still injectable through the sort parameter.")
        assert f["resolved_at"] is None
        f = go(r1c, f, "in_progress")
        f = go(r1c, f, "pending_verification", note="Sort parameter now allow-listed as well.")
        f = go(p1c, f, "closed", note=NOTE)
        assert f["status"] == "closed" and f["closed_at"] and f["verified_at"]
        assert f["verified_by"]["email"] == w.p1.email
        f = go(p1c, f, "reopened", note="Regression found on the production build.")
        assert f["status"] == "reopened" and f["closed_at"] is None and f["verified_at"] is None
        actions = list(RemediationActivity.objects.filter(finding_id=f["id"]).order_by("created_at", "id")
                       .values_list("action", flat=True))  # fmt: skip
        assert actions == [
            "published", "started", "paused", "started", "submitted_for_verification", "verification_failed",
            "started", "submitted_for_verification", "verification_passed", "reopened",
        ]  # fmt: skip
        assert verify_chain().ok

    def test_notes_are_stored_and_visible_to_remediation(self, w, p1c, r1c, live):
        f = go(r1c, live, "pending_verification", note="Upgraded the framework to 5.2.")
        go(p1c, f, "reopened", note="Header is still reflected in the response.")
        kinds = {n["kind"] for n in r1c.get(furl(live, "/notes")).json()["results"]}
        assert {"remediation", "verification"} <= kinds
        assert FindingNote.objects.filter(finding_id=live["id"], kind="verification").count() == 1
        r = p1c.post(furl(live, "/notes"), {"kind": "verification", "body": "forged verification"}, format="json")
        assert r.status_code == 400  # verification notes only come from transitions

    def test_direct_close_by_pentester(self, w, p1c, live):
        f = go(p1c, live, "closed", note="Accepted as informational by the client.")
        assert f["status"] == "closed" and f["verified_at"] is None and f["closed_at"]

    def test_timeline_endpoint_lists_newest_first(self, w, p1c, r1c, live):
        go(r1c, live, "in_progress")
        rows = r1c.get(furl(live, "/activity")).json()["results"]
        assert [r["action"] for r in rows] == ["started", "published"]
        assert rows[0]["actor"]["email"] == w.r1.email and rows[0]["from_status"] == "open"


@pytest.mark.django_db
class TestPermissions:
    @pytest.mark.parametrize("to,kw", [
        ("closed", {"note": NOTE}),
        ("risk_accepted", {"note": NOTE, "risk_accepted_until": "2099-01-01"}),
        ("false_positive", {"note": NOTE}),
    ])  # fmt: skip
    def test_remediation_cannot_run_testing_team_moves(self, w, r1c, live, to, kw):
        r = move(r1c, live, to, **kw)
        assert r.status_code == 403
        assert Finding.objects.get(pk=live["id"]).status == "open"
        assert AuditEvent.objects.filter(outcome="denied", entity_id=live["id"]).exists()

    def test_remediation_cannot_verify_or_reopen(self, w, p1c, r1c, live):
        f = go(r1c, live, "pending_verification", note="Fixed in 2.4, retest please.")
        assert move(r1c, f, "closed", note=NOTE).status_code == 403
        assert move(r1c, f, "reopened", note=NOTE).status_code == 403
        f = go(p1c, f, "closed", note=NOTE)
        assert move(r1c, f, "reopened", note=NOTE).status_code == 403

    def test_remediation_cannot_publish(self, w, p1c, r1c):
        f = make(p1c, w.eng_a)
        assert r1c.get(furl(f)).status_code == 404  # drafts are invisible to remediation
        assert move(p1c, f, "open").status_code == 200

    def test_pentester_cannot_accept_risk_but_admin_can(self, w, p1c, admin_client, live):
        assert move(p1c, live, "risk_accepted", note=NOTE, risk_accepted_until="2099-01-01").status_code == 403
        soon = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()
        r = move(admin_client, live, "risk_accepted", note="Business accepts the exposure.", risk_accepted_until=soon)
        assert r.status_code == 200 and r.json()["status"] == "risk_accepted"

    def test_other_engagement_pentester_gets_404(self, w, live):
        assert move(signed_in(w.p2), live, "in_progress").status_code == 404

    def test_allowed_transitions_follow_role(self, w, p1c, r1c, admin_client, live):
        names = lambda c: {t["to"] for t in c.get(furl(live)).json()["allowed_transitions"]}  # noqa: E731
        assert names(r1c) == {"in_progress", "pending_verification"}
        assert {"closed", "duplicate", "false_positive", "pending_verification"} <= names(p1c)
        assert "risk_accepted" not in names(p1c) and "risk_accepted" in names(admin_client)


@pytest.mark.django_db
class TestRules:
    def test_unknown_moves_are_conflicts(self, w, p1c, live):
        assert move(p1c, live, "draft").status_code == 409
        assert move(p1c, live, "reopened").status_code == 409  # open is not reopenable
        draft = make(p1c, w.eng_a, title="Other")
        assert move(p1c, draft, "closed", note=NOTE).status_code == 409

    def test_stale_version_is_rejected(self, w, p1c, r1c, live):
        go(r1c, live, "in_progress")
        r = move(p1c, live, "closed", note=NOTE)  # still holds the old version
        assert r.status_code == 409
        assert Finding.objects.get(pk=live["id"]).status == "in_progress"

    def test_second_of_two_racing_moves_loses(self, w, p1c, r1c, live):
        assert move(r1c, live, "in_progress").status_code == 200
        assert move(p1c, live, "in_progress").status_code == 409

    def test_move_is_atomic(self, w, p1c, live, monkeypatch):
        from apps.findings import services

        def boom(*a, **k):
            raise RuntimeError("audit down")

        monkeypatch.setattr(services.audit, "record", boom)
        with pytest.raises(RuntimeError):
            services.transition(None, w.p1, Finding.objects.get(pk=live["id"]), "in_progress", None)
        f = Finding.objects.get(pk=live["id"])
        assert f.status == "open" and f.version == live["version"]
        assert RemediationActivity.objects.filter(finding=f).count() == 1  # only the publish entry

    def test_archived_engagement_blocks_moves(self, w, p1c, admin, live):
        from apps.engagements import services as eng_services

        eng_services.change_status(None, admin, w.eng_a, "cancelled", w.eng_a.version)
        w.eng_a.refresh_from_db()
        eng_services.archive_engagement(None, admin, w.eng_a, w.eng_a.version)
        assert move(p1c, live, "in_progress").status_code == 409

    def test_risk_acceptance_validation(self, w, admin_client, live):
        today = datetime.date.today()
        bad = lambda until: move(admin_client, live, "risk_accepted", note=NOTE, risk_accepted_until=until)  # noqa: E731
        assert move(admin_client, live, "risk_accepted", note=NOTE).status_code == 400
        assert bad(today.isoformat()).status_code == 400
        assert bad((today + datetime.timedelta(days=366)).isoformat()).status_code == 400
        until = today + datetime.timedelta(days=365)
        f = go(admin_client, live, "risk_accepted", note=NOTE, risk_accepted_until=until.isoformat())
        assert f["risk_accepted_until"] == until.isoformat() and f["risk_acceptance_reason"] == NOTE
        f = go(admin_client, f, "reopened", note="Acceptance withdrawn after the audit.")
        assert f["risk_accepted_until"] is None and f["risk_acceptance_reason"] == ""

    def test_false_positive_and_duplicate_can_reopen(self, w, p1c, live):
        other = publish(p1c, make(p1c, w.eng_a, title="Original"))
        dup = go(p1c, live, "duplicate", duplicate_of=other["id"])
        assert dup["duplicate_of"]["ref"] == other["ref"]
        assert move(p1c, dup, "reopened").status_code == 400  # reason required
        back = go(p1c, dup, "reopened", note="Not the same root cause after all.")
        assert back["status"] == "reopened" and back["duplicate_of"] is None
        fp = go(p1c, publish(p1c, make(p1c, w.eng_a, title="Third")), "false_positive", note="Scanner artefact here.")
        assert go(p1c, fp, "reopened", note="Reproduced on a second host.")["status"] == "reopened"

    def test_duplicate_rules_still_apply(self, w, p1c, live):
        assert move(p1c, live, "duplicate").status_code == 400
        assert move(p1c, live, "duplicate", duplicate_of=live["id"]).status_code == 400


@pytest.mark.django_db
class TestSla:
    @pytest.mark.parametrize("severity,days", [("critical", 7), ("high", 30), ("medium", 90), ("low", 180)])
    def test_due_date_set_at_publish(self, w, p1c, severity, days):
        f = publish(p1c, make(p1c, w.eng_a, severity=severity))
        assert f["due_date"] == (datetime.date.today() + datetime.timedelta(days=days)).isoformat()

    def test_info_has_no_sla_and_drafts_have_no_due_date(self, w, p1c):
        draft = make(p1c, w.eng_a, severity="info")
        assert draft["due_date"] is None
        assert publish(p1c, draft)["due_date"] is None

    def test_severity_change_recomputes_due_date(self, w, p1c):
        f = publish(p1c, make(p1c, w.eng_a, severity="low"))
        r = p1c.patch(furl(f), {"version": f["version"], "severity": "critical"}, format="json")
        assert r.status_code == 200
        assert r.json()["due_date"] == (datetime.date.today() + datetime.timedelta(days=7)).isoformat()

    def test_overdue_flag(self, w, p1c, live):
        Finding.objects.filter(pk=live["id"]).update(due_date=datetime.date.today() - datetime.timedelta(days=1))
        assert p1c.get(furl(live)).json()["is_overdue"] is True
        row = p1c.get(f"{API}/findings").json()["results"][0]
        assert row["is_overdue"] is True and row["due_date"]
        f = p1c.get(furl(live)).json()
        f = go(p1c, f, "closed", note=NOTE)
        assert f["is_overdue"] is False  # clock stops once the finding is closed

    def test_reopen_keeps_original_due_date(self, w, p1c, live):
        f = go(p1c, live, "closed", note=NOTE)
        assert go(p1c, f, "reopened", note="Came back after the release.")["due_date"] == live["due_date"]


@pytest.mark.django_db
class TestEditing:
    def test_editable_while_working_not_while_pending_or_closed(self, w, p1c, r1c, live):
        edit = lambda f: p1c.patch(furl(f), {"version": f["version"], "endpoint": "/search"}, format="json")  # noqa: E731
        f = go(r1c, live, "in_progress")
        f = edit(f).json()
        f = go(r1c, f, "pending_verification", note="Fix deployed to staging.")
        assert edit(f).status_code == 409
        f = go(p1c, f, "reopened", note="Fix incomplete, still reproducible.")
        f = edit(f).json()
        assert f["endpoint"] == "/search"
        f = go(p1c, f, "closed", note=NOTE)
        assert edit(f).status_code == 409


@pytest.mark.django_db
class TestActivity:
    def post(self, c, f, **kw):
        return c.post(furl(f, "/activity"), {"action": "comment", "note": "Working on it.", **kw}, format="json")

    def test_remediation_can_log_progress(self, w, r1c, live):
        assert self.post(r1c, live, action="fix_deployed", note="Hotfix on staging.").status_code == 201
        assert self.post(r1c, live, action="mitigated", note="WAF rule added.").status_code == 201
        assert self.post(r1c, live).status_code == 201
        assert r1c.get(furl(live)).json()["status"] == "open"  # timeline only, no status change

    def test_rejects_drafts_blank_notes_and_foreign_evidence(self, w, p1c, r1c, live):
        draft = make(p1c, w.eng_a, title="Draft")
        assert self.post(p1c, draft).status_code == 409
        assert self.post(r1c, live, note="  ").status_code == 400
        other = publish(p1c, make(p1c, w.eng_a, title="Elsewhere"))
        r = p1c.post(furl(other, "/activity"), {"action": "comment", "note": "x", "evidence_ids": [live["id"]]},
                     format="json")  # fmt: skip
        assert r.status_code == 400

    def test_progress_updates_need_a_working_status(self, w, p1c, r1c, live):
        f = go(p1c, live, "closed", note=NOTE)
        assert self.post(r1c, f, action="fix_deployed").status_code == 409
        assert self.post(r1c, f).status_code == 201  # comments stay open

    def test_activity_rows_are_append_only(self, w, live):
        row = RemediationActivity.objects.filter(finding_id=live["id"]).first()
        with pytest.raises(IntegrityError), transaction.atomic():
            RemediationActivity.objects.filter(pk=row.pk).update(note="tampered")
        with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cur:
            cur.execute("DELETE FROM findings_remediationactivity WHERE id = %s", [row.pk])


@pytest.mark.django_db
class TestAudit:
    def test_each_move_is_audited_with_changes(self, w, p1c, r1c, live):
        f = go(r1c, live, "pending_verification", note="Fix is live on staging.")
        go(p1c, f, "closed", note=NOTE)
        ev = AuditEvent.objects.get(action="finding.verified", entity_id=live["id"])
        assert ev.changes["status"] == ["pending_verification", "closed"] and "verified_by" in ev.changes
        assert ev.engagement_id == w.eng_a.pk and ev.metadata["reason"] == NOTE

    def test_legacy_endpoints_use_the_machine(self, w, p1c):
        f = make(p1c, w.eng_a, title="Legacy")
        r = p1c.post(furl(f, "/publish"), {"version": 1}, format="json")
        assert r.status_code == 200 and r.json()["due_date"]
        assert RemediationActivity.objects.filter(finding_id=f["id"], action="published").exists()
        r = p1c.post(furl(f, "/false-positive"), {"version": 2, "reason": "Verified scanner noise"}, format="json")
        assert r.status_code == 200 and r.json()["status"] == "false_positive"
        assert RemediationActivity.objects.filter(finding_id=f["id"], action="false_positive").exists()
