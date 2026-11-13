"""Phase 7: calendar feed, double-booking hints, rescheduling."""

from datetime import timedelta

import pytest

from apps.audit.models import AuditEvent
from apps.engagements import scheduling
from apps.engagements import services as eng_services
from apps.engagements.models import Engagement
from tests.conftest import make_role, make_user, signed_in
from tests.test_findings import API, furl, make, publish
from tests.world import build_world

CAL = f"{API}/calendar/events"


@pytest.fixture
def w(admin):
    return build_world(admin)


@pytest.fixture
def p1c(w):
    return signed_in(w.p1)


@pytest.fixture
def r1c(w):
    return signed_in(w.r1)


def window(w, days=60, back=5):
    return f"start={w.today - timedelta(days=back)}&end={w.today + timedelta(days=days)}"


def feed(client, w, extra="", **kw):
    r = client.get(f"{CAL}?{window(w, **kw)}{extra}")
    assert r.status_code == 200, r.content
    return r.json()["results"]


def refs(events):
    return {e["ref"] for e in events}


def extra_engagement(admin, w, name="Second Acme test", start=None, end=None, lead=None, org=None):
    return eng_services.create_engagement(
        None, admin,
        {**w.base, "organisation": org or w.org_a, "name": name, "lead": lead or w.p1,
         "start_date": start or w.today, "end_date": end or w.today + timedelta(days=5)},
    )  # fmt: skip


def go_to(admin, eng, status):
    steps = {"cancelled": ["cancelled"], "completed": ["scheduled", "in_progress", "reporting", "completed"]}[status]
    for s in steps:
        eng.refresh_from_db()
        eng_services.change_status(None, admin, eng, s, eng.version)


@pytest.mark.django_db
class TestFeed:
    def test_scoping(self, w, admin_client, p1c, r1c):
        assert refs(feed(admin_client, w)) == {w.eng_a.ref, w.eng_b.ref}
        assert refs(feed(p1c, w)) == {w.eng_a.ref}
        assert refs(feed(signed_in(w.p2), w)) == {w.eng_b.ref}
        assert refs(feed(r1c, w)) == {w.eng_a.ref}

    def test_role_without_calendar_view_is_refused(self, w):
        nobody = make_user("nobody@example.com", make_role("NoCal", ["engagements.view"]))
        assert signed_in(nobody).get(f"{CAL}?{window(w)}").status_code == 403

    def test_event_shape_and_team(self, w, p1c):
        ev = feed(p1c, w)[0]
        assert ev["lead"]["id"] == str(w.p1.pk) and ev["client"]["name"] == "Acme Corp"
        assert {u["id"] for u in ev["team"]} >= {str(w.p1.pk), str(w.r1.pk)}
        assert ev["status"] == "planned" and ev["overdue"] is False and ev["version"] == 1

    def test_window_overlap(self, w, p1c):
        far = f"start={w.today + timedelta(days=100)}&end={w.today + timedelta(days=120)}"
        assert p1c.get(f"{CAL}?{far}").json()["results"] == []
        edge = f"start={w.today + timedelta(days=10)}&end={w.today + timedelta(days=20)}"
        assert refs(p1c.get(f"{CAL}?{edge}").json()["results"]) == {w.eng_a.ref}  # ends on the first day

    @pytest.mark.parametrize(
        "query",
        [
            "",
            "start=2026-01-01",
            "start=x&end=y",
            "start=2026-02-01&end=2026-01-01",
            "start=2026-01-01&end=2028-01-01",
        ],
    )
    def test_bad_windows_are_400(self, w, p1c, query):
        assert p1c.get(f"{CAL}?{query}").status_code == 400

    def test_too_many_events_is_400(self, w, admin_client, monkeypatch):
        monkeypatch.setattr(scheduling, "MAX_EVENTS", 1)
        assert admin_client.get(f"{CAL}?{window(w)}").status_code == 400

    def test_cancelled_hidden_unless_asked_and_archived_never_shown(self, w, admin, admin_client):
        c = extra_engagement(admin, w, "To cancel")
        go_to(admin, c, "cancelled")
        assert c.ref not in refs(feed(admin_client, w))
        assert c.ref in refs(feed(admin_client, w, "&status=cancelled"))
        c.refresh_from_db()
        eng_services.archive_engagement(None, admin, c, c.version)
        assert c.ref not in refs(feed(admin_client, w, "&status=cancelled,planned"))

    def test_completed_shown_by_default(self, w, admin, admin_client):
        c = extra_engagement(admin, w, "Done")
        go_to(admin, c, "completed")
        assert c.ref in refs(feed(admin_client, w))

    def test_filters(self, w, admin, admin_client):
        c = extra_engagement(admin, w, "Borealis extra", lead=w.p2, org=w.org_b)
        assert refs(feed(admin_client, w, f"&client={w.org_b.pk}")) == {w.eng_b.ref, c.ref}
        assert refs(feed(admin_client, w, f"&pentester={w.p1.pk}")) == {w.eng_a.ref}
        assert refs(feed(admin_client, w, f"&engagement={c.pk}")) == {c.ref}
        assert refs(feed(admin_client, w, "&status=scheduled")) == set()
        assert refs(feed(signed_in(w.p1), w, "&mine=true")) == {w.eng_a.ref}
        assert refs(feed(admin_client, w, "&mine=true")) == set()  # admin is on no team

    def test_filter_ids_are_validated(self, w, p1c):
        assert p1c.get(f"{CAL}?{window(w)}&client=nope").status_code == 400

    def test_overdue_flag(self, w, admin_client):
        Engagement.objects.filter(pk=w.eng_a.pk).update(
            start_date=w.today - timedelta(days=9), end_date=w.today - timedelta(days=1)
        )
        ev = {e["ref"]: e for e in feed(admin_client, w)}[w.eng_a.ref]
        assert ev["overdue"] is True

    def test_finding_counts_follow_finding_scope(self, w, p1c, r1c):
        mine = publish(p1c, make(p1c, w.eng_a, title="Assigned"))
        p1c.patch(furl(mine), {"version": mine["version"], "remediation_owner": str(w.r1.pk)}, format="json")
        publish(p1c, make(p1c, w.eng_a, title="Not assigned"))
        make(p1c, w.eng_a, title="Draft")
        assert feed(p1c, w)[0]["findings"] == {"total": 3, "active": 2}
        assert feed(r1c, w)[0]["findings"] == {"total": 1, "active": 1}  # one assigned, published finding


@pytest.mark.django_db
class TestConflicts:
    def test_overlap_marks_both_events_for_the_shared_person(self, w, admin, admin_client):
        c = extra_engagement(admin, w)  # same lead p1, same dates as A
        events = {e["ref"]: e for e in feed(admin_client, w)}
        for mine, other in ((w.eng_a.ref, c.ref), (c.ref, w.eng_a.ref)):
            hit = events[mine]["conflicts"]
            assert any(h["user"]["id"] == str(w.p1.pk) and h["with"]["ref"] == other for h in hit)
        assert events[w.eng_b.ref]["conflicts"] == []

    def test_no_overlap_no_conflict(self, w, admin, admin_client):
        later = extra_engagement(admin, w, start=w.today + timedelta(days=30), end=w.today + timedelta(days=35))
        events = {e["ref"]: e for e in feed(admin_client, w)}
        assert events[later.ref]["conflicts"] == [] and events[w.eng_a.ref]["conflicts"] == []

    def test_finished_engagements_do_not_conflict(self, w, admin, admin_client):
        c = extra_engagement(admin, w)
        go_to(admin, c, "completed")
        assert {e["ref"]: e for e in feed(admin_client, w)}[w.eng_a.ref]["conflicts"] == []

    def test_viewer_never_learns_about_engagements_they_cannot_see(self, w, admin, r1c):
        extra_engagement(admin, w)  # r1 is only on A
        events = feed(r1c, w)
        assert refs(events) == {w.eng_a.ref} and events[0]["conflicts"] == []


@pytest.mark.django_db
class TestReschedule:
    def url(self, eng):
        return f"{CAL}/{eng.pk}/reschedule"

    def body(self, w, eng, shift=7, **kw):
        eng.refresh_from_db()
        return {"start_date": str(eng.start_date + timedelta(days=shift)), "end_date": str(eng.end_date + timedelta(days=shift)),
                "version": eng.version, **kw}  # fmt: skip

    def test_admin_moves_and_it_is_audited(self, w, admin_client):
        old = (w.eng_a.start_date, w.eng_a.end_date)
        r = admin_client.post(self.url(w.eng_a), self.body(w, w.eng_a), format="json")
        assert r.status_code == 200 and r.json()["saved"] is True and r.json()["version"] == 2
        w.eng_a.refresh_from_db()
        assert w.eng_a.start_date == old[0] + timedelta(days=7)
        ev = AuditEvent.objects.get(action="engagement.rescheduled")
        assert ev.engagement_id == w.eng_a.pk and ev.changes["start_date"][0] == old[0].isoformat()

    def test_dry_run_changes_nothing_but_reports_conflicts(self, w, admin, admin_client):
        extra_engagement(admin, w, start=w.today + timedelta(days=20), end=w.today + timedelta(days=25))
        r = admin_client.post(self.url(w.eng_a), self.body(w, w.eng_a, shift=20, dry_run=True), format="json")
        body = r.json()
        assert r.status_code == 200 and body["saved"] is False and body["version"] == 1
        assert body["conflicts"] and body["conflicts"][0]["user"]["id"] == str(w.p1.pk)
        w.eng_a.refresh_from_db()
        assert w.eng_a.start_date == w.today and not AuditEvent.objects.filter(action="engagement.rescheduled").exists()

    def test_conflict_warns_but_never_blocks(self, w, admin, admin_client):
        extra_engagement(admin, w, start=w.today + timedelta(days=20), end=w.today + timedelta(days=25))
        r = admin_client.post(self.url(w.eng_a), self.body(w, w.eng_a, shift=20), format="json")
        assert r.status_code == 200 and r.json()["saved"] is True and r.json()["conflicts"]
        assert AuditEvent.objects.get(action="engagement.rescheduled").metadata["double_booked"]

    def test_only_super_admin_can_move(self, w, p1c, r1c):
        for c in (p1c, r1c):
            assert c.post(self.url(w.eng_a), self.body(w, w.eng_a), format="json").status_code == 403
        assert signed_in(w.p2).post(self.url(w.eng_b), self.body(w, w.eng_b), format="json").status_code == 403
        w.eng_a.refresh_from_db()
        assert w.eng_a.start_date == w.today

    def test_unknown_engagement_is_404(self, w, admin_client):
        r = admin_client.post(f"{CAL}/00000000-0000-0000-0000-000000000000/reschedule",
                              {"start_date": str(w.today), "end_date": str(w.today), "version": 1}, format="json")  # fmt: skip
        assert r.status_code == 404

    def test_stale_version_is_409(self, w, admin_client):
        body = self.body(w, w.eng_a)
        assert admin_client.post(self.url(w.eng_a), body, format="json").status_code == 200
        assert admin_client.post(self.url(w.eng_a), body, format="json").status_code == 409

    def test_end_before_start_is_400(self, w, admin_client):
        body = {**self.body(w, w.eng_a), "end_date": str(w.today - timedelta(days=3))}
        assert admin_client.post(self.url(w.eng_a), body, format="json").status_code == 400

    @pytest.mark.parametrize("status", ["completed", "cancelled"])
    def test_finished_engagements_cannot_move(self, w, admin, admin_client, status):
        go_to(admin, w.eng_a, status)
        assert admin_client.post(self.url(w.eng_a), self.body(w, w.eng_a), format="json").status_code == 409

    def test_archived_engagement_cannot_move(self, w, admin, admin_client):
        go_to(admin, w.eng_a, "cancelled")
        w.eng_a.refresh_from_db()
        eng_services.archive_engagement(None, admin, w.eng_a, w.eng_a.version)
        assert admin_client.post(self.url(w.eng_a), self.body(w, w.eng_a), format="json").status_code == 409

    def test_same_dates_is_a_no_op(self, w, admin_client):
        body = self.body(w, w.eng_a, shift=0)
        r = admin_client.post(self.url(w.eng_a), body, format="json")
        assert r.status_code == 200 and r.json()["version"] == 1
        assert not AuditEvent.objects.filter(action="engagement.rescheduled").exists()

    def test_extra_fields_are_rejected(self, w, admin_client):
        body = {**self.body(w, w.eng_a), "status": "completed"}
        assert admin_client.post(self.url(w.eng_a), body, format="json").status_code == 400
