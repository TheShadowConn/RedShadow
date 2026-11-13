"""Phase 5B: retest rounds, work queues, hourly SLA and risk-expiry sweeps."""

import datetime

import pytest
from django.conf import settings

from apps.audit.models import AuditEvent
from apps.audit.service import verify_chain
from apps.engagements import services as eng_services
from apps.engagements.models import EngagementMembership
from apps.findings import tasks
from apps.findings.models import Finding, RemediationActivity
from tests.conftest import make_user, signed_in
from tests.test_findings import API, furl, make, publish
from tests.test_lifecycle import NOTE, go
from tests.world import build_world

TODAY = datetime.date.today()


@pytest.fixture
def w(admin):
    world = build_world(admin)
    world.p4 = make_user("p4@example.com", "pentester")  # second assessor on engagement A
    EngagementMembership.objects.create(engagement=world.eng_a, user=world.p4, added_by=admin)
    return world


@pytest.fixture
def p1c(w):
    return signed_in(w.p1)


@pytest.fixture
def p4c(w):
    return signed_in(w.p4)


@pytest.fixture
def r1c(w):
    return signed_in(w.r1)


def pending_finding(p1c, r1c, w, title="Finding", assign=True):
    f = publish(p1c, make(p1c, w.eng_a, title=title))
    if assign:
        r = p1c.patch(furl(f), {"version": f["version"], "remediation_owner": str(w.r1.pk)}, format="json")
        assert r.status_code == 200, r.content
        f = r.json()
        return go(r1c, f, "pending_verification", note="Fix is live on staging.")
    return go(p1c, f, "pending_verification", note="Fix is live on staging.")


def round_body(w, findings, assessor=None, **kw):
    return {"engagement": str(w.eng_a.pk), "assessor": str((assessor or w.p4).pk),
            "findings": [f["id"] for f in findings], **kw}  # fmt: skip


def rurl(rnd, tail=""):
    return f"{API}/retest-rounds/{rnd['id']}{tail}"


def new_round(client, w, findings, **kw):
    r = client.post(f"{API}/retest-rounds", round_body(w, findings, **kw), format="json")
    assert r.status_code == 201, r.content
    return r.json()


def result(client, rnd, idx, outcome="passed", note="Retested on staging, behaves as expected.", **kw):
    item = rnd["items"][idx]
    return client.post(rurl(rnd, f"/items/{item['id']}/result"), {"result": outcome, "note": note, **kw}, format="json")


@pytest.mark.django_db
class TestCreate:
    def test_creates_round_with_numbered_ref_and_timeline(self, w, p1c, r1c):
        a, b = pending_finding(p1c, r1c, w, "A"), pending_finding(p1c, r1c, w, "B")
        rnd = new_round(p1c, w, [a, b])
        assert rnd["number"] == 1 and rnd["ref"].endswith("-R1") and rnd["status"] == "queued"
        assert rnd["counts"]["pending"] == 2 and rnd["assessor"]["email"] == w.p4.email
        assert RemediationActivity.objects.filter(finding_id=a["id"], action="retest_requested").exists()
        c = pending_finding(p1c, r1c, w, "C")
        assert new_round(p1c, w, [c])["number"] == 2
        assert AuditEvent.objects.filter(action="retest_round.created", engagement_id=w.eng_a.pk).count() == 2

    def test_remediation_cannot_request_retest(self, w, p1c, r1c):
        a = pending_finding(p1c, r1c, w)
        assert r1c.post(f"{API}/retest-rounds", round_body(w, [a]), format="json").status_code == 403

    def test_only_pending_verification_findings(self, w, p1c, r1c):
        live = publish(p1c, make(p1c, w.eng_a, title="Open one"))
        r = p1c.post(f"{API}/retest-rounds", round_body(w, [live]), format="json")
        assert r.status_code == 400 and "pending verification" in str(r.json())

    def test_finding_cannot_be_in_two_open_rounds(self, w, p1c, r1c):
        a = pending_finding(p1c, r1c, w)
        new_round(p1c, w, [a])
        r = p1c.post(f"{API}/retest-rounds", round_body(w, [a]), format="json")
        assert r.status_code == 409

    def test_assessor_must_be_able_to_record(self, w, p1c, r1c):
        a = pending_finding(p1c, r1c, w)
        for bad in (w.r1, w.p2):  # remediation user; pentester outside the engagement
            r = p1c.post(f"{API}/retest-rounds", round_body(w, [a], assessor=bad), format="json")
            assert r.status_code == 400

    def test_findings_from_another_engagement_are_rejected(self, w, p1c, r1c, admin_client):
        other = make(admin_client, w.eng_b, title="Elsewhere")
        r = p1c.post(f"{API}/retest-rounds", round_body(w, [other]), format="json")
        assert r.status_code == 400

    def test_archived_engagement_blocks_creation(self, w, p1c, r1c, admin):
        a = pending_finding(p1c, r1c, w)
        eng_services.change_status(None, admin, w.eng_a, "cancelled", w.eng_a.version)
        w.eng_a.refresh_from_db()
        eng_services.archive_engagement(None, admin, w.eng_a, w.eng_a.version)
        assert p1c.post(f"{API}/retest-rounds", round_body(w, [a]), format="json").status_code == 409


@pytest.mark.django_db
class TestResults:
    def test_pass_closes_and_completes_round(self, w, p1c, p4c, r1c):
        a, b = pending_finding(p1c, r1c, w, "A"), pending_finding(p1c, r1c, w, "B")
        rnd = new_round(p1c, w, [a, b])
        r = result(p4c, rnd, 0, "passed")
        assert r.status_code == 200 and r.json()["status"] == "in_progress"
        first = Finding.objects.get(pk=rnd["items"][0]["finding"]["id"])
        assert first.status == "closed" and first.verified_by_id == w.p4.pk
        r = result(p4c, rnd, 1, "failed", note="Still injectable through the sort parameter.")
        body = r.json()
        assert body["status"] == "completed" and body["completed_at"]
        assert body["counts"]["passed"] == 1 and body["counts"]["failed"] == 1
        assert Finding.objects.get(pk=rnd["items"][1]["finding"]["id"]).status == "reopened"
        assert AuditEvent.objects.filter(action="retest_round.completed").exists()
        ev = AuditEvent.objects.get(action="finding.verified")
        assert ev.metadata["retest_round"] == rnd["ref"]
        assert verify_chain().ok

    def test_only_assigned_assessor_may_record(self, w, p1c, p4c, r1c, admin_client):
        a = pending_finding(p1c, r1c, w)
        rnd = new_round(p1c, w, [a])
        for client in (p1c, admin_client, r1c):  # requester, super admin, remediation owner
            assert result(client, rnd, 0).status_code in (403, 404)
        assert Finding.objects.get(pk=a["id"]).status == "pending_verification"
        assert AuditEvent.objects.filter(action="retest_round.result_denied", outcome="denied").exists()
        assert result(p4c, rnd, 0).status_code == 200

    def test_note_required_and_no_double_recording(self, w, p1c, p4c, r1c):
        a = pending_finding(p1c, r1c, w)
        rnd = new_round(p1c, w, [a])
        assert result(p4c, rnd, 0, note="no").status_code == 400
        assert result(p4c, rnd, 0).status_code == 200
        assert result(p4c, rnd, 0).status_code == 409

    def test_evidence_must_belong_to_finding(self, w, p1c, p4c, r1c):
        a = pending_finding(p1c, r1c, w)
        rnd = new_round(p1c, w, [a])
        assert result(p4c, rnd, 0, evidence_ids=[a["id"]]).status_code == 400

    def test_hand_verification_settles_the_item(self, w, p1c, r1c):
        a = pending_finding(p1c, r1c, w)
        rnd = new_round(p1c, w, [a])
        go(p1c, a, "closed", note=NOTE)  # a pentester closes it outside the retest
        got = p1c.get(rurl(rnd)).json()
        assert got["items"][0]["result"] == "not_tested" and got["status"] == "completed"


@pytest.mark.django_db
class TestAssessors:
    def test_lists_only_people_who_can_record(self, w, p1c, r1c, admin):
        got = p1c.get(f"{API}/retest-rounds/assessors?engagement={w.eng_a.pk}").json()
        emails = {u["email"] for u in got}
        assert w.p4.email in emails and w.p1.email in emails and admin.email in emails
        assert w.r1.email not in emails and w.p2.email not in emails  # remediation; not on the engagement

    def test_closed_to_remediation_and_other_engagements(self, w, p1c, r1c):
        assert r1c.get(f"{API}/retest-rounds/assessors?engagement={w.eng_a.pk}").status_code == 403
        assert p1c.get(f"{API}/retest-rounds/assessors?engagement={w.eng_b.pk}").status_code == 404
        assert p1c.get(f"{API}/retest-rounds/assessors").status_code == 404


@pytest.mark.django_db
class TestManage:
    def test_requester_can_cancel_and_items_become_not_tested(self, w, p1c, p4c, r1c):
        a = pending_finding(p1c, r1c, w)
        rnd = new_round(p1c, w, [a])
        assert p4c.post(rurl(rnd, "/cancel"), {"version": 1}, format="json").status_code == 403  # assessor only
        r = p1c.post(rurl(rnd, "/cancel"), {"version": 1}, format="json")
        assert r.status_code == 200 and r.json()["status"] == "cancelled"
        assert r.json()["items"][0]["result"] == "not_tested"
        assert Finding.objects.get(pk=a["id"]).status == "pending_verification"
        assert result(p4c, r.json(), 0).status_code == 409
        assert p1c.post(rurl(rnd, "/cancel"), {"version": 2}, format="json").status_code == 409

    def test_admin_can_cancel_any_round(self, w, p1c, r1c, admin_client):
        rnd = new_round(p1c, w, [pending_finding(p1c, r1c, w)])
        assert admin_client.post(rurl(rnd, "/cancel"), {"version": 1}, format="json").status_code == 200

    def test_reassign_moves_the_right_to_record(self, w, p1c, p4c, r1c, admin):
        p5 = make_user("p5@example.com", "pentester")
        EngagementMembership.objects.create(engagement=w.eng_a, user=p5, added_by=admin)
        a = pending_finding(p1c, r1c, w)
        rnd = new_round(p1c, w, [a])
        assert p4c.post(rurl(rnd, "/assign"), {"version": 1, "assessor": str(p5.pk)}, format="json").status_code == 403
        r = p1c.post(rurl(rnd, "/assign"), {"version": 1, "assessor": str(p5.pk)}, format="json")
        assert r.status_code == 200 and r.json()["assessor"]["email"] == p5.email
        assert result(p4c, rnd, 0).status_code == 403
        assert result(signed_in(p5), rnd, 0).status_code == 200

    def test_reassign_to_ineligible_user_is_rejected(self, w, p1c, r1c):
        rnd = new_round(p1c, w, [pending_finding(p1c, r1c, w)])
        r = p1c.post(rurl(rnd, "/assign"), {"version": 1, "assessor": str(w.p2.pk)}, format="json")
        assert r.status_code == 400


@pytest.mark.django_db
class TestVisibility:
    def test_other_engagement_pentester_cannot_see_rounds(self, w, p1c, r1c):
        rnd = new_round(p1c, w, [pending_finding(p1c, r1c, w)])
        other = signed_in(w.p2)
        assert other.get(rurl(rnd)).status_code == 404
        assert other.get(f"{API}/retest-rounds").json()["results"] == []

    def test_remediation_sees_only_its_own_items(self, w, p1c, r1c):
        mine = pending_finding(p1c, r1c, w, "Mine")
        theirs = pending_finding(p1c, r1c, w, "Not mine", assign=False)
        rnd = new_round(p1c, w, [mine, theirs])
        seen = r1c.get(rurl(rnd)).json()
        assert [i["finding"]["id"] for i in seen["items"]] == [mine["id"]] and seen["counts"]["total"] == 1
        only_theirs = new_round(p1c, w, [pending_finding(p1c, r1c, w, "Third", assign=False)])
        assert r1c.get(rurl(only_theirs)).status_code == 404  # no finding of theirs inside
        assert r1c.get(f"{API}/retest-rounds").json()["count"] == 1

    def test_flags_tell_the_ui_who_may_act(self, w, p1c, p4c, r1c):
        rnd = new_round(p1c, w, [pending_finding(p1c, r1c, w)])
        assert p4c.get(rurl(rnd)).json()["can_record"] is True and p4c.get(rurl(rnd)).json()["can_manage"] is False
        assert p1c.get(rurl(rnd)).json()["can_record"] is False and p1c.get(rurl(rnd)).json()["can_manage"] is True


@pytest.mark.django_db
class TestQueues:
    def test_remediation_queue_orders_overdue_first_and_counts(self, w, p1c, r1c):
        a = publish(p1c, make(p1c, w.eng_a, title="Late", severity="low"))
        b = publish(p1c, make(p1c, w.eng_a, title="Soon", severity="critical"))
        c = publish(p1c, make(p1c, w.eng_a, title="Later", severity="high"))
        for f in (a, b, c):
            p1c.patch(furl(f), {"version": 2, "remediation_owner": str(w.r1.pk)}, format="json")
        Finding.objects.filter(pk=a["id"]).update(due_date=TODAY - datetime.timedelta(days=3))
        body = r1c.get(f"{API}/queues/remediation").json()
        assert [row["title"] for row in body["results"]] == ["Late", "Soon", "Later"]
        assert body["counts"]["open"] == 3 and body["counts"]["overdue"] == 1
        assert body["results"][0]["is_overdue"] is True and body["results"][0]["days_left"] == -3
        assert r1c.get(f"{API}/queues/remediation?overdue=true").json()["count"] == 1

    def test_queue_matches_findings_list(self, w, p1c, r1c):
        for t in ("A", "B"):
            pending_finding(p1c, r1c, w, t)
        publish(p1c, make(p1c, w.eng_a, title="Unassigned"))  # not visible to r1
        listed = r1c.get(f"{API}/findings?status=open,in_progress,reopened").json()["count"]
        assert r1c.get(f"{API}/queues/remediation").json()["count"] == listed == 0
        for client in (p1c, r1c):
            ids = {r["id"] for r in client.get(f"{API}/findings?status=pending_verification").json()["results"]}
            if client is p1c:
                q = client.get(f"{API}/queues/verification").json()
                assert {r["id"] for r in q["results"]} == ids and q["counts"]["pending_verification"] == 2

    def test_verification_queue_shows_retest_and_is_closed_to_remediation(self, w, p1c, r1c):
        a = pending_finding(p1c, r1c, w, "A")
        pending_finding(p1c, r1c, w, "B")
        rnd = new_round(p1c, w, [a])
        rows = {r["title"]: r for r in p1c.get(f"{API}/queues/verification").json()["results"]}
        assert rows["A"]["retest"]["ref"] == rnd["ref"] and rows["B"]["retest"] is None
        assert r1c.get(f"{API}/queues/verification").status_code == 403

    def test_queues_respect_engagement_isolation(self, w, p1c, r1c):
        pending_finding(p1c, r1c, w)
        assert signed_in(w.p2).get(f"{API}/queues/verification").json()["count"] == 0


@pytest.mark.django_db
class TestSweeps:
    def live(self, w, p1c, **kw):
        return publish(p1c, make(p1c, w.eng_a, **kw))

    def test_sla_breach_recorded_once(self, w, p1c):
        f = self.live(w, p1c)
        Finding.objects.filter(pk=f["id"]).update(due_date=TODAY - datetime.timedelta(days=1))
        assert tasks.sla_sweep() == 1
        assert tasks.sla_sweep() == 0  # idempotent
        ev = AuditEvent.objects.get(action="finding.sla_breached", entity_id=f["id"])
        assert ev.actor_label == "system" and ev.actor_id is None and ev.engagement_id == w.eng_a.pk
        assert RemediationActivity.objects.filter(finding_id=f["id"], action="sla_breached", actor=None).count() == 1
        assert p1c.get(furl(f)).json()["is_overdue"] is True

    def test_sweep_skips_findings_not_being_fixed_or_not_late(self, w, p1c, r1c):
        late = {"due_date": TODAY - datetime.timedelta(days=1)}
        ok = self.live(w, p1c, title="On time")
        pend = pending_finding(p1c, r1c, w, "Waiting")
        Finding.objects.filter(pk=pend["id"]).update(**late)
        assert tasks.sla_sweep() == 0
        assert not Finding.objects.get(pk=ok["id"]).sla_breached_at

    def test_new_deadline_can_breach_again(self, w, p1c):
        f = self.live(w, p1c, severity="low")
        Finding.objects.filter(pk=f["id"]).update(due_date=TODAY - datetime.timedelta(days=1))
        tasks.sla_sweep()
        cur = p1c.get(furl(f)).json()
        r = p1c.patch(furl(f), {"version": cur["version"], "severity": "critical"}, format="json")
        assert r.status_code == 200 and Finding.objects.get(pk=f["id"]).sla_breached_at is None

    def test_expired_risk_acceptance_reopens(self, w, p1c, admin_client):
        f = self.live(w, p1c)
        soon = (TODAY + datetime.timedelta(days=5)).isoformat()
        f = go(admin_client, f, "risk_accepted", note="Business accepts the exposure.", risk_accepted_until=soon)
        assert tasks.expire_risk_acceptance() == 0  # not expired yet
        Finding.objects.filter(pk=f["id"]).update(risk_accepted_until=TODAY - datetime.timedelta(days=1))
        assert tasks.expire_risk_acceptance() == 1
        assert tasks.expire_risk_acceptance() == 0
        row = Finding.objects.get(pk=f["id"])
        assert row.status == "reopened" and row.risk_accepted_until is None and row.risk_acceptance_reason == ""
        ev = AuditEvent.objects.get(action="finding.reopened", entity_id=f["id"])
        assert ev.actor_label == "system" and ev.metadata["trigger"] == "risk_acceptance_expired"
        last = RemediationActivity.objects.filter(finding_id=f["id"]).first()
        assert last.action == "reopened" and last.actor_id is None and "expired" in last.note
        assert verify_chain().ok

    def test_archived_engagement_is_left_alone(self, w, p1c, admin):
        f = self.live(w, p1c)
        Finding.objects.filter(pk=f["id"]).update(due_date=TODAY - datetime.timedelta(days=1))
        eng_services.change_status(None, admin, w.eng_a, "cancelled", w.eng_a.version)
        w.eng_a.refresh_from_db()
        eng_services.archive_engagement(None, admin, w.eng_a, w.eng_a.version)
        assert tasks.sla_sweep() == 0

    def test_tasks_are_scheduled_hourly(self):
        names = {v["task"]: v["schedule"] for v in settings.CELERY_BEAT_SCHEDULE.values()}
        assert names["findings.sla_sweep"] == 3600.0 and names["findings.expire_risk_acceptance"] == 3600.0

    def test_one_failing_finding_does_not_stop_the_sweep(self, w, p1c, monkeypatch):
        a, b = self.live(w, p1c, title="A"), self.live(w, p1c, title="B")
        Finding.objects.filter(pk__in=[a["id"], b["id"]]).update(due_date=TODAY - datetime.timedelta(days=1))
        from apps.findings import services

        real = services.system_flag_sla_breach

        def flaky(finding):
            if finding.title == "A":
                raise RuntimeError("boom")
            return real(finding)

        monkeypatch.setattr(services, "system_flag_sla_breach", flaky)
        assert tasks.sla_sweep() == 1
        assert Finding.objects.get(pk=b["id"]).sla_breached_at is not None
