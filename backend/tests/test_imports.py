"""Phase 8: CSV import (upload, map, validate, duplicates, commit, rollback) and its isolation."""

import csv
import io
import time
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.service import verify_chain
from apps.engagements import services as eng_services
from apps.findings.models import CWE, Finding, FindingCounter
from apps.findings.services import dedupe_hash
from apps.imports import mapping as mapping_rules
from apps.imports import parsing, services
from apps.imports.models import ImportJob, ImportMapping
from tests.conftest import make_role, make_user, signed_in
from tests.test_findings import API
from tests.world import build_world

HEADER = ["Title", "Severity", "Description", "Recommendation", "Asset", "CWE", "Date", "Endpoint"]
GOOD = ["SQL injection", "High", "Concatenated query.", "Parameterise.", "Acme shop", "CWE-89", "2026-11-01", "/search"]


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


def csv_bytes(rows, header=HEADER, delimiter=",", encoding="utf-8"):
    out = io.StringIO()
    csv.writer(out, delimiter=delimiter, lineterminator="\r\n").writerows([header, *rows])
    return out.getvalue().encode(encoding)


def upload(client, eng, data, name="findings.csv"):
    return client.post(
        f"{API}/imports",
        {"engagement": str(eng.pk), "file": SimpleUploadedFile(name, data, "text/csv")},
        format="multipart",
    )


def new_job(client, eng, rows=None, **kw):
    r = upload(client, eng, csv_bytes(rows if rows is not None else [GOOD], **kw))
    assert r.status_code == 201, r.content
    return r.json()


def jurl(job, tail=""):
    return f"{API}/imports/{job['id']}{tail}"


def refetch(client, job):
    return client.get(jurl(job)).json()


COLUMNS = {"title": "Title", "severity": "Severity", "description": "Description", "recommendation": "Recommendation",
           "asset": "Asset", "cwe": "CWE", "discovered_at": "Date", "endpoint": "Endpoint"}  # fmt: skip


def map_job(client, job, column_map=None, value_map=None, **kw):
    r = client.post(
        jurl(job, "/mapping"), {"column_map": column_map or COLUMNS, "value_map": value_map or {}, **kw}, format="json"
    )
    assert r.status_code == 202, r.content
    return refetch(client, job)


def commit(client, job, mode="valid_rows_only", duplicates="skip"):
    return client.post(jurl(job, "/commit"), {"mode": mode, "duplicates": duplicates}, format="json")


def rows(client, job, query=""):
    r = client.get(jurl(job, f"/rows{query}"))
    assert r.status_code == 200, r.content
    return r.json()["results"]


def prepared(client, eng, data_rows, **kw):
    return map_job(client, new_job(client, eng, data_rows), **kw)


@pytest.mark.django_db
class TestUpload:
    def test_upload_is_read_and_ready_for_mapping(self, w, p1c):
        job = new_job(p1c, w.eng_a)
        assert job["status"] == "parsed" and job["headers"] == HEADER and job["counts"] == {"total": 1}
        assert job["encoding"] == "utf-8" and job["delimiter"] == "," and len(job["file_sha256"]) == 64
        assert job["suggested_mapping"]["title"] == "Title" and job["suggested_mapping"]["asset"] == "Asset"
        assert job["sample"][0][0] == "SQL injection"
        assert AuditEvent.objects.filter(action="import.uploaded", engagement_id=w.eng_a.pk).exists()

    def test_remediation_cannot_import(self, w, r1c):
        assert upload(r1c, w.eng_a, csv_bytes([GOOD])).status_code == 403

    def test_cannot_import_into_another_engagement(self, w, p1c):
        assert upload(p1c, w.eng_b, csv_bytes([GOOD])).status_code == 400  # not in scope: reported as unknown

    @pytest.mark.parametrize("name,data", [("x.exe", b"a,b\n1,2\n"), ("x.csv", b""), ("x.pdf", b"%PDF")])
    def test_bad_file_names_and_empty_files(self, w, p1c, name, data):
        assert upload(p1c, w.eng_a, data, name).status_code == 400

    def test_too_big_is_refused(self, w, p1c, monkeypatch):
        monkeypatch.setattr(parsing, "MAX_BYTES", 100)
        assert upload(p1c, w.eng_a, csv_bytes([GOOD] * 5)).status_code == 400

    def test_archived_engagement_is_refused(self, w, p1c, admin):
        eng_services.change_status(None, admin, w.eng_a, "cancelled", w.eng_a.version)
        w.eng_a.refresh_from_db()
        eng_services.archive_engagement(None, admin, w.eng_a, w.eng_a.version)
        assert upload(p1c, w.eng_a, csv_bytes([GOOD])).status_code == 409

    def test_second_upload_while_one_is_working_is_refused(self, w, p1c, admin):
        ImportJob.objects.create(
            engagement=w.eng_a,
            uploaded_by=w.p1,
            original_name="x.csv",
            file_sha256="0" * 64,
            file_size=1,
            status="importing",
        )
        assert upload(p1c, w.eng_a, csv_bytes([GOOD])).status_code == 409


@pytest.mark.django_db
class TestParsing:
    def job_for(self, w, p1c, data):
        r = upload(p1c, w.eng_a, data)
        assert r.status_code == 201
        return r.json()

    def test_semicolon_tab_and_bom(self, w, p1c):
        assert self.job_for(w, p1c, csv_bytes([GOOD], delimiter=";"))["delimiter"] == ";"
        assert self.job_for(w, p1c, csv_bytes([GOOD], delimiter="\t"))["delimiter"] == "\t"
        bom = self.job_for(w, p1c, b"\xef\xbb\xbf" + csv_bytes([GOOD]))
        assert bom["headers"][0] == "Title" and bom["status"] == "parsed"

    def test_windows_1252(self, w, p1c):
        data = csv_bytes([["Café ünïcode", "high", "d", "r", "", "", "", ""]], encoding="cp1252")
        job = self.job_for(w, p1c, data)
        assert job["encoding"] == "windows-1252" and job["sample"][0][0] == "Café ünïcode"

    def test_ragged_rows_and_blank_lines(self, w, p1c):
        data = b"Title,Severity,Description\r\nShort row,high\r\n\r\n,,\r\nFull,low,text\r\n"
        job = self.job_for(w, p1c, data)
        assert job["counts"]["total"] == 2 and job["sample"][0] == ["Short row", "high", ""]

    @pytest.mark.parametrize(
        "data,message",
        [
            (b"Title,Severity\r\n", "no rows"),
            (b"Title,Title\r\nx,y\r\n", "both named"),
            (b",Severity\r\nx,y\r\n", "no name"),
            (b"<html><body>hi</body></html>", "not a CSV"),
            (b"a,b\r\n\x00\x01,2\r\n", "CSV text"),
        ],
    )
    def test_unusable_files_fail_with_a_message(self, w, p1c, data, message):
        job = self.job_for(w, p1c, data)
        assert job["status"] == "failed" and message in job["error"]
        assert AuditEvent.objects.filter(action="import.failed").exists()

    def test_limits(self, w, p1c, monkeypatch):
        monkeypatch.setattr(parsing, "MAX_ROWS", 3)
        assert "more than 3" in self.job_for(w, p1c, csv_bytes([GOOD] * 5))["error"]
        monkeypatch.setattr(parsing, "MAX_COLUMNS", 3)
        assert "columns" in self.job_for(w, p1c, csv_bytes([GOOD]))["error"]


@pytest.mark.django_db
class TestMapping:
    def test_suggest_and_clean(self):
        assert mapping_rules.suggest(["Name", "Risk", "Host", "Fix"]) == {
            "title": "Name",
            "severity": "Risk",
            "asset": "Host",
            "recommendation": "Fix",
        }

    @pytest.mark.parametrize(
        "column_map,key",
        [
            ({"severity": "Severity"}, "title"),
            ({"title": "Title"}, "severity"),
            ({"title": "Nope", "severity": "Severity"}, "title"),
            ({"title": "Title", "severity": "Title"}, "severity"),
            ({"title": "Title", "severity": "Severity", "bogus": "Endpoint"}, "bogus"),
        ],
    )
    def test_bad_mappings_are_400(self, w, p1c, column_map, key):
        job = new_job(p1c, w.eng_a)
        r = p1c.post(jurl(job, "/mapping"), {"column_map": column_map}, format="json")
        assert r.status_code == 400 and key in r.json()["error"]["fields"]

    def test_vector_alone_can_replace_severity(self, w, p1c):
        data = csv_bytes([["Vector only", "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"]], header=["Title", "Vector"])
        job = upload(p1c, w.eng_a, data).json()
        job = map_job(p1c, job, {"title": "Title", "cvss_vector": "Vector"})
        assert job["status"] == "previewed" and rows(p1c, job)[0]["severity"] == "critical"

    def test_remapping_resets_the_rows(self, w, p1c):
        job = prepared(p1c, w.eng_a, [GOOD, ["", "high", "", "", "", "", "", ""]])
        assert job["status"] == "previewed" and job["counts"]["invalid"] == 1
        job = map_job(p1c, job, {**{k: v for k, v in COLUMNS.items() if k != "description"}, "title": "Description"})
        assert job["counts"]["valid"] == 1  # now the description column is the title

    def test_save_and_list_own_mappings_only(self, w, p1c):
        job = new_job(p1c, w.eng_a)
        map_job(p1c, job, save_as="Burp export")
        assert [m["name"] for m in p1c.get(f"{API}/import-mappings").json()] == ["Burp export"]
        assert signed_in(w.p2).get(f"{API}/import-mappings").json() == []
        mid = p1c.get(f"{API}/import-mappings").json()[0]["id"]
        assert signed_in(w.p2).delete(f"{API}/import-mappings/{mid}").status_code == 404
        assert p1c.delete(f"{API}/import-mappings/{mid}").status_code == 204
        assert ImportMapping.objects.count() == 0

    def test_mapping_while_working_or_after_commit_is_refused(self, w, p1c):
        job = prepared(p1c, w.eng_a, [GOOD])
        assert commit(p1c, job).status_code == 202
        assert p1c.post(jurl(job, "/mapping"), {"column_map": COLUMNS}, format="json").status_code == 409


@pytest.mark.django_db
class TestAssetColumn:
    """The Asset column takes the asset's name, its IP address or its URL (the asset identifier)."""

    def test_name_ip_and_url_all_resolve(self, w, p1c, admin):
        from apps.engagements import services as eng_services
        from apps.organisations import services as org_services

        host = org_services.create_asset(None, admin, w.org_a, {"name": "Jump host", "type": "host", "identifier": "10.9.8.7"})
        eng_services.link_asset(None, admin, w.eng_a, host, True, "")
        data = [
            ["By name", "low", "", "", "acme SHOP", "", "", ""],
            ["By url", "low", "", "", "https://shop.acme.test/", "", "", ""],
            ["By ip", "low", "", "", " 10.9.8.7 ", "", "", ""],
            ["By nothing", "low", "", "", "10.9.8.8", "", "", ""],
        ]
        job = prepared(p1c, w.eng_a, data)
        got = {r["row_number"]: r for r in rows(p1c, job)}
        assert job["counts"]["valid"] == 3 and job["counts"]["invalid"] == 1
        assert [e["code"] for e in got[5]["errors"]] == ["unknown_asset"]
        assert "IP address or URL" in got[5]["errors"][0]["message"]
        assert commit(p1c, job).status_code == 202
        from apps.findings.models import Finding

        by_title = {f.title: f.asset_id for f in Finding.objects.filter(engagement=w.eng_a)}
        assert by_title == {"By name": w.asset_a.pk, "By url": w.asset_a.pk, "By ip": host.pk}


@pytest.mark.django_db
class TestValidation:
    def test_each_rule(self, w, p1c):
        bad = [
            ["", "high", "", "", "", "", "", ""],  # no title
            ["T" * 201, "high", "", "", "", "", "", ""],  # long title
            ["Odd severity", "purple", "", "", "", "", "", ""],
            ["Unknown asset", "low", "", "", "Nowhere", "", "", ""],
            ["Unknown CWE", "low", "", "", "", "9999999", "", ""],
            ["Bad date", "low", "", "", "", "", "01/02/2026", ""],
            ["Long endpoint", "low", "", "", "", "", "", "/" * 501],
            ["No severity", "", "", "", "", "", "", ""],
        ]
        job = prepared(p1c, w.eng_a, [GOOD, *bad])
        got = {r["row_number"]: r for r in rows(p1c, job)}
        assert job["counts"] == {"total": 9, "valid": 1, "invalid": 8, "duplicate": 0}
        codes = [[e["code"] for e in r["errors"]] for r in sorted(got.values(), key=lambda r: r["row_number"])[1:]]
        assert codes == [
            ["required"],
            ["too_long"],
            ["invalid_severity"],
            ["unknown_asset"],
            ["unknown_cwe"],
            ["invalid_date"],
            ["too_long"],
            ["required"],
        ]

    def test_aliases_value_map_and_cwe_forms(self, w, p1c):
        data = [
            ["A", "Informational", "", "", "", "89", "", ""],
            ["B", "Sehr hoch", "", "", "", "CWE-79", "", ""],
            ["C", "Moderate", "", "", "", "cwe 20", "", ""],
        ]
        job = prepared(p1c, w.eng_a, data, value_map={"severity": {"Sehr hoch": "critical"}})
        got = {r["title"]: r for r in rows(p1c, job)}
        assert [got[t]["severity"] for t in "ABC"] == ["info", "critical", "medium"] and job["counts"]["valid"] == 3

    def test_cvss_vector_sets_severity_and_conflicts_are_flagged(self, w, p1c):
        v = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
        data = csv_bytes(
            [["Matches", "critical", v], ["Mismatch", "low", v], ["Garbage", "", "CVSS:9/x"]],
            header=["Title", "Severity", "Vector"],
        )
        job = map_job(
            p1c, upload(p1c, w.eng_a, data).json(), {"title": "Title", "severity": "Severity", "cvss_vector": "Vector"}
        )
        got = {r["title"]: [e["code"] for e in r["errors"]] for r in rows(p1c, job)}
        assert got == {"Matches": [], "Mismatch": ["severity_mismatch"], "Garbage": ["invalid_cvss"]}

    def test_references(self, w, p1c):
        data = csv_bytes(
            [["R", "low", "OWASP|https://owasp.org/; https://example.test/a\nftp://bad"]],
            header=["Title", "Severity", "Refs"],
        )
        job = map_job(
            p1c, upload(p1c, w.eng_a, data).json(), {"title": "Title", "severity": "Severity", "references": "Refs"}
        )
        assert [e["code"] for e in rows(p1c, job)[0]["errors"]] == ["invalid_reference"]

    def test_extra_values_in_a_row_are_an_error(self, w, p1c):
        job = prepared(p1c, w.eng_a, [GOOD + ["stray"]])
        assert rows(p1c, job)[0]["errors"][0]["code"] == "too_many_values"


@pytest.mark.django_db
class TestDuplicates:
    def test_duplicates_in_the_file_and_against_the_engagement(self, w, p1c):
        existing = Finding.objects.create(
            ref="RS-F-900001", engagement=w.eng_a, title="Existing one", severity="low", reported_by=w.p1,
            discovered_at=w.today, dedupe_hash=dedupe_hash(w.eng_a.pk, "Existing one", None, "", None),
        )  # fmt: skip
        data = [GOOD, GOOD, ["Existing one", "low", "", "", "", "", "", ""], ["Fresh", "low", "", "", "", "", "", ""]]
        job = prepared(p1c, w.eng_a, data)
        assert job["counts"] == {"total": 4, "valid": 2, "invalid": 0, "duplicate": 2}
        got = sorted(rows(p1c, job), key=lambda r: r["row_number"])
        assert got[1]["duplicate_of"] == {"line": got[0]["row_number"]}
        assert got[2]["duplicate_of"]["finding"]["ref"] == existing.ref
        assert [r["status"] for r in got] == ["valid", "duplicate", "duplicate", "valid"]

    def test_skip_or_import_anyway(self, w, p1c):
        job = prepared(p1c, w.eng_a, [GOOD, GOOD])
        assert commit(p1c, job, duplicates="skip").status_code == 202
        assert Finding.objects.filter(engagement=w.eng_a, source="import").count() == 1
        done = refetch(p1c, job)
        assert done["counts"]["imported"] == 1 and done["counts"]["skipped"] == 1
        job2 = prepared(p1c, w.eng_a, [["Another", "low", "", "", "", "", "", ""]] * 2)
        assert commit(p1c, job2, duplicates="import").status_code == 202
        assert Finding.objects.filter(engagement=w.eng_a, title="Another").count() == 2


@pytest.mark.django_db
class TestCommit:
    def test_valid_rows_become_drafts_with_traceability(self, w, p1c):
        data = [GOOD, ["Second", "low", "", "", "", "", "", ""], ["", "high", "", "", "", "", "", ""]]
        job = prepared(p1c, w.eng_a, data)
        assert commit(p1c, job).status_code == 202
        done = refetch(p1c, job)
        assert done["status"] == "completed" and done["counts"]["imported"] == 2 and done["counts"]["invalid"] == 1
        found = list(Finding.objects.filter(import_job_id=job["id"]).order_by("ref"))
        assert [f.title for f in found] == ["SQL injection", "Second"]
        f = found[0]
        assert f.status == "draft" and f.source == "import" and f.reported_by_id == w.p1.pk and f.version == 1
        assert (
            f.asset_id == w.asset_a.pk
            and f.cwe_id == 89
            and str(f.discovered_at) == "2026-11-01"
            and f.severity == "high"
        )
        assert found[1].ref == f"RS-F-{int(f.ref[5:]) + 1:06d}"
        ev = AuditEvent.objects.get(action="import.committed")
        assert ev.metadata["imported"] == 2 and ev.metadata["first_ref"] == f.ref and ev.engagement_id == w.eng_a.pk
        assert [r["status"] for r in rows(p1c, job)].count("imported") == 2
        assert verify_chain().ok

    def test_imported_findings_are_invisible_to_remediation_until_published(self, w, p1c, r1c):
        job = prepared(p1c, w.eng_a, [GOOD])
        commit(p1c, job)
        f = Finding.objects.get(import_job_id=job["id"])
        assert r1c.get(f"{API}/findings/{f.pk}").status_code == 404
        detail = p1c.get(f"{API}/findings/{f.pk}").json()
        assert detail["imported_from"]["file"] == "findings.csv" and detail["status"] == "draft"

    def test_all_or_nothing_is_refused_with_invalid_rows(self, w, p1c):
        job = prepared(p1c, w.eng_a, [GOOD, ["", "high", "", "", "", "", "", ""]])
        r = commit(p1c, job, mode="all_or_nothing")
        assert r.status_code == 409 and "1 rows have errors" in r.json()["error"]["message"]
        assert Finding.objects.filter(source="import").count() == 0 and refetch(p1c, job)["status"] == "previewed"

    def test_all_or_nothing_commits_when_everything_is_valid(self, w, p1c):
        job = prepared(p1c, w.eng_a, [GOOD, ["Other", "low", "", "", "", "", "", ""]])
        assert commit(p1c, job, mode="all_or_nothing").status_code == 202
        assert Finding.objects.filter(source="import").count() == 2

    def test_failure_mid_import_rolls_back_to_zero_findings(self, w, p1c, monkeypatch):
        job = prepared(p1c, w.eng_a, [[f"Finding {i}", "low", "", "", "", "", "", ""] for i in range(5)])
        before = FindingCounter.objects.filter(pk=1).values_list("last", flat=True).first()
        monkeypatch.setattr(services, "CHUNK", 2)
        real, calls = services.reserve_refs, {"n": 0}

        def flaky(count):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("disk full")
            return real(count)

        monkeypatch.setattr(services, "reserve_refs", flaky)
        commit(p1c, job)
        done = refetch(p1c, job)
        assert done["status"] == "failed" and "rolled back" in done["error"]
        assert Finding.objects.filter(source="import").count() == 0
        assert FindingCounter.objects.filter(pk=1).values_list("last", flat=True).first() == before
        assert not [r for r in rows(p1c, job) if r["status"] == "imported"]
        assert AuditEvent.objects.filter(action="import.failed", outcome="failure").exists()

    def test_asset_removed_after_preview_aborts_all_or_nothing(self, w, p1c):
        from apps.engagements.models import EngagementAsset

        job = prepared(p1c, w.eng_a, [GOOD])
        EngagementAsset.objects.filter(engagement=w.eng_a).update(in_scope=False)
        commit(p1c, job, mode="all_or_nothing")
        assert refetch(p1c, job)["status"] == "failed" and Finding.objects.filter(source="import").count() == 0

    def test_commit_needs_a_preview_and_something_to_import(self, w, p1c):
        job = new_job(p1c, w.eng_a)
        assert commit(p1c, job).status_code == 409  # not mapped yet
        empty = prepared(p1c, w.eng_a, [["", "high", "", "", "", "", "", ""]])
        assert commit(p1c, empty).status_code == 409  # nothing valid

    def test_cannot_commit_twice(self, w, p1c):
        job = prepared(p1c, w.eng_a, [GOOD])
        assert commit(p1c, job).status_code == 202
        assert commit(p1c, job).status_code == 409

    def test_cvss_vector_column_is_scored(self, w, p1c):
        v = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
        job = map_job(
            p1c,
            upload(p1c, w.eng_a, csv_bytes([["Scored", v]], header=["Title", "Vector"])).json(),
            {"title": "Title", "cvss_vector": "Vector"},
        )
        commit(p1c, job)
        f = Finding.objects.get(title="Scored")
        assert f.severity == "critical" and str(f.cvss_score) == "9.8" and f.cvss_version == "3.1"

    def test_fifty_thousand_rows(self, w, p1c):
        data = csv_bytes([[f"Bulk finding {i}", "low", "", "", "", "", "", ""] for i in range(50_000)])
        start = time.monotonic()
        job = map_job(p1c, upload(p1c, w.eng_a, data).json())
        assert job["status"] == "previewed" and job["counts"]["valid"] == 50_000
        commit(p1c, job, mode="all_or_nothing")
        assert refetch(p1c, job)["status"] == "completed"
        assert Finding.objects.filter(import_job_id=job["id"]).count() == 50_000
        assert time.monotonic() - start < 240


@pytest.mark.django_db
class TestAccessAndHousekeeping:
    def test_scoping(self, w, p1c, r1c, admin_client):
        job = new_job(p1c, w.eng_a)
        other = signed_in(w.p2)
        assert other.get(jurl(job)).status_code == 404
        assert other.get(f"{API}/imports").json()["results"] == []
        assert r1c.get(f"{API}/imports").status_code == 403
        assert admin_client.get(jurl(job)).status_code == 200
        assert [j["id"] for j in p1c.get(f"{API}/imports").json()["results"]] == [job["id"]]

    def test_other_users_cannot_drive_the_job(self, w, p1c):
        job = new_job(p1c, w.eng_a)
        other = signed_in(w.p2)
        for tail in ("/mapping", "/commit", "/cancel"):
            assert other.post(jurl(job, tail), {}, format="json").status_code == 404

    def test_view_only_role_cannot_change_a_job(self, w, p1c, admin):
        viewer = make_user("viewer@example.com", make_role("ImportViewer", ["engagements.view", "imports.view"]))
        from apps.engagements.models import EngagementMembership

        EngagementMembership.objects.create(engagement=w.eng_a, user=viewer, added_by=admin)
        job = new_job(p1c, w.eng_a)
        vc = signed_in(viewer)
        assert vc.get(jurl(job)).status_code == 200
        assert vc.post(jurl(job, "/cancel"), {}, format="json").status_code == 403

    def test_cancel_removes_the_file(self, w, p1c):
        job = new_job(p1c, w.eng_a)
        assert p1c.post(jurl(job, "/cancel"), {}, format="json").json()["status"] == "cancelled"
        row = ImportJob.objects.get(pk=job["id"])
        assert row.storage_key == "" and row.file_purged_at
        assert p1c.post(jurl(job, "/cancel"), {}, format="json").status_code == 409

    def test_cannot_cancel_after_commit(self, w, p1c):
        job = prepared(p1c, w.eng_a, [GOOD])
        commit(p1c, job)
        assert p1c.post(jurl(job, "/cancel"), {}, format="json").status_code == 409

    def test_rows_filter_and_paging(self, w, p1c):
        job = prepared(
            p1c, w.eng_a, [GOOD, ["", "high", "", "", "", "", "", ""], ["Other", "low", "", "", "", "", "", ""]]
        )
        assert {r["status"] for r in rows(p1c, job, "?status=invalid")} == {"invalid"}
        assert {r["status"] for r in rows(p1c, job, "?status=invalid,duplicate")} == {
            "invalid"
        }  # none are duplicates here
        assert len(rows(p1c, job, "?status=invalid,valid,nonsense")) == 3
        body = p1c.get(jurl(job, "/rows?page_size=2")).json()
        assert body["count"] == 3 and len(body["results"]) == 2
        assert body["results"][0]["cells"]["Title"] == "SQL injection"

    def test_error_report_csv(self, w, p1c):
        job = prepared(p1c, w.eng_a, [GOOD, ['=HYPERLINK("x")', "purple", "", "", "", "", "", ""]])
        r = p1c.get(jurl(job, "/errors.csv"))
        assert r.status_code == 200 and "attachment" in r["Content-Disposition"] and r["Cache-Control"] == "no-store"
        table = list(csv.reader(io.StringIO(b"".join(r.streaming_content).decode())))
        assert table[0][:3] == ["line", "status", "problems"] and len(table) == 2
        assert "not a severity" in table[1][2] and table[1][3].startswith("'=")

    def test_template_download(self, w, p1c, r1c):
        r = p1c.get(f"{API}/imports/template.csv")
        body = b"".join(r.streaming_content)
        assert r.status_code == 200 and b"Title,Severity" in body
        assert b"Acme shop" in body and b"10.0.0.5" in body and b"https://shop.acme.test" in body
        assert r1c.get(f"{API}/imports/template.csv").status_code == 403

    def test_cleanup_closes_stuck_jobs_and_purges_old_files(self, w, p1c):
        stuck = ImportJob.objects.create(
            engagement=w.eng_a,
            uploaded_by=w.p1,
            original_name="s.csv",
            file_sha256="0" * 64,
            file_size=1,
            status="importing",
        )
        ImportJob.objects.filter(pk=stuck.pk).update(updated_at=timezone.now() - timedelta(hours=2))
        job = new_job(p1c, w.eng_a)
        ImportJob.objects.filter(pk=job["id"]).update(
            status="completed", finished_at=timezone.now() - timedelta(days=31)
        )
        assert services.cleanup() == {"stuck": 1, "purged": 1}
        stuck.refresh_from_db()
        assert stuck.status == "failed" and ImportJob.objects.get(pk=job["id"]).storage_key == ""
        assert services.cleanup() == {"stuck": 0, "purged": 0}

    def test_tasks_are_scheduled(self):
        from django.conf import settings

        assert "imports.cleanup" in {v["task"] for v in settings.CELERY_BEAT_SCHEDULE.values()}

    def test_cwe_table_has_what_the_tests_use(self):
        assert CWE.objects.filter(pk__in=[20, 79, 89]).count() == 3
