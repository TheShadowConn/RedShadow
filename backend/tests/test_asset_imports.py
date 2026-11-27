"""Asset CSV import: matching by identifier, non-onboarded assets, duplicates, partial failure, safety."""

import csv
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.audit.models import AuditEvent
from apps.imports.models import ImportJob
from apps.organisations import services as org_services
from apps.organisations.models import Asset, AssetIdentifier
from tests.conftest import signed_in
from tests.test_findings import API
from tests.world import build_world

HEADER = ["Name", "Type", "Env", "Criticality", "IP", "Hostname", "URL", "Tags"]
COLUMNS = {
    "name": "Name", "type": "Type", "environment": "Env", "criticality": "Criticality",
    "ip": "IP", "hostname": "Hostname", "url": "URL", "tags": "Tags",
}  # fmt: skip


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)


@pytest.fixture
def w(admin):
    return build_world(admin)


def csv_bytes(rows, header=HEADER):
    out = io.StringIO()
    csv.writer(out, lineterminator="\r\n").writerows([header, *rows])
    return out.getvalue().encode()


def upload(client, org, rows, header=HEADER, name="assets.csv"):
    return client.post(
        f"{API}/imports",
        {
            "kind": "assets",
            "organisation": str(org.pk),
            "file": SimpleUploadedFile(name, csv_bytes(rows, header), "text/csv"),
        },
        format="multipart",
    )


def prepared(client, org, rows, **kw):
    r = upload(client, org, rows, **kw)
    assert r.status_code == 201, r.content
    job = r.json()
    r = client.post(f"{API}/imports/{job['id']}/mapping", {"column_map": COLUMNS, "value_map": {}}, format="json")
    assert r.status_code == 202, r.content
    return client.get(f"{API}/imports/{job['id']}").json()


def commit(client, job, mode="valid_rows_only"):
    return client.post(f"{API}/imports/{job['id']}/commit", {"mode": mode, "duplicates": "skip"}, format="json")


def row_list(client, job, query=""):
    return client.get(f"{API}/imports/{job['id']}/rows{query}").json()["results"]


def by_line(client, job):
    return {r["row_number"]: r for r in row_list(client, job, "?page_size=100")}


@pytest.mark.django_db
class TestUploadAndMapping:
    def test_upload_reads_the_file_and_suggests_columns(self, w, admin_client):
        r = upload(admin_client, w.org_a, [["Web", "Host", "prod", "3", "10.1.0.1", "web.acme.test", "", ""]])
        assert r.status_code == 201
        job = r.json()
        assert job["kind"] == "assets" and job["engagement"] is None and job["organisation"]["id"] == str(w.org_a.pk)
        assert job["status"] == "parsed" and job["attempt"] == 1
        assert job["suggested_mapping"]["ip"] == "IP" and job["suggested_mapping"]["hostname"] == "Hostname"
        assert AuditEvent.objects.filter(action="import.uploaded", entity_id=job["id"]).exists()

    def test_pentester_cannot_import_assets_or_see_asset_jobs(self, w, admin_client):
        job = upload(admin_client, w.org_a, [["a", "", "", "", "10.1.0.2", "", "", ""]]).json()
        c = signed_in(w.p1)
        assert upload(c, w.org_a, [["a", "", "", "", "10.1.0.3", "", "", ""]]).status_code in (400, 403)
        assert c.get(f"{API}/imports/{job['id']}").status_code == 404
        assert job["id"] not in [j["id"] for j in c.get(f"{API}/imports").json()["results"]]
        assert (
            c.post(f"{API}/imports/{job['id']}/commit", {"mode": "valid_rows_only"}, format="json").status_code == 404
        )

    def test_mapping_needs_an_identifier_column(self, w, admin_client):
        job = upload(admin_client, w.org_a, [["a", "Host", "", "", "10.1.0.4", "", "", ""]]).json()
        r = admin_client.post(
            f"{API}/imports/{job['id']}/mapping", {"column_map": {"name": "Name"}, "value_map": {}}, format="json"
        )
        assert r.status_code == 400 and "identifiers" in r.json()["error"]["fields"]

    def test_findings_field_names_are_not_asset_fields(self, w, admin_client):
        job = upload(admin_client, w.org_a, [["a", "Host", "", "", "10.1.0.5", "", "", ""]]).json()
        r = admin_client.post(
            f"{API}/imports/{job['id']}/mapping",
            {"column_map": {"title": "Name", "ip": "IP"}, "value_map": {}},
            format="json",
        )
        assert r.status_code == 400 and "title" in r.json()["error"]["fields"]

    def test_organisation_outside_scope_is_refused(self, w):
        assert upload(signed_in(w.p1), w.org_b, [["a", "", "", "", "10.1.0.6", "", "", ""]]).status_code in (400, 403)

    def test_template_download(self, w, admin_client):
        r = admin_client.get(f"{API}/imports/asset-template.csv")
        text = b"".join(r.streaming_content).decode()
        assert r.status_code == 200
        assert text.splitlines()[0].strip() == "Name,Asset type,Environment,Criticality,Identifiers,Tags"
        assert len(text.splitlines()) == 4

    def test_template_imports_as_downloaded(self, w, admin_client):
        import csv
        import io

        text = b"".join(admin_client.get(f"{API}/imports/asset-template.csv").streaming_content).decode()
        rows = list(csv.reader(io.StringIO(text)))
        job = upload(admin_client, w.org_a, rows[1:], header=rows[0]).json()
        mapping = job["suggested_mapping"]
        assert set(mapping) == {"name", "type", "environment", "criticality", "identifiers", "tags"}
        r = admin_client.post(f"{API}/imports/{job['id']}/mapping", {"column_map": mapping, "value_map": {}}, format="json")
        assert r.status_code == 202, r.content
        job = admin_client.get(f"{API}/imports/{job['id']}").json()
        assert commit(admin_client, job).status_code in (200, 202)
        names = set(Asset.objects.filter(organisation=w.org_a).values_list("name", flat=True))
        assert {"Acme shop", "Web 01", "Acme API"} <= names


@pytest.mark.django_db
class TestCheck:
    def test_new_known_merge_conflict_and_in_file_rows(self, w, admin, admin_client):
        web = org_services.create_asset(
            None, admin, w.org_a, {"name": "Web", "type": "host", "identifiers": [{"value": "10.2.0.1"}]}
        )
        db = org_services.create_asset(
            None, admin, w.org_a, {"name": "Db", "type": "host", "identifiers": [{"value": "10.2.0.2"}]}
        )
        job = prepared(
            admin_client,
            w.org_a,
            [
                ["Brand new", "", "", "", "10.2.0.9", "new.acme.test", "", ""],  # 2: create
                ["Web again", "", "", "", "10.2.0.1", "", "", ""],  # 3: known, nothing new
                ["Web more", "", "", "", "10.2.0.1", "web.acme.test", "", ""],  # 4: adds a hostname
                ["Bridge", "", "", "", "10.2.0.1", "x", "", "https://db.acme.test"],  # 5: ok? 10.2.0.1 only
                ["Both", "", "", "", "10.2.0.1; 10.2.0.2", "", "", ""],  # 6: conflict Web vs Db
                ["Same as 2", "", "", "", "", "NEW.acme.test.", "", ""],  # 7: known in file
                ["Folds into 2", "", "", "", "10.2.0.9", "", "https://new.acme.test/", ""],  # 8: adds a URL to row 2
                ["Bad ip", "", "", "", "10.2.0.300", "", "", ""],  # 9: invalid
                ["No id", "", "", "", "", "", "", ""],  # 10: invalid
            ],
        )
        assert job["status"] == "previewed", job
        rows = by_line(admin_client, job)
        actions = {n: (r["status"], (r["asset"] or {}).get("action")) for n, r in rows.items()}
        assert actions[2] == ("valid", "create")
        assert actions[3] == ("duplicate", "known")
        assert actions[4] == ("valid", "merge") and rows[4]["asset"]["asset"]["name"] == "Web"
        assert rows[6]["status"] == "invalid" and rows[6]["errors"][0]["code"] == "identifier_conflict"
        assert "Db" in rows[6]["errors"][0]["message"] and "Web" in rows[6]["errors"][0]["message"]
        assert actions[7] == ("duplicate", "known_in_file") and rows[7]["duplicate_of"] == {"line": 2}
        assert actions[8] == ("valid", "merge_in_file")
        assert rows[9]["status"] == "invalid" and rows[10]["status"] == "invalid"
        c = job["counts"]
        assert c["total"] == 9 and c["to_create"] >= 1 and c["invalid"] == 3
        assert web.identifiers.count() == 1  # nothing changes before the commit
        assert db.identifiers.count() == 1

    def test_name_falls_back_to_first_identifier_and_type_is_guessed(self, w, admin_client):
        job = prepared(admin_client, w.org_a, [["", "", "", "", "", "", "https://app.acme.test", ""]])
        row = row_list(admin_client, job)[0]
        assert row["title"] == "https://app.acme.test" and row["asset"]["type"] == "web_app"

    def test_bad_values_are_row_errors_not_crashes(self, w, admin_client):
        job = prepared(
            admin_client,
            w.org_a,
            [
                ["a", "Spaceship", "", "", "10.2.1.1", "", "", ""],
                ["b", "Host", "moon", "", "10.2.1.2", "", "", ""],
                ["c", "Host", "", "9", "10.2.1.3", "", "", ""],
                ["d", "Host", "", "", "10.2.1.4", "", "", ";".join(f"t{i}" for i in range(30))],
                ["e", "Host", "", "", "", "", "https://u:p@a.test", ""],
            ],
        )
        got = by_line(admin_client, job)
        assert [got[n]["errors"][0]["field"] for n in range(2, 7)] == [
            "type",
            "environment",
            "criticality",
            "tags",
            "url",
        ]
        assert job["counts"]["invalid"] == 5

    def test_archived_asset_match_is_an_error(self, w, admin, admin_client):
        org_services.set_asset_archived(None, admin, w.asset_a, True)
        job = prepared(admin_client, w.org_a, [["Shop", "", "", "", "", "", "https://shop.acme.test", ""]])
        row = row_list(admin_client, job)[0]
        assert row["status"] == "invalid" and row["errors"][0]["code"] == "archived_asset"

    def test_same_identifier_in_another_organisation_is_independent(self, w, admin_client):
        job = prepared(admin_client, w.org_b, [["Shop clone", "", "", "", "", "", "https://shop.acme.test", ""]])
        assert row_list(admin_client, job)[0]["asset"]["action"] == "create"

    def test_one_row_can_hold_many_identifiers_in_one_cell(self, w, admin_client):
        job = prepared(admin_client, w.org_a, [["Multi", "", "", "", "10.2.2.1; 10.2.2.2 | 10.2.2.3", "", "", ""]])
        assert len(row_list(admin_client, job)[0]["asset"]["identifiers"]) == 3


@pytest.mark.django_db
class TestCommit:
    ROWS = [
        ["Web", "Host", "staging", "high", "10.3.0.1", "web.acme.test", "", "pci; public"],
        ["Shop", "", "", "", "", "", "https://SHOP.acme.test/", ""],  # matches the existing Acme shop by URL
        ["Shop alias", "", "", "", "", "shop-alias.acme.test", "https://shop.acme.test", ""],  # same asset, new alias
        ["Wifi", "Wireless network", "", "2", "", "", "", ""],  # no identifier: invalid
    ]

    def test_creates_not_onboarded_assets_and_enriches_matches(self, w, admin_client):
        before = Asset.objects.filter(organisation=w.org_a).count()
        job = prepared(admin_client, w.org_a, self.ROWS)
        assert job["counts"]["invalid"] == 1
        assert commit(admin_client, job, "all_or_nothing").status_code == 409  # one row has an error
        r = commit(admin_client, job)
        assert r.status_code == 202
        done = admin_client.get(f"{API}/imports/{job['id']}").json()
        assert done["status"] == "completed", done
        assert done["counts"]["created"] == 1 and done["counts"]["merged"] == 1 and done["counts"]["skipped"] == 1
        assert Asset.objects.filter(organisation=w.org_a).count() == before + 1
        web = Asset.objects.get(name="Web")
        assert web.onboarding_status == "pending" and web.origin == "import" and web.onboarded_at is None
        assert (web.type, web.environment, web.criticality, web.tags) == ("host", "staging", 4, ["pci", "public"])
        assert {i.normalized for i in web.identifiers.all()} == {"10.3.0.1", "web.acme.test"}
        assert web.identifiers.filter(is_primary=True).count() == 1 and web.identifier == "10.3.0.1"
        w.asset_a.refresh_from_db()
        assert w.asset_a.onboarding_status == "onboarded"  # an existing asset stays as it was
        assert w.asset_a.name == "Acme shop"
        assert {i.normalized for i in w.asset_a.identifiers.all()} == {"https://shop.acme.test", "shop-alias.acme.test"}
        ev = AuditEvent.objects.filter(action="import.committed", entity_id=job["id"]).get()
        assert ev.metadata["created_not_onboarded"] == 1 and ev.metadata["merged_into_existing"] == 1
        rows = by_line(admin_client, job)
        assert rows[2]["status"] == "imported" and rows[2]["asset"]["asset"]["id"] == str(web.pk)
        assert rows[3]["status"] == "skipped"
        assert rows[4]["status"] == "imported" and rows[5]["status"] == "invalid"

    def test_running_the_same_file_again_creates_nothing(self, w, admin_client):
        rows = [["Web", "Host", "", "", "10.3.1.1", "web31.acme.test", "", ""]]
        first = prepared(admin_client, w.org_a, rows)
        assert commit(admin_client, first).status_code == 202
        count = Asset.objects.count()
        identifiers = AssetIdentifier.objects.count()
        second = prepared(admin_client, w.org_a, rows, name="again.csv")
        assert second["counts"]["duplicate"] == 1 and second["counts"]["valid"] == 0
        assert commit(admin_client, second).status_code == 409  # nothing new
        assert Asset.objects.count() == count and AssetIdentifier.objects.count() == identifiers

    def test_one_asset_under_different_identifiers_in_two_files_is_still_one_asset(self, w, admin_client):
        a = prepared(admin_client, w.org_a, [["Web", "Host", "", "", "10.3.2.1", "", "", ""]])
        commit(admin_client, a)
        b = prepared(
            admin_client,
            w.org_a,
            [["Web", "Host", "", "", "10.3.2.1", "web32.acme.test", "", ""]],
        )
        assert commit(admin_client, b).status_code == 202
        assets = Asset.objects.filter(identifiers__normalized__in=["10.3.2.1", "web32.acme.test"]).distinct()
        assert assets.count() == 1 and assets.get().identifiers.count() == 2

    def test_rows_of_one_file_fold_into_one_asset(self, w, admin_client):
        job = prepared(
            admin_client,
            w.org_a,
            [
                ["Srv", "Host", "", "", "10.3.3.1", "", "", ""],
                ["Srv", "Host", "", "", "10.3.3.1", "srv33.acme.test", "", ""],
                ["Srv", "Host", "", "", "", "SRV33.acme.test", "https://srv33.acme.test", ""],
            ],
        )
        assert commit(admin_client, job).status_code == 202
        a = Asset.objects.get(identifiers__normalized="10.3.3.1")
        assert {i.normalized for i in a.identifiers.all()} == {"10.3.3.1", "srv33.acme.test", "https://srv33.acme.test"}
        assert Asset.objects.filter(name="Srv").count() == 1

    def test_conflict_rows_are_left_out_and_nothing_is_guessed(self, w, admin, admin_client):
        org_services.create_asset(
            None, admin, w.org_a, {"name": "A", "type": "host", "identifiers": [{"value": "10.3.4.1"}]}
        )
        org_services.create_asset(
            None, admin, w.org_a, {"name": "B", "type": "host", "identifiers": [{"value": "10.3.4.2"}]}
        )
        job = prepared(
            admin_client,
            w.org_a,
            [["x", "", "", "", "10.3.4.1; 10.3.4.2", "", "", ""], ["ok", "", "", "", "10.3.4.3", "", "", ""]],
        )
        assert commit(admin_client, job).status_code == 202
        assert Asset.objects.filter(identifiers__normalized="10.3.4.1").count() == 1
        assert not AssetIdentifier.objects.filter(normalized="10.3.4.3", asset__name="A").exists()
        assert Asset.objects.get(name="ok").onboarding_status == "pending"

    def test_identifier_taken_between_check_and_commit(self, w, admin, admin_client):
        job = prepared(
            admin_client,
            w.org_a,
            [["Late", "", "", "", "10.3.5.1", "", "", ""], ["Fine", "", "", "", "10.3.5.2", "", "", ""]],
        )
        org_services.create_asset(
            None, admin, w.org_a, {"name": "Sniped", "type": "host", "identifiers": [{"value": "10.3.5.1"}]}
        )
        # the stale check said "create"; the commit matches again and joins the asset that now owns it
        assert commit(admin_client, job).status_code == 202
        assert Asset.objects.filter(identifiers__normalized="10.3.5.1").count() == 1
        assert Asset.objects.filter(name="Late").count() == 0 and Asset.objects.filter(name="Fine").exists()

    def test_conflict_arising_before_commit_aborts_all_or_nothing(self, w, admin, admin_client):
        job = prepared(
            admin_client,
            w.org_a,
            [["One", "", "", "", "10.3.6.1", "", "", ""], ["Two", "", "", "", "10.3.6.1; 10.3.6.2", "", "", ""]],
        )
        assert job["counts"]["invalid"] == 0
        org_services.create_asset(
            None, admin, w.org_a, {"name": "X", "type": "host", "identifiers": [{"value": "10.3.6.2"}]}
        )
        assert commit(admin_client, job, "all_or_nothing").status_code == 202
        done = admin_client.get(f"{API}/imports/{job['id']}").json()
        assert done["status"] == "failed" and "Nothing was imported" in done["error"]
        assert not Asset.objects.filter(name="One").exists()  # rolled back with the failing row

    def test_archived_organisation_refuses_import(self, w, admin, admin_client):
        from apps.engagements import services as eng_services

        job = prepared(admin_client, w.org_a, [["a", "", "", "", "10.3.7.1", "", "", ""]])
        eng_services.change_status(None, admin, w.eng_a, "cancelled", w.eng_a.version)
        org_services.archive_organisation(None, admin, w.org_a)
        assert commit(admin_client, job).status_code == 409
        assert upload(admin_client, w.org_a, [["a", "", "", "", "10.3.7.2", "", "", ""]]).status_code == 409

    def test_imported_asset_can_be_onboarded_later_and_then_joins_an_engagement(self, w, admin_client):
        job = prepared(admin_client, w.org_a, [["Later", "Host", "", "", "10.3.8.1", "", "", ""]])
        commit(admin_client, job)
        a = Asset.objects.get(name="Later")
        link = f"{API}/engagements/{w.eng_a.pk}/assets"
        assert admin_client.post(link, {"asset": str(a.pk)}, format="json").status_code == 400
        listing = admin_client.get(f"{API}/assets", {"onboarding_status": "pending"}).json()
        assert [x["name"] for x in listing["results"]] == ["Later"]
        assert admin_client.post(f"{API}/assets/{a.pk}/onboard", {"criticality": 5}, format="json").status_code == 200
        assert admin_client.post(link, {"asset": str(a.pk)}, format="json").status_code == 201

    def test_problem_report_lists_rows_left_out(self, w, admin_client):
        job = prepared(admin_client, w.org_a, self.ROWS)
        r = admin_client.get(f"{API}/imports/{job['id']}/errors.csv")
        text = b"".join(r.streaming_content).decode()
        assert "no identifier" in text.lower() and "Wifi" in text

    def test_commit_with_only_known_rows_is_refused(self, w, admin_client):
        job = prepared(admin_client, w.org_a, [["Shop", "", "", "", "", "", "https://shop.acme.test", ""]])
        assert job["counts"]["valid"] == 0 and commit(admin_client, job).status_code == 409

    def test_only_one_import_per_organisation_at_a_time(self, w, admin, admin_client):
        ImportJob.objects.create(
            kind="assets", organisation=w.org_a, uploaded_by=admin, original_name="x.csv", file_sha256="0" * 64,
            file_size=1, status="importing",
        )  # fmt: skip
        assert upload(admin_client, w.org_a, [["a", "", "", "", "10.3.9.1", "", "", ""]]).status_code == 409
        assert upload(admin_client, w.org_b, [["a", "", "", "", "10.3.9.1", "", "", ""]]).status_code == 201
