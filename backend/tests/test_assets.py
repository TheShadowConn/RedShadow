"""Assets: listing, search and filters, identifiers, conflicts, onboarding, delete, merge and permissions."""

import pytest

from apps.audit.models import AuditEvent
from apps.engagements import services as eng_services
from apps.findings.models import Finding
from apps.organisations import services as org_services
from apps.organisations.models import Asset, AssetIdentifier
from tests.conftest import make_role, make_user, signed_in
from tests.test_findings import API
from tests.world import build_world


@pytest.fixture
def w(admin):
    return build_world(admin)


def mk(client, org, name="Web 01", identifiers=None, **extra):
    body = {"organisation": str(org.pk), "name": name, "type": "host", "identifiers": identifiers or [], **extra}
    return client.post(f"{API}/assets", body, format="json")


def ids(asset_json):
    return {i["normalized"] for i in asset_json["identifiers"]}


@pytest.mark.django_db
class TestCreate:
    def test_asset_with_several_identifiers(self, w, admin_client):
        r = mk(
            admin_client,
            w.org_a,
            identifiers=[
                {"kind": "ip", "value": "10.1.1.1"},
                {"kind": "hostname", "value": "WEB01.Acme.test", "is_primary": True},
                {"value": "https://web01.acme.test/"},
            ],
        )
        assert r.status_code == 201, r.content
        a = r.json()
        assert ids(a) == {"10.1.1.1", "web01.acme.test", "https://web01.acme.test"}
        primary = [i for i in a["identifiers"] if i["is_primary"]]
        assert len(primary) == 1 and primary[0]["normalized"] == "web01.acme.test"
        assert a["identifier"] == "WEB01.Acme.test"  # display copy of the primary
        assert a["onboarding_status"] == "onboarded" and a["origin"] == "manual"
        assert AuditEvent.objects.filter(action="asset.created", entity_id=a["id"]).exists()

    def test_first_identifier_is_primary_when_none_is_flagged(self, w, admin_client):
        a = mk(admin_client, w.org_a, identifiers=[{"value": "10.1.1.2"}, {"value": "10.1.1.3"}]).json()
        assert [i["normalized"] for i in a["identifiers"] if i["is_primary"]] == ["10.1.1.2"]

    def test_legacy_single_identifier_text_still_works(self, w, admin_client):
        r = admin_client.post(
            f"{API}/assets",
            {"organisation": str(w.org_a.pk), "name": "Old style", "type": "host", "identifier": "10.9.9.9"},
            format="json",
        )
        assert r.status_code == 201
        assert ids(r.json()) == {"10.9.9.9"} and r.json()["identifier"] == "10.9.9.9"

    def test_same_identifier_in_two_spellings_is_kept_once(self, w, admin_client):
        r = mk(admin_client, w.org_a, identifiers=[{"value": "https://A.test/"}, {"value": "https://a.test"}])
        assert r.status_code == 201 and len(r.json()["identifiers"]) == 1

    def test_invalid_identifier_is_400_and_creates_nothing(self, w, admin_client):
        before = Asset.objects.count()
        r = mk(
            admin_client, w.org_a, identifiers=[{"kind": "ip", "value": "10.0.0.999"}, {"kind": "mac", "value": "xx"}]
        )
        assert r.status_code == 400
        assert len(r.json()["error"]["fields"]["identifiers"]) == 2
        assert Asset.objects.count() == before

    def test_identifier_owned_by_another_asset_is_refused_with_its_name(self, w, admin_client):
        r = mk(admin_client, w.org_a, name="Clone", identifiers=[{"value": "https://SHOP.acme.test"}])
        assert r.status_code == 400
        assert "Acme shop" in r.json()["error"]["fields"]["identifiers"][0]
        assert not Asset.objects.filter(name="Clone").exists()

    def test_other_organisation_may_use_the_same_identifier(self, w, admin_client):
        assert mk(admin_client, w.org_b, identifiers=[{"value": "https://shop.acme.test"}]).status_code == 201

    def test_unknown_and_readonly_fields_rejected(self, w, admin_client):
        r = admin_client.post(
            f"{API}/assets",
            {"organisation": str(w.org_a.pk), "name": "x", "type": "host", "onboarding_status": "pending"},
            format="json",
        )
        assert r.status_code == 400
        r = mk(admin_client, w.org_a, identifiers=[{"value": "10.0.0.1", "asset": "x"}])
        assert r.status_code == 400

    def test_blank_name_rejected(self, w, admin_client):
        assert mk(admin_client, w.org_a, name="   ").status_code == 400

    def test_archived_organisation_is_read_only(self, w, admin, admin_client):
        eng_services.change_status(None, admin, w.eng_a, "cancelled", w.eng_a.version)
        org_services.archive_organisation(None, admin, w.org_a)
        assert mk(admin_client, w.org_a, identifiers=[{"value": "10.4.4.4"}]).status_code == 409


@pytest.mark.django_db
class TestCheck:
    def test_reports_free_owned_and_invalid(self, w, admin_client):
        r = admin_client.post(
            f"{API}/assets/identifiers/check",
            {
                "organisation": str(w.org_a.pk),
                "identifiers": [
                    {"value": "https://shop.acme.test"},
                    {"value": "10.5.5.5"},
                    {"kind": "ip", "value": "no"},
                ],
            },
            format="json",
        )
        assert r.status_code == 200
        got = r.json()
        assert [g["status"] for g in got] == ["owned", "free", "invalid"]
        assert got[0]["asset"]["name"] == "Acme shop"

    def test_asset_may_keep_its_own_identifiers(self, w, admin_client):
        r = admin_client.post(
            f"{API}/assets/identifiers/check",
            {
                "organisation": str(w.org_a.pk),
                "asset": str(w.asset_a.pk),
                "identifiers": [{"value": "https://shop.acme.test"}],
            },
            format="json",
        )
        assert r.json()[0]["status"] == "free"


@pytest.mark.django_db
class TestIdentifierEndpoints:
    def make(self, w, admin_client):
        return mk(admin_client, w.org_a, identifiers=[{"value": "10.2.0.1"}]).json()

    def test_add_primary_promote_and_remove(self, w, admin_client):
        a = self.make(w, admin_client)
        url = f"{API}/assets/{a['id']}/identifiers"
        r = admin_client.post(url, {"value": "web02.acme.test", "is_primary": True}, format="json")
        assert r.status_code == 201 and r.json()["is_primary"] and r.json()["kind"] == "hostname"
        got = admin_client.get(f"{API}/assets/{a['id']}").json()
        assert got["identifier"] == "web02.acme.test" and sum(i["is_primary"] for i in got["identifiers"]) == 1
        old = next(i for i in got["identifiers"] if i["normalized"] == "10.2.0.1")
        r = admin_client.patch(f"{url}/{old['id']}", {"is_primary": True}, format="json")
        assert r.status_code == 200
        assert admin_client.get(f"{API}/assets/{a['id']}").json()["identifier"] == "10.2.0.1"

    def test_removing_the_primary_promotes_another(self, w, admin_client):
        a = self.make(w, admin_client)
        url = f"{API}/assets/{a['id']}/identifiers"
        admin_client.post(url, {"value": "10.2.0.2"}, format="json")
        assert admin_client.delete(f"{url}/{a['identifiers'][0]['id']}").status_code == 204
        got = admin_client.get(f"{API}/assets/{a['id']}").json()
        assert [i["normalized"] for i in got["identifiers"] if i["is_primary"]] == ["10.2.0.2"]
        assert got["identifier"] == "10.2.0.2"

    def test_last_identifier_of_an_onboarded_asset_cannot_be_removed(self, w, admin_client):
        a = self.make(w, admin_client)
        r = admin_client.delete(f"{API}/assets/{a['id']}/identifiers/{a['identifiers'][0]['id']}")
        assert r.status_code == 409

    def test_cannot_add_an_identifier_owned_elsewhere_or_twice(self, w, admin_client):
        a = self.make(w, admin_client)
        url = f"{API}/assets/{a['id']}/identifiers"
        assert admin_client.post(url, {"value": "https://shop.acme.test"}, format="json").status_code == 400
        assert admin_client.post(url, {"value": "10.2.0.1"}, format="json").status_code == 409

    def test_edit_value_renormalises_and_checks_conflicts(self, w, admin_client):
        a = self.make(w, admin_client)
        url = f"{API}/assets/{a['id']}/identifiers/{a['identifiers'][0]['id']}"
        r = admin_client.patch(url, {"value": "10.2.0.77"}, format="json")
        assert r.status_code == 200 and r.json()["normalized"] == "10.2.0.77"
        assert (
            admin_client.patch(url, {"kind": "url", "value": "https://shop.acme.test"}, format="json").status_code
            == 400
        )
        assert admin_client.patch(url, {"value": "nope", "kind": "ip"}, format="json").status_code == 400

    def test_identifier_of_another_asset_is_not_reachable_through_this_one(self, w, admin_client):
        a = self.make(w, admin_client)
        other = w.asset_a.identifiers.first()
        r = admin_client.delete(f"{API}/assets/{a['id']}/identifiers/{other.pk}")
        assert r.status_code == 404
        assert AssetIdentifier.objects.filter(pk=other.pk).exists()

    def test_legacy_identifier_patch_adds_a_primary_and_keeps_the_old_one(self, w, admin_client):
        r = admin_client.patch(f"{API}/assets/{w.asset_a.pk}", {"identifier": "https://shop2.acme.test"}, format="json")
        assert r.status_code == 200
        assert r.json()["identifier"] == "https://shop2.acme.test"
        assert {"https://shop.acme.test", "https://shop2.acme.test"} <= ids(r.json())
        r = admin_client.patch(f"{API}/assets/{w.asset_a.pk}", {"identifier": "10.0.0.5"}, format="json")
        assert r.status_code == 200  # free in Acme: only Borealis owns it
        assert (
            admin_client.patch(
                f"{API}/assets/{w.asset_b.pk}", {"identifier": "https://shop.acme.test"}, format="json"
            ).status_code
            == 200
        )


@pytest.mark.django_db
class TestList:
    def seed(self, w, admin_client):
        mk(
            admin_client,
            w.org_a,
            "Db 01",
            [{"value": "10.3.0.1"}, {"value": "db01.acme.test"}],
            criticality=5,
            environment="staging",
            tags=["pci"],
        )
        mk(admin_client, w.org_a, "Wifi", [{"value": "guest-wifi"}], type="wireless")

    def test_search_covers_name_every_identifier_and_tags(self, w, admin_client):
        self.seed(w, admin_client)
        for term in ("db 01", "10.3.0.1", "DB01.ACME", "pci"):
            r = admin_client.get(f"{API}/assets", {"search": term})
            assert [a["name"] for a in r.json()["results"]] == ["Db 01"], term

    def test_filters(self, w, admin_client):
        self.seed(w, admin_client)

        def names(**q):
            return sorted(a["name"] for a in admin_client.get(f"{API}/assets", q).json()["results"])

        assert names(type="wireless") == ["Wifi"]
        assert names(environment="staging") == ["Db 01"]
        assert names(criticality="5") == ["Db 01"]
        assert names(organisation=str(w.org_b.pk)) == ["Borealis core"]
        assert names(onboarding_status="pending") == []
        assert "Acme shop" in names(organisation=str(w.org_a.pk))

    def test_identifiers_and_engagement_count_in_the_list(self, w, admin_client):
        row = next(a for a in admin_client.get(f"{API}/assets").json()["results"] if a["name"] == "Acme shop")
        assert row["engagement_count"] == 1 and row["identifiers"][0]["normalized"] == "https://shop.acme.test"

    def test_search_does_not_duplicate_rows(self, w, admin_client):
        self.seed(w, admin_client)
        assert admin_client.get(f"{API}/assets", {"search": "db"}).json()["count"] == 1

    def test_archived_hidden_unless_asked(self, w, admin_client):
        admin_client.post(f"{API}/assets/{w.asset_a.pk}/archive")
        assert "Acme shop" not in [a["name"] for a in admin_client.get(f"{API}/assets").json()["results"]]
        assert "Acme shop" in [
            a["name"] for a in admin_client.get(f"{API}/assets", {"archived": "true"}).json()["results"]
        ]

    def test_summary(self, w, admin_client, admin):
        org_services.create_asset(None, admin, w.org_a, {"name": "x", "type": "host", "identifier": "10.8.8.8"})
        Asset.objects.filter(name="x").update(onboarding_status="pending")
        s = admin_client.get(f"{API}/assets/summary").json()
        assert s["pending"] == 1 and s["onboarded"] == 2 and s["total"] == 3

    def test_ordering(self, w, admin_client):
        self.seed(w, admin_client)
        got = [a["name"] for a in admin_client.get(f"{API}/assets", {"ordering": "criticality"}).json()["results"]]
        assert got[0] == "Db 01"


@pytest.mark.django_db
class TestPermissions:
    def test_pentester_sees_only_assets_of_their_engagements_and_cannot_write(self, w):
        c = signed_in(w.p1)
        assert [a["name"] for a in c.get(f"{API}/assets").json()["results"]] == ["Acme shop"]
        assert c.get(f"{API}/assets/{w.asset_b.pk}").status_code == 404
        for method, path, body in [
            ("post", "/assets", {"organisation": str(w.org_a.pk), "name": "x", "type": "host"}),
            ("patch", f"/assets/{w.asset_a.pk}", {"name": "y"}),
            ("delete", f"/assets/{w.asset_a.pk}", None),
            ("post", f"/assets/{w.asset_a.pk}/identifiers", {"value": "10.0.0.1"}),
            ("post", f"/assets/{w.asset_a.pk}/onboard", {}),
            ("post", f"/assets/{w.asset_a.pk}/merge", {"source": str(w.asset_b.pk)}),
            ("post", "/assets/identifiers/check", {"organisation": str(w.org_a.pk), "identifiers": []}),
            ("post", "/assets/onboard", {"ids": [str(w.asset_a.pk)]}),
        ]:
            r = getattr(c, method)(f"{API}{path}", body, format="json")
            assert r.status_code in (403, 404), (path, r.status_code)

    def test_custom_role_with_create_but_not_delete(self, w):
        role = make_role(
            "Asset editor",
            ["assets.view", "assets.create", "assets.update", "organisations.view"],
            all_engagements=True,
        )
        c = signed_in(make_user("ae@example.com", role))
        assert mk(c, w.org_a, identifiers=[{"value": "10.6.0.1"}]).status_code == 201
        assert c.delete(f"{API}/assets/{w.asset_a.pk}").status_code == 403

    def test_anonymous_is_refused(self, w, api):
        assert api.get(f"{API}/assets").status_code in (401, 403)

    def test_cannot_use_an_organisation_outside_scope_for_a_check(self, w):
        role = make_role(
            "Asset editor 2", ["assets.view", "assets.create", "organisations.view"], all_engagements=False
        )
        c = signed_in(make_user("ae2@example.com", role))
        r = c.post(
            f"{API}/assets/identifiers/check", {"organisation": str(w.org_a.pk), "identifiers": []}, format="json"
        )
        assert r.status_code == 400


@pytest.mark.django_db
class TestOnboarding:
    def pending(self, admin, org, name="Imported", ident="10.7.0.1"):
        a = org_services.create_asset(None, admin, org, {"name": name, "type": "host", "identifier": ident})
        Asset.objects.filter(pk=a.pk).update(onboarding_status="pending", origin="import", onboarded_at=None)
        return a

    def test_onboard_completes_details(self, w, admin, admin_client):
        a = self.pending(admin, w.org_a)
        r = admin_client.post(f"{API}/assets/{a.pk}/onboard", {"criticality": 5, "name": "Core DB"}, format="json")
        assert r.status_code == 200, r.content
        j = r.json()
        assert j["onboarding_status"] == "onboarded" and j["criticality"] == 5 and j["name"] == "Core DB"
        assert j["onboarded_at"]
        assert AuditEvent.objects.filter(action="asset.onboarded", entity_id=str(a.pk)).exists()

    def test_onboard_is_idempotent(self, w, admin_client):
        r = admin_client.post(f"{API}/assets/{w.asset_a.pk}/onboard", {}, format="json")
        assert r.status_code == 200 and r.json()["onboarding_status"] == "onboarded"

    def test_asset_without_identifier_cannot_be_onboarded(self, w, admin, admin_client):
        a = org_services.create_asset(None, admin, w.org_a, {"name": "Bare", "type": "other"})
        Asset.objects.filter(pk=a.pk).update(onboarding_status="pending")
        assert admin_client.post(f"{API}/assets/{a.pk}/onboard", {}, format="json").status_code == 409

    def test_bulk_onboard_reports_skips(self, w, admin, admin_client):
        a = self.pending(admin, w.org_a, "A1", "10.7.0.2")
        b = org_services.create_asset(None, admin, w.org_a, {"name": "Bare", "type": "other"})
        Asset.objects.filter(pk=b.pk).update(onboarding_status="pending")
        r = admin_client.post(f"{API}/assets/onboard", {"ids": [str(a.pk), str(b.pk)]}, format="json")
        assert r.status_code == 200
        assert r.json()["onboarded"] == 1 and r.json()["skipped"][0]["name"] == "Bare"

    def test_not_onboarded_asset_cannot_join_an_engagement(self, w, admin, admin_client):
        a = self.pending(admin, w.org_a)
        r = admin_client.post(f"{API}/engagements/{w.eng_a.pk}/assets", {"asset": str(a.pk)}, format="json")
        assert r.status_code == 400
        admin_client.post(f"{API}/assets/{a.pk}/onboard", {}, format="json")
        r = admin_client.post(f"{API}/engagements/{w.eng_a.pk}/assets", {"asset": str(a.pk)}, format="json")
        assert r.status_code == 201, r.content

    def test_pentester_never_sees_not_onboarded_assets(self, w, admin):
        a = self.pending(admin, w.org_a)
        assert signed_in(w.p1).get(f"{API}/assets/{a.pk}").status_code == 404


@pytest.mark.django_db
class TestDeleteAndMerge:
    def test_unused_asset_is_deleted_with_identifiers_and_audited(self, w, admin_client):
        a = mk(admin_client, w.org_a, identifiers=[{"value": "10.9.1.1"}, {"value": "x.acme.test"}]).json()
        assert admin_client.get(f"{API}/assets/{a['id']}/usage").json() == {
            "engagements": 0,
            "findings": 0,
            "identifiers": 2,
        }
        assert admin_client.delete(f"{API}/assets/{a['id']}").status_code == 204
        assert not Asset.objects.filter(pk=a["id"]).exists()
        assert not AssetIdentifier.objects.filter(asset_id=a["id"]).exists()
        ev = AuditEvent.objects.filter(action="asset.deleted").latest("id")
        assert "10.9.1.1" in ev.metadata["identifiers"]
        # the identifiers are free again
        assert mk(admin_client, w.org_a, "Again", [{"value": "10.9.1.1"}]).status_code == 201

    def test_asset_in_an_engagement_cannot_be_deleted(self, w, admin_client):
        r = admin_client.delete(f"{API}/assets/{w.asset_a.pk}")
        assert r.status_code == 409 and "Archive" in r.json()["error"]["message"]
        assert Asset.objects.filter(pk=w.asset_a.pk).exists()

    def test_asset_with_findings_cannot_be_deleted(self, w, admin, admin_client):
        a = mk(admin_client, w.org_a, "Used", [{"value": "10.9.2.2"}]).json()
        Finding.objects.filter(pk__isnull=False).count()
        from apps.findings.services import reserve_refs

        Finding.objects.create(
            ref=reserve_refs(1)[0], engagement=w.eng_a, asset_id=a["id"], title="t", severity="low", status="draft",
            reported_by=admin, discovered_at=w.today, dedupe_hash="x" * 64,
        )  # fmt: skip
        assert admin_client.delete(f"{API}/assets/{a['id']}").status_code == 409

    def test_merge_moves_identifiers_links_and_findings(self, w, admin, admin_client):
        keep = mk(admin_client, w.org_a, "Keep", [{"value": "10.9.3.1"}], tags=["a"]).json()
        dupe = mk(
            admin_client, w.org_a, "Dupe", [{"value": "dupe.acme.test"}, {"value": "10.9.3.2"}], tags=["b"]
        ).json()
        eng_services.link_asset(None, admin, w.eng_a, Asset.objects.get(pk=dupe["id"]), True, "")
        from apps.findings.services import reserve_refs

        f = Finding.objects.create(
            ref=reserve_refs(1)[0], engagement=w.eng_a, asset_id=dupe["id"], title="t", severity="low", status="draft",
            reported_by=admin, discovered_at=w.today, dedupe_hash="y" * 64,
        )  # fmt: skip
        r = admin_client.post(f"{API}/assets/{keep['id']}/merge", {"source": dupe["id"]}, format="json")
        assert r.status_code == 200, r.content
        j = r.json()
        assert ids(j) == {"10.9.3.1", "dupe.acme.test", "10.9.3.2"}
        assert sum(i["is_primary"] for i in j["identifiers"]) == 1 and j["identifiers"][0]["normalized"] == "10.9.3.1"
        assert set(j["tags"]) == {"a", "b"} and j["engagement_count"] == 1
        assert not Asset.objects.filter(pk=dupe["id"]).exists()
        f.refresh_from_db()
        assert str(f.asset_id) == keep["id"]
        assert AuditEvent.objects.filter(action="asset.merged").exists()

    def test_merge_rules(self, w, admin_client):
        a = mk(admin_client, w.org_a, "A", [{"value": "10.9.4.1"}]).json()
        b = mk(admin_client, w.org_b, "B", [{"value": "10.9.4.2"}]).json()
        assert admin_client.post(f"{API}/assets/{a['id']}/merge", {"source": a["id"]}, format="json").status_code == 400
        assert admin_client.post(f"{API}/assets/{a['id']}/merge", {"source": b["id"]}, format="json").status_code == 400
        assert admin_client.post(f"{API}/assets/{a['id']}/merge", {"source": "nope"}, format="json").status_code == 400


@pytest.mark.django_db
class TestIdentifierRows:
    def test_every_existing_asset_got_its_identifier_row(self, w):
        assert w.asset_a.identifiers.get().normalized == "https://shop.acme.test"
        assert w.asset_b.identifiers.get().kind == "ip"


@pytest.mark.django_db
class TestBulkArchiveAndScope:
    def test_bulk_archive_and_unarchive(self, w, admin_client):
        a = mk(admin_client, w.org_a, "B1", [{"value": "10.11.0.1"}]).json()
        b = mk(admin_client, w.org_a, "B2", [{"value": "10.11.0.2"}]).json()
        r = admin_client.post(f"{API}/assets/archive", {"ids": [a["id"], b["id"]], "archived": True}, format="json")
        assert r.status_code == 200 and r.json()["changed"] == 2 and r.json()["skipped"] == []
        assert Asset.objects.filter(pk__in=[a["id"], b["id"]], archived_at__isnull=False).count() == 2
        again = admin_client.post(f"{API}/assets/archive", {"ids": [a["id"]], "archived": True}, format="json")
        assert again.json()["changed"] == 0
        r = admin_client.post(f"{API}/assets/archive", {"ids": [a["id"]], "archived": False}, format="json")
        assert r.json()["changed"] == 1
        assert AuditEvent.objects.filter(action="asset.archived").count() == 2

    def test_bulk_archive_permissions_and_input(self, w, admin_client):
        c = signed_in(w.p1)
        body = {"ids": [str(w.asset_a.pk)], "archived": True}
        assert c.post(f"{API}/assets/archive", body, format="json").status_code == 403
        assert (
            admin_client.post(f"{API}/assets/archive", {"ids": [], "archived": True}, format="json").status_code == 400
        )
        r = admin_client.post(
            f"{API}/assets/archive", {"ids": ["8a3b2a52-0d6b-4b4e-9a53-3b6d1b0c1111"], "archived": True}, format="json"
        )
        assert r.json()["not_found"] == 1

    def test_engagement_scope_lists_every_identifier(self, w, admin_client, admin):
        org_services.update_asset(None, admin, w.asset_a, {"identifier": "shop.acme.test"})
        r = admin_client.get(f"{API}/engagements/{w.eng_a.pk}/assets")
        ids_ = r.json()[0]["asset"]["identifiers"]
        assert set(ids_) == {"https://shop.acme.test", "shop.acme.test"}


@pytest.mark.django_db
def test_pdf_scope_table_lists_every_identifier(w, admin, settings, tmp_path, django_capture_on_commit_callbacks):
    settings.MEDIA_ROOT = str(tmp_path)
    from apps.reports import services as report_services  # noqa: F401
    from tests.test_reports import done, download, pdf_text, request_report, seed

    org_services.update_asset(None, admin, w.asset_a, {"identifier": "shop-alt.acme.test"})
    p1c = signed_in(w.p1)
    seed(w, p1c, 1)
    job = done(p1c, request_report(p1c, w.eng_a, django_capture_on_commit_callbacks))
    text = pdf_text(download(p1c, job))
    assert "shop-alt.acme.test" in text and "shop.acme.test" in text
