"""Cost report page API, import history deletion, the needs-review flag, and blank reference labels."""

from datetime import date

import pytest

from apps.audit.models import AuditEvent
from apps.engagements import services as eng_services
from apps.findings.models import Finding
from apps.imports.models import ImportJob
from tests.conftest import signed_in
from tests.test_findings import API
from tests.test_import_gaps import GAPS, import_everything
from tests.test_imports import GOOD, commit, prepared
from tests.world import build_world


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)


@pytest.fixture
def w(admin):
    return build_world(admin)


@pytest.fixture
def p1c(w):
    return signed_in(w.p1)


def cost(admin, eng, amount, currency="EUR", category="labour", on=date(2026, 11, 3), text=""):
    return eng_services.add_cost(
        None, admin, eng, {"amount": amount, "currency": currency, "category": category, "description": text,
                           "incurred_on": on},
    )  # fmt: skip


@pytest.mark.django_db
class TestCostReport:
    @pytest.fixture
    def lines(self, admin, w):
        cost(admin, w.eng_a, 100, on=date(2026, 11, 3), text="Labour")
        cost(admin, w.eng_a, 40, "USD", "travel", date(2026, 10, 20))
        cost(admin, w.eng_b, 250, "EUR", "tools", date(2025, 12, 5))

    def get(self, client, query=""):
        r = client.get(f"{API}/costs{query}")
        return r

    def test_lists_every_line_with_totals_timeline_and_options(self, admin_client, w, lines):
        r = self.get(admin_client)
        assert r.status_code == 200
        d = r.json()
        assert len(d["items"]) == 3 and d["truncated"] is False
        assert {(t["currency"], t["total"]) for t in d["totals"]} == {("EUR", 350.0), ("USD", 40.0)}
        assert [(t["month"], t["currency"]) for t in d["timeline"]] == [
            ("2025-12", "EUR"), ("2026-10", "USD"), ("2026-11", "EUR")]
        assert d["options"]["years"] == [2026, 2025]
        assert {e["ref"] for e in d["options"]["engagements"]} == {w.eng_a.ref, w.eng_b.ref}
        first = d["items"][0]
        assert first["engagement"]["ref"] == w.eng_a.ref and first["incurred_on"] == "2026-11-03"

    def test_filters(self, admin_client, w, lines):
        assert len(self.get(admin_client, "?year=2025").json()["items"]) == 1
        assert len(self.get(admin_client, "?year=2026&month=10").json()["items"]) == 1
        assert len(self.get(admin_client, f"?engagement={w.eng_b.pk}").json()["items"]) == 1
        assert len(self.get(admin_client, "?category=travel").json()["items"]) == 1
        d = self.get(admin_client, "?currency=EUR").json()
        assert len(d["items"]) == 2 and [t["currency"] for t in d["totals"]] == ["EUR"]
        by_eng = self.get(admin_client, "?year=2026&currency=EUR").json()["by_engagement"]
        assert [(b["engagement"]["ref"], b["total"]) for b in by_eng] == [(w.eng_a.ref, 100.0)]

    @pytest.mark.parametrize("query", ["?year=abc", "?month=13", "?currency=ZZZ", "?category=x", "?engagement=nope"])
    def test_bad_filters_are_refused(self, admin_client, query):
        assert self.get(admin_client, query).status_code == 400

    def test_needs_the_costs_permission(self, p1c, lines):
        assert self.get(p1c).status_code == 403

    def test_requires_sign_in(self, api):
        assert api.get(f"{API}/costs").status_code in (401, 403)


@pytest.mark.django_db
class TestImportHistory:
    def test_super_admin_deletes_a_completed_import_and_keeps_the_findings(self, w, admin_client, p1c):
        job = prepared(p1c, w.eng_a, [GOOD])
        assert commit(p1c, job).status_code == 202
        assert Finding.objects.filter(import_job_id=job["id"]).count() == 1
        listed = admin_client.get(f"{API}/imports/{job['id']}").json()
        assert listed["status"] == "completed" and listed["can_delete"] is True
        assert admin_client.delete(f"{API}/imports/{job['id']}").status_code == 204
        assert not ImportJob.objects.filter(pk=job["id"]).exists()
        kept = Finding.objects.get(title="SQL injection")
        assert kept.import_job_id is None and kept.source == "import"
        ev = AuditEvent.objects.get(action="import.history_deleted")
        assert ev.metadata["findings_kept"] == 1

    def test_a_pentester_cannot_delete_a_completed_import(self, w, p1c):
        job = prepared(p1c, w.eng_a, [GOOD])
        commit(p1c, job)
        assert p1c.get(f"{API}/imports/{job['id']}").json()["can_delete"] is False
        assert p1c.delete(f"{API}/imports/{job['id']}").status_code in (403, 409)
        assert ImportJob.objects.filter(pk=job["id"]).exists()

    def test_running_imports_cannot_be_deleted(self, w, admin_client, p1c):
        job = prepared(p1c, w.eng_a, [GOOD])  # previewed, not run
        assert admin_client.delete(f"{API}/imports/{job['id']}").status_code == 409

    def test_clear_history_removes_finished_imports_only(self, w, admin_client, p1c):
        done = prepared(p1c, w.eng_a, [GOOD])
        commit(p1c, done)
        waiting = prepared(p1c, w.eng_a, [GOOD])
        r = admin_client.post(f"{API}/imports/clear-history", {}, format="json")
        assert r.status_code == 200 and r.json() == {"deleted": 1}
        assert not ImportJob.objects.filter(pk=done["id"]).exists()
        assert ImportJob.objects.filter(pk=waiting["id"]).exists()
        assert Finding.objects.filter(title="SQL injection").exists()

    def test_clear_history_needs_the_permission(self, p1c):
        assert p1c.post(f"{API}/imports/clear-history", {}, format="json").status_code == 403


@pytest.mark.django_db
class TestNeedsReview:
    def test_list_flags_and_filters_findings_with_gaps(self, w, p1c):
        import_everything(p1c, w, [GOOD, GAPS[1]])
        rows = p1c.get(f"{API}/findings?page_size=50").json()["results"]
        flags = {r["title"]: r["needs_review"] for r in rows}
        assert flags == {"SQL injection": False, "Has a title": True}
        only = p1c.get(f"{API}/findings?needs_review=true").json()["results"]
        assert [r["title"] for r in only] == ["Has a title"]

    def test_flag_clears_when_the_gaps_are_reviewed(self, w, p1c):
        import_everything(p1c, w, [GAPS[1]])
        f = Finding.objects.get(title="Has a title")
        v = p1c.get(f"{API}/findings/{f.pk}").json()["version"]
        p1c.post(f"{API}/findings/{f.pk}/import-reviewed", {"version": v}, format="json")
        assert p1c.get(f"{API}/findings?needs_review=true").json()["results"] == []


@pytest.mark.django_db
class TestReferences:
    def finding(self, w, p1c):
        import_everything(p1c, w, [GAPS[1]])
        f = Finding.objects.get(title="Has a title")
        return f, p1c.get(f"{API}/findings/{f.pk}").json()["version"]

    def test_a_reference_without_a_label_uses_the_link_as_label(self, w, p1c):
        f, v = self.finding(w, p1c)
        r = p1c.patch(f"{API}/findings/{f.pk}", {"version": v,
                      "references": [{"label": "", "url": "https://nvd.nist.gov/vuln/detail/cve-2026-98432"}]}, format="json")
        assert r.status_code == 200
        assert r.json()["references"] == [{"label": "https://nvd.nist.gov/vuln/detail/cve-2026-98432",
                                           "url": "https://nvd.nist.gov/vuln/detail/cve-2026-98432"}]

    def test_a_bad_link_is_refused_with_a_field_error(self, w, p1c):
        f, v = self.finding(w, p1c)
        r = p1c.patch(f"{API}/findings/{f.pk}", {"version": v, "references": [{"label": "x", "url": "N/A"}]}, format="json")
        assert r.status_code == 400 and "references" in r.json()["error"]["fields"]
