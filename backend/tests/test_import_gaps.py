"""Imports with gaps: rows with fixable problems become drafts marked for review; reference downloads."""

import pytest

from apps.audit.models import AuditEvent
from apps.findings.models import Finding
from tests.conftest import signed_in
from tests.test_findings import API
from tests.test_imports import GOOD, commit, prepared, refetch
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


# title missing, unknown asset, unknown CWE, bad date, bad severity: all fixable later
GAPS = [
    ["", "", "Missing title and severity.", "", "No such host", "CWE-999999", "not-a-date", ""],
    ["Has a title", "banana", "Bad severity.", "", "", "", "", ""],
]


def import_everything(client, w, rows):
    job = prepared(client, w.eng_a, rows)
    assert commit(client, job, mode="everything").status_code == 202
    return job


@pytest.mark.django_db
class TestIncompleteRows:
    def test_counts_report_how_many_rows_are_incomplete(self, w, p1c):
        job = prepared(p1c, w.eng_a, [GOOD, *GAPS])
        c = job["counts"]
        assert c["valid"] == 1 and c["invalid"] == 2 and c["incomplete"] == 2

    def test_everything_mode_imports_gaps_as_flagged_drafts(self, w, p1c):
        job = import_everything(p1c, w, [GOOD, *GAPS])
        done = refetch(p1c, job)
        assert done["status"] == "completed" and done["counts"]["imported"] == 3
        flagged = Finding.objects.filter(import_job_id=job["id"]).exclude(import_issues=[])
        assert flagged.count() == 2
        first = flagged.get(title__startswith="Untitled finding (line ")
        assert first.status == "draft" and first.severity == "info" and first.asset_id is None and first.cwe_id is None
        assert {i["field"] for i in first.import_issues} >= {"title", "asset", "cwe", "discovered_at"}
        assert Finding.objects.get(import_job_id=job["id"], title="SQL injection").import_issues == []

    def test_other_modes_still_skip_invalid_rows(self, w, p1c):
        job = prepared(p1c, w.eng_a, [GOOD, *GAPS])
        assert commit(p1c, job, mode="valid_rows_only").status_code == 202
        assert Finding.objects.filter(source="import").count() == 1

    def test_unstorable_rows_are_never_imported(self, w, p1c):
        too_long = ["T" * 201, "high", "", "", "", "", "", ""]
        job = prepared(p1c, w.eng_a, [too_long])
        assert job["counts"].get("incomplete", 0) == 0
        assert commit(p1c, job, mode="everything").status_code == 409  # nothing importable
        assert Finding.objects.filter(source="import").count() == 0

    def test_publish_is_blocked_until_gaps_are_fixed_or_reviewed(self, w, p1c):
        import_everything(p1c, w, [GAPS[1]])
        f = Finding.objects.get(title="Has a title")
        url = f"{API}/findings/{f.pk}"
        body = {"description": "Now described.", "recommendation": "Fix it."}
        d = p1c.get(url).json()
        assert d["import_issues"][0]["field"] == "severity"
        d = p1c.patch(url, {**body, "version": d["version"]}, format="json").json()
        r = p1c.post(f"{url}/publish", {"version": d["version"]}, format="json")
        assert r.status_code == 409 and "imported with gaps" in r.json()["error"]["message"]
        # editing the field that had the gap clears it
        d = p1c.patch(url, {"severity": "high", "version": d["version"]}, format="json").json()
        assert d["import_issues"] == []
        assert p1c.post(f"{url}/publish", {"version": d["version"]}, format="json").status_code == 200

    def test_mark_reviewed_clears_gaps_and_is_audited(self, w, p1c):
        import_everything(p1c, w, [GAPS[1]])
        f = Finding.objects.get(title="Has a title")
        url = f"{API}/findings/{f.pk}"
        d = p1c.get(url).json()
        r = p1c.post(f"{url}/import-reviewed", {"version": d["version"]}, format="json")
        assert r.status_code == 200 and r.json()["import_issues"] == []
        ev = AuditEvent.objects.filter(action="finding.import_reviewed", entity_id=str(f.pk)).get()
        assert ev.metadata["fields"] == ["severity"]


@pytest.mark.django_db
class TestReferenceDownloads:
    def test_cvss_guide_lists_every_band(self, p1c):
        r = p1c.get(f"{API}/imports/cvss-guide.csv")
        assert r.status_code == 200 and r["Content-Type"].startswith("text/csv")
        text = b"".join(r.streaming_content).decode()
        for line in ("9.0 to 10.0,Critical,critical", "7.0 to 8.9,High,high", "4.0 to 6.9,Medium,medium",
                     "0.1 to 3.9,Low,low", "0.0,Info,info"):  # fmt: skip
            assert line in text

    def test_cwe_list_downloads_the_seeded_list(self, p1c):
        r = p1c.get(f"{API}/imports/cwe-list.csv")
        text = b"".join(r.streaming_content).decode()
        assert r.status_code == 200 and "CWE-79,79," in text and "CWE-89,89," in text

    def test_downloads_need_import_permission(self, api):
        assert api.get(f"{API}/imports/cwe-list.csv").status_code in (401, 403)
