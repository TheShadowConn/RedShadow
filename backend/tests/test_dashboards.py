"""Phase 10: role dashboards. Every number must equal what the matching list screen shows for the same user."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.dashboards import selectors
from apps.engagements.models import EngagementMembership
from apps.findings.models import Finding
from tests.conftest import Api, signed_in
from tests.test_findings import API, make, publish
from tests.world import build_world

DASH = f"{API}/dashboards"
OPEN = "open,in_progress,pending_verification,reopened"
SEVERITIES = ["critical", "high", "medium", "low", "info"]
STATUSES = ["draft", "open", "in_progress", "pending_verification", "reopened", "closed", "risk_accepted",
            "false_positive", "duplicate"]  # fmt: skip


@pytest.fixture
def w(admin):
    return build_world(admin)


@pytest.fixture
def p1c(w):
    return signed_in(w.p1)


@pytest.fixture
def r1c(w):
    return signed_in(w.r1)


def count(client, query: str) -> int:
    r = client.get(f"{API}/findings?page_size=1&{query}")
    assert r.status_code == 200, r.content
    return r.json()["count"]


def seed(w, p1c, extra_eng=None):
    """Findings in every status and severity, some assigned to the Remediation user, some overdue."""
    today = timezone.localdate()
    specs = [
        ("critical", "open", -3), ("high", "in_progress", -1), ("high", "open", 3), ("medium", "reopened", 20),
        ("medium", "pending_verification", None), ("low", "closed", None), ("low", "risk_accepted", None),
        ("info", "open", None), ("critical", "false_positive", None), ("medium", "duplicate", None),
    ]  # fmt: skip
    rows = []
    for i, (sev, status, due) in enumerate(specs):
        f = publish(p1c, make(p1c, w.eng_a, title=f"Dash finding {i} {sev}", severity=sev))
        fields = {"status": status, "remediation_owner": w.r1 if i % 2 == 0 else None}
        if due is not None:
            fields["due_date"] = today + timedelta(days=due)
        if status == "closed":
            fields.update(closed_at=timezone.now() - timedelta(days=2), due_date=today + timedelta(days=5))
        if status == "risk_accepted":
            fields["risk_accepted_until"] = today + timedelta(days=10)
        if status == "duplicate":
            fields["duplicate_of"] = Finding.objects.get(pk=rows[0]["id"])
        Finding.objects.filter(pk=f["id"]).update(**fields)
        rows.append(f)
    make(p1c, w.eng_a, title="Secret draft title", severity="high")  # stays a draft
    return rows


def dash(client, kind):
    r = client.get(f"{DASH}/{kind}")
    assert r.status_code == 200, r.content
    return r.json()


def assert_matches_lists(client, d, with_verification, with_queue=True):
    f = d["findings"]
    assert f["total"] == count(client, "")
    for s in STATUSES:
        assert f["by_status"][s] == count(client, f"status={s}"), s
    for sev in SEVERITIES:
        assert f["by_severity"][sev] == count(client, f"severity={sev}"), sev
        assert f["open_by_severity"][sev] == count(client, f"severity={sev}&status={OPEN}"), sev
    assert f["open"] == count(client, f"status={OPEN}")
    assert f["drafts"] == count(client, "status=draft")
    if with_queue:
        remediation = client.get(f"{API}/queues/remediation?page_size=1").json()["counts"]
        assert f["overdue"] == remediation["overdue"]
    if with_verification:
        assert f["pending_verification"] == client.get(f"{API}/queues/verification?page_size=1").json()["count"]
    e = d["engagements"]
    for status, n in e["by_status"].items():
        assert n == client.get(f"{API}/engagements?page_size=1&status={status}").json()["count"], status
    assert e["total"] == client.get(f"{API}/engagements?page_size=1").json()["count"]
    assert len(d["trend"]) == selectors.TREND_WEEKS
    assert sum(t["opened"] for t in d["trend"]) == f["total"] - f["drafts"]


@pytest.mark.django_db
class TestNumbersMatchTheLists:
    def test_admin(self, w, admin_client, p1c):
        seed(w, p1c)
        p2c = signed_in(w.p2)
        publish(p2c, make(p2c, w.eng_b, title="Other org finding", severity="critical"))
        d = dash(admin_client, "admin")
        assert d["kind"] == "admin" and d["findings"]["total"] == 12  # 10 + draft + the other organisation's
        assert_matches_lists(admin_client, d, with_verification=True)

    def test_pentester(self, w, p1c):
        seed(w, p1c)
        d = dash(p1c, "pentester")
        assert d["kind"] == "pentester"
        assert_matches_lists(p1c, d, with_verification=True)
        assert d["mine"]["open"] == count(p1c, f"assigned=me&status={OPEN}")

    def test_remediation(self, w, p1c, r1c):
        seed(w, p1c)
        d = dash(r1c, "remediation")
        assert d["kind"] == "remediation"
        assert 0 < d["findings"]["total"] < 10  # only what is assigned and published
        assert_matches_lists(r1c, d, with_verification=False)
        assert all(row["id"] for row in d["next_due"])

    def test_assigned_only_member_sees_assigned_numbers(self, w, p1c):
        seeded = seed(w, p1c)
        EngagementMembership.objects.create(engagement=w.eng_a, user=w.p3, finding_scope="assigned")
        Finding.objects.filter(pk=seeded[0]["id"]).update(assigned_pentester=w.p3)
        c3 = signed_in(w.p3)
        d = dash(c3, "pentester")
        assert d["findings"]["total"] == 1 == count(c3, "")
        assert_matches_lists(c3, d, with_verification=True)


@pytest.mark.django_db
class TestIsolationAndAccess:
    def test_other_engagements_never_leak(self, w, p1c):
        seed(w, p1c)
        p2c = signed_in(w.p2)
        hidden = publish(p2c, make(p2c, w.eng_b, title="Borealis only finding", severity="critical"))
        d = dash(p1c, "pentester")
        text = str(d)
        assert "Borealis" not in text and w.eng_b.ref not in text and hidden["ref"] not in text
        assert d["findings"]["total"] == 11

    def test_remediation_activity_hides_drafts(self, w, p1c, r1c):
        seed(w, p1c)
        feed = dash(r1c, "remediation")["activity"]
        assert not any("Secret draft title" in (e["entity_label"] or "") for e in feed)
        assert "Secret draft title" not in str(dash(r1c, "remediation"))

    def test_each_dashboard_needs_its_own_permission(self, w, admin_client, p1c, r1c):
        assert p1c.get(f"{DASH}/admin").status_code == 403
        assert r1c.get(f"{DASH}/admin").status_code == 403
        assert r1c.get(f"{DASH}/pentester").status_code == 403
        assert p1c.get(f"{DASH}/remediation").status_code == 403
        for kind in ("admin", "pentester", "remediation"):
            assert admin_client.get(f"{DASH}/{kind}").status_code == 200

    def test_anonymous_and_writes_are_refused(self, w, admin_client):
        assert Api().get(f"{DASH}/admin").status_code == 401
        assert admin_client.post(f"{DASH}/admin", {}, format="json").status_code == 405


@pytest.mark.django_db
class TestMeasures:
    def test_sla_compliance_and_time_to_close(self, w, p1c):
        today = timezone.localdate()
        for i, due in enumerate([today + timedelta(days=3), today - timedelta(days=5)]):
            f = publish(p1c, make(p1c, w.eng_a, title=f"Closed {i}", severity="high"))
            Finding.objects.filter(pk=f["id"]).update(
                status="closed", closed_at=timezone.now() - timedelta(days=1), due_date=due
            )
        sla = dash(p1c, "pentester")["sla"]
        assert sla["closed"] == 2 and sla["dated"] == 2 and sla["on_time"] == 1 and sla["compliance_pct"] == 50.0
        assert sla["mean_days_to_close"] is not None

    def test_empty_dashboard_is_well_formed(self, w, p1c):
        d = dash(p1c, "pentester")
        assert d["findings"]["total"] == 0 and d["sla"]["compliance_pct"] is None
        assert d["findings"]["by_severity"] == dict.fromkeys(SEVERITIES, 0)
        assert d["retests"]["active_rounds"] == 0 and d["next_due"] == []

    def test_trend_buckets_this_week(self, w, p1c):
        seed(w, p1c)
        trend = dash(p1c, "pentester")["trend"]
        assert trend[-1]["opened"] == 10
        # seed() closes one finding two days ago, which is last week's bucket on a Monday or Tuesday
        closed_day = (timezone.now() - timedelta(days=2)).date()
        closed_week = closed_day - timedelta(days=closed_day.weekday())
        closed = {str(t["week_start"]): t["closed"] for t in trend}
        assert closed[str(closed_week)] == 1 and sum(closed.values()) == 1
        assert [t["week_start"] for t in trend] == sorted(t["week_start"] for t in trend)

    def test_upcoming_engagements_and_top_organisations(self, w, admin_client, p1c):
        seed(w, p1c)
        from apps.engagements.models import Engagement

        Engagement.objects.filter(pk=w.eng_b.pk).update(
            status="scheduled", start_date=timezone.localdate() + timedelta(days=4)
        )
        d = dash(admin_client, "admin")
        assert [e["ref"] for e in d["engagements"]["upcoming"]] == [w.eng_a.ref, w.eng_b.ref]  # soonest start first
        assert d["top_organisations"][0]["name"] == "Acme Corp" and d["top_organisations"][0]["critical"] >= 1

    def test_query_count_stays_flat(self, w, admin_client, p1c, django_assert_max_num_queries):
        seed(w, p1c)
        dash(admin_client, "admin")  # warm caches (permissions)
        with django_assert_max_num_queries(45):
            dash(admin_client, "admin")
