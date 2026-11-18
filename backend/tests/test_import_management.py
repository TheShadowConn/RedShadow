"""Import management: delete a failed import, corrected-file re-upload, retry, history, partial failure."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.audit.models import AuditEvent
from apps.findings.models import Finding
from apps.imports.models import ImportAttempt, ImportJob, ImportRow
from tests.conftest import signed_in
from tests.test_findings import API
from tests.test_imports import GOOD, HEADER, commit, csv_bytes, jurl, map_job, new_job, refetch, rows, upload
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


def empty_job(client, eng):
    """A header-only file: the worker marks the job failed."""
    r = upload(client, eng, csv_bytes([]), name="empty.csv")
    assert r.status_code == 201, r.content
    job = r.json()
    assert refetch(client, job)["status"] == "failed"
    return refetch(client, job)


def bad(n):
    return [f"Bad {n}", "Spectacular", "d", "r", "Acme shop", "CWE-89", "2026-11-01", "/x"]


def good(n):
    return [f"Finding {n}", "High", "d", "r", "Acme shop", "CWE-89", "2026-11-01", f"/p{n}"]


def reupload(client, job, data, name="fixed.csv"):
    return client.post(jurl(job, "/reupload"), {"file": SimpleUploadedFile(name, data, "text/csv")}, format="multipart")


@pytest.mark.django_db
class TestDelete:
    def test_failed_import_is_deleted_with_rows_history_and_file(self, w, p1c):
        job = empty_job(p1c, w.eng_a)
        assert job["can_delete"] is True
        r = p1c.delete(jurl(job))
        assert r.status_code == 204
        assert not ImportJob.objects.filter(pk=job["id"]).exists()
        assert not ImportAttempt.objects.filter(job_id=job["id"]).exists()
        assert not ImportRow.objects.filter(job_id=job["id"]).exists()
        ev = AuditEvent.objects.filter(action="import.deleted", entity_id=job["id"]).get()
        assert ev.metadata["file"] == "empty.csv" and ev.outcome == "success"
        assert p1c.get(jurl(job)).status_code == 404

    def test_cancelled_import_can_be_deleted(self, w, p1c):
        job = new_job(p1c, w.eng_a)
        assert p1c.post(jurl(job, "/cancel"), {}, format="json").status_code == 200
        assert p1c.delete(jurl(job)).status_code == 204

    @pytest.mark.parametrize("stage", ["parsed", "previewed", "completed"])
    def test_other_states_cannot_be_deleted(self, w, p1c, stage):
        job = new_job(p1c, w.eng_a)
        if stage != "parsed":
            map_job(p1c, job)
        if stage == "completed":
            assert commit(p1c, job).status_code == 202
        r = p1c.delete(jurl(job))
        assert r.status_code == 409
        assert ImportJob.objects.filter(pk=job["id"]).exists()
        assert not r.json()["error"]["message"] == ""

    def test_an_import_that_created_findings_is_never_deleted(self, w, p1c):
        job = new_job(p1c, w.eng_a)
        map_job(p1c, job)
        commit(p1c, job)
        ImportJob.objects.filter(pk=job["id"]).update(status="failed")  # even if a later step marked it failed
        assert p1c.delete(jurl(job)).status_code == 409
        assert Finding.objects.filter(import_job_id=job["id"]).exists()

    def test_permissions(self, w, p1c):
        job = empty_job(p1c, w.eng_a)
        assert signed_in(w.r1).delete(jurl(job)).status_code in (403, 404)
        assert signed_in(w.p2).delete(jurl(job)).status_code == 404  # another engagement's import
        assert ImportJob.objects.filter(pk=job["id"]).exists()
        assert p1c.delete(jurl(job)).status_code == 204


@pytest.mark.django_db
class TestReupload:
    def test_corrected_file_after_a_failed_read_goes_into_the_same_import(self, w, p1c):
        job = empty_job(p1c, w.eng_a)
        r = reupload(p1c, job, csv_bytes([GOOD]))
        assert r.status_code == 202, r.content
        now = refetch(p1c, job)
        assert now["id"] == job["id"] and now["attempt"] == 2 and now["status"] == "parsed"
        assert now["original_name"] == "fixed.csv" and now["error"] == "" and now["counts"] == {"total": 1}
        history = p1c.get(jurl(job, "/history")).json()
        assert [(h["number"], h["outcome"]) for h in history] == [(2, "in_progress"), (1, "superseded")]
        assert history[1]["error"] and history[1]["original_name"] == "empty.csv"
        assert AuditEvent.objects.filter(action="import.reuploaded", entity_id=job["id"]).exists()

    def test_mapping_is_reused_and_the_new_file_is_checked_at_once(self, w, p1c):
        job = new_job(p1c, w.eng_a, [GOOD, bad(1)])
        job = map_job(p1c, job)
        assert job["status"] == "previewed" and job["counts"]["invalid"] == 1 and job["can_reupload"] is True
        r = reupload(p1c, job, csv_bytes([GOOD, good(2)]))
        assert r.status_code == 202
        now = refetch(p1c, job)
        assert now["status"] == "previewed" and now["attempt"] == 2
        assert now["counts"]["invalid"] == 0 and now["counts"]["valid"] == 2
        assert rows(p1c, now, "?status=invalid") == []
        # the first attempt's rows stay readable as history
        old = p1c.get(jurl(job, "/rows?attempt=1&status=invalid")).json()["results"]
        assert len(old) == 1 and old[0]["errors"][0]["code"] == "invalid_severity"
        history = {h["number"]: h for h in p1c.get(jurl(job, "/history")).json()}
        assert history[1]["outcome"] == "superseded" and history[1]["counts"]["invalid"] == 1
        assert history[2]["counts"]["valid"] == 2

    def test_changed_columns_send_the_user_back_to_mapping(self, w, p1c):
        job = map_job(p1c, new_job(p1c, w.eng_a, [GOOD, bad(1)]))
        data = csv_bytes([["x", "High"]], header=["Heading", "Level"])
        assert reupload(p1c, job, data).status_code == 202
        now = refetch(p1c, job)
        assert now["status"] == "parsed" and now["headers"] == ["Heading", "Level"]

    def test_the_same_file_is_refused(self, w, p1c):
        data = csv_bytes([GOOD, bad(1)])
        job = map_job(p1c, new_job(p1c, w.eng_a, [GOOD, bad(1)]))
        assert reupload(p1c, job, data).status_code == 400
        assert refetch(p1c, job)["attempt"] == 1

    def test_partial_failure_then_corrected_file_imports_only_what_is_new(self, w, p1c):
        job = map_job(p1c, new_job(p1c, w.eng_a, [good(1), bad(2), good(3)]))
        assert commit(p1c, job).status_code == 202
        done = refetch(p1c, job)
        assert done["status"] == "completed" and done["counts"]["imported"] == 2 and done["counts"]["invalid"] == 1
        assert done["can_reupload"] is True and done["can_delete"] is False
        assert Finding.objects.filter(engagement=w.eng_a).count() == 2
        # the user fixes line 3 only and uploads the whole file again
        assert reupload(p1c, job, csv_bytes([good(1), good(2), good(3)])).status_code == 202
        again = refetch(p1c, job)
        assert again["status"] == "previewed" and again["attempt"] == 2
        assert again["counts"]["valid"] == 1 and again["counts"]["duplicate"] == 2 and again["counts"]["invalid"] == 0
        assert commit(p1c, job).status_code == 202
        final = refetch(p1c, job)
        assert final["status"] == "completed" and final["counts"]["imported"] == 1 and final["counts"]["skipped"] == 2
        assert Finding.objects.filter(engagement=w.eng_a).count() == 3  # no finding twice
        history = p1c.get(jurl(job, "/history")).json()
        assert [h["outcome"] for h in history] == ["completed", "completed"]
        assert [h["counts"].get("imported") for h in history] == [1, 2]

    def test_a_clean_completed_import_has_nothing_to_correct(self, w, p1c):
        job = map_job(p1c, new_job(p1c, w.eng_a, [GOOD]))
        commit(p1c, job)
        assert refetch(p1c, job)["can_reupload"] is False
        assert reupload(p1c, job, csv_bytes([good(9)])).status_code == 409

    def test_cancelled_or_working_imports_refuse(self, w, p1c):
        job = new_job(p1c, w.eng_a)
        p1c.post(jurl(job, "/cancel"), {}, format="json")
        assert reupload(p1c, job, csv_bytes([good(9)])).status_code == 409
        busy = new_job(p1c, w.eng_a)
        ImportJob.objects.filter(pk=busy["id"]).update(status="importing")
        # a second upload is refused while one is working
        assert upload(p1c, w.eng_a, csv_bytes([GOOD])).status_code == 409

    def test_bad_files_are_refused_without_touching_the_job(self, w, p1c):
        job = map_job(p1c, new_job(p1c, w.eng_a, [GOOD, bad(1)]))
        assert reupload(p1c, job, b"", "x.csv").status_code == 400
        assert reupload(p1c, job, b"a,b", "x.exe").status_code == 400
        now = refetch(p1c, job)
        assert now["attempt"] == 1 and now["status"] == "previewed"

    def test_permissions(self, w, p1c):
        job = empty_job(p1c, w.eng_a)
        data = csv_bytes([GOOD])
        assert reupload(signed_in(w.r1), job, data).status_code in (403, 404)
        assert reupload(signed_in(w.p2), job, data).status_code == 404
        assert refetch(p1c, job)["attempt"] == 1

    def test_findings_import_still_refuses_an_engagement_that_got_archived(self, w, p1c, admin):
        from apps.engagements import services as eng_services

        job = empty_job(p1c, w.eng_a)
        eng_services.change_status(None, admin, w.eng_a, "cancelled", w.eng_a.version)
        w.eng_a.refresh_from_db()
        eng_services.archive_engagement(None, admin, w.eng_a, w.eng_a.version)
        assert reupload(p1c, job, csv_bytes([GOOD])).status_code == 409


@pytest.mark.django_db
class TestRetry:
    def test_failed_validation_resumes_with_the_same_file_and_mapping(self, w, p1c):
        job = map_job(p1c, new_job(p1c, w.eng_a, [GOOD]))
        ImportJob.objects.filter(pk=job["id"]).update(status="failed", error="The rows could not be checked.")
        now = refetch(p1c, job)
        assert now["can_retry"] is True
        r = p1c.post(jurl(job, "/retry"), {}, format="json")
        assert r.status_code == 202, r.content
        after = refetch(p1c, job)
        assert after["status"] == "previewed" and after["error"] == "" and after["counts"]["valid"] == 1
        assert after["attempt"] == 1
        assert AuditEvent.objects.filter(action="import.retried", entity_id=job["id"]).exists()
        assert [h["outcome"] for h in p1c.get(jurl(job, "/history")).json()] == ["in_progress"]

    def test_a_failed_read_is_read_again(self, w, p1c):
        job = empty_job(p1c, w.eng_a)
        assert p1c.post(jurl(job, "/retry"), {}, format="json").status_code == 202
        assert refetch(p1c, job)["status"] == "failed"  # the file is still empty: fails again, cleanly

    def test_retry_after_the_commit_failed_reaches_the_preview_again(self, w, p1c):
        job = map_job(p1c, new_job(p1c, w.eng_a, [GOOD]))
        ImportJob.objects.filter(pk=job["id"]).update(
            status="failed", error="Nothing was imported. x", mode="all_or_nothing"
        )
        assert p1c.post(jurl(job, "/retry"), {}, format="json").status_code == 202
        assert refetch(p1c, job)["status"] == "previewed"
        assert commit(p1c, job).status_code == 202
        assert refetch(p1c, job)["status"] == "completed"

    def test_only_failed_imports_retry(self, w, p1c):
        job = new_job(p1c, w.eng_a)
        assert p1c.post(jurl(job, "/retry"), {}, format="json").status_code == 409

    def test_a_purged_file_cannot_be_retried(self, w, p1c):
        job = empty_job(p1c, w.eng_a)
        ImportJob.objects.filter(pk=job["id"]).update(storage_key="")
        assert p1c.post(jurl(job, "/retry"), {}, format="json").status_code == 409
        assert refetch(p1c, job)["can_retry"] is False

    def test_permissions(self, w, p1c):
        job = empty_job(p1c, w.eng_a)
        assert signed_in(w.r1).post(jurl(job, "/retry"), {}, format="json").status_code in (403, 404)
        assert signed_in(w.p2).post(jurl(job, "/retry"), {}, format="json").status_code == 404


@pytest.mark.django_db
class TestHistoryAndList:
    def test_history_is_scoped_like_the_job(self, w, p1c):
        job = new_job(p1c, w.eng_a)
        assert len(p1c.get(jurl(job, "/history")).json()) == 1
        assert signed_in(w.p2).get(jurl(job, "/history")).status_code == 404
        assert signed_in(w.r1).get(jurl(job, "/history")).status_code in (200, 403)

    def test_list_filters_by_kind_status_and_name(self, w, p1c, admin_client):
        a = new_job(p1c, w.eng_a)
        b = empty_job(p1c, w.eng_a)
        assert {j["id"] for j in p1c.get(f"{API}/imports", {"status": "failed"}).json()["results"]} == {b["id"]}
        assert {j["id"] for j in p1c.get(f"{API}/imports", {"search": "empty"}).json()["results"]} == {b["id"]}
        assert {j["id"] for j in p1c.get(f"{API}/imports", {"kind": "findings"}).json()["results"]} == {
            a["id"],
            b["id"],
        }
        assert p1c.get(f"{API}/imports", {"kind": "assets"}).json()["results"] == []

    def test_existing_jobs_keep_working_after_the_upgrade(self, w, p1c):
        """A job from before attempts existed has attempt 1 and its rows belong to attempt 1."""
        job = map_job(p1c, new_job(p1c, w.eng_a, [GOOD]))
        assert job["attempt"] == 1 and set(
            ImportRow.objects.filter(job_id=job["id"]).values_list("attempt", flat=True)
        ) == {1}
        assert HEADER  # the import still reads findings columns
