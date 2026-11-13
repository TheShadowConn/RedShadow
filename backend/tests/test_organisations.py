import pytest

from tests.conftest import make_role, make_user, signed_in
from tests.world import build_world

API = "/api/v1"


@pytest.fixture
def w(admin):
    return build_world(admin)


def ids(response):
    return {row["id"] for row in response.json()["results"]}


@pytest.mark.django_db
class TestOrganisationsAdmin:
    def test_crud_and_validation(self, admin_client):
        r = admin_client.post(f"{API}/organisations", {"name": "Cobalt", "industry": "Energy"}, format="json")
        assert r.status_code == 201 and r.json()["slug"] == "cobalt"
        oid = r.json()["id"]
        assert admin_client.post(f"{API}/organisations", {"name": "cobalt"}, format="json").status_code == 400
        assert (
            admin_client.post(f"{API}/organisations", {"name": "X", "slug": "evil"}, format="json").status_code == 400
        )
        assert admin_client.post(f"{API}/organisations", {"name": "  "}, format="json").status_code == 400
        r = admin_client.patch(f"{API}/organisations/{oid}", {"industry": "Utilities"}, format="json")
        assert r.status_code == 200 and r.json()["industry"] == "Utilities"
        assert admin_client.patch(f"{API}/organisations/{oid}", {"archived_at": None}, format="json").status_code == 400

    def test_archive_rules(self, admin_client, w):
        assert admin_client.post(f"{API}/organisations/{w.org_a.pk}/archive").status_code == 409  # open engagement
        r = admin_client.post(f"{API}/organisations", {"name": "Empty Org"}, format="json")
        oid = r.json()["id"]
        assert admin_client.post(f"{API}/organisations/{oid}/archive").json()["archived"] is True
        assert admin_client.patch(f"{API}/organisations/{oid}", {"notes": "x"}, format="json").status_code == 409
        assert oid not in ids(admin_client.get(f"{API}/organisations"))
        assert oid in ids(admin_client.get(f"{API}/organisations?archived=true"))
        assert admin_client.get(f"{API}/organisations/{oid}").status_code == 200
        assert admin_client.post(f"{API}/organisations/{oid}/unarchive").json()["archived"] is False


@pytest.mark.django_db
class TestOrganisationIsolation:
    def test_pentester_sees_only_own_engagement_org(self, w):
        c = signed_in(w.p1)
        assert ids(c.get(f"{API}/organisations")) == {str(w.org_a.pk)}
        assert c.get(f"{API}/organisations/{w.org_a.pk}").status_code == 200
        assert c.get(f"{API}/organisations/{w.org_b.pk}").status_code == 404
        assert ids(c.get(f"{API}/organisations?search=Borealis")) == set()

    def test_non_member_sees_nothing(self, w):
        c = signed_in(w.p3)
        assert ids(c.get(f"{API}/organisations")) == set()
        assert c.get(f"{API}/organisations/{w.org_a.pk}").status_code == 404
        assert ids(c.get(f"{API}/assets")) == set()
        assert ids(c.get(f"{API}/contacts")) == set()

    def test_writes_forbidden_for_non_admin(self, w):
        for user in (w.p1, w.r1):
            c = signed_in(user)
            assert c.post(f"{API}/organisations", {"name": "Hax"}, format="json").status_code == 403
            assert c.patch(f"{API}/organisations/{w.org_a.pk}", {"notes": "x"}, format="json").status_code == 403
            assert c.post(f"{API}/organisations/{w.org_a.pk}/archive").status_code == 403

    def test_remediation_member_reads_own_org(self, w):
        c = signed_in(w.r1)
        assert ids(c.get(f"{API}/organisations")) == {str(w.org_a.pk)}


@pytest.mark.django_db
class TestContacts:
    def test_admin_crud_and_primary_exclusive(self, admin_client, w):
        r = admin_client.post(
            f"{API}/contacts", {"organisation": str(w.org_a.pk), "name": "Carl", "is_primary": True}, format="json"
        )
        assert r.status_code == 201
        w.contact_a.refresh_from_db()
        assert w.contact_a.is_primary is False
        cid = r.json()["id"]
        assert admin_client.patch(f"{API}/contacts/{cid}", {"phone": "123"}, format="json").status_code == 200
        assert (
            admin_client.post(
                f"{API}/contacts", {"organisation": str(w.org_a.pk), "name": "Bad", "email": "nope"}, format="json"
            ).status_code
            == 400
        )
        assert admin_client.delete(f"{API}/contacts/{cid}").status_code == 204

    def test_pentester_reads_own_org_contacts_only(self, w):
        c = signed_in(w.p1)
        assert ids(c.get(f"{API}/contacts")) == {str(w.contact_a.pk)}
        assert c.get(f"{API}/contacts/{w.contact_b.pk}").status_code == 404
        assert c.get(f"{API}/organisations/{w.org_b.pk}/contacts").status_code == 404
        assert c.patch(f"{API}/contacts/{w.contact_a.pk}", {"phone": "1"}, format="json").status_code == 403
        assert c.delete(f"{API}/contacts/{w.contact_a.pk}").status_code == 403
        assert (
            c.post(f"{API}/contacts", {"organisation": str(w.org_a.pk), "name": "x"}, format="json").status_code == 403
        )

    def test_organisation_id_injection_rejected(self, w):
        # role may update organisations only in scope... but a role with the write code reaches all orgs,
        # so injection is tested on the read side: unreachable org id is "nonexistent"
        c = signed_in(w.p1)
        assert c.get(f"{API}/contacts?organisation={w.org_b.pk}").json()["results"] == []
        assert c.get(f"{API}/contacts?organisation=not-a-uuid").json()["results"] == []


@pytest.mark.django_db
class TestAssets:
    def test_admin_crud_and_new_types(self, admin_client, w):
        for t in ("wireless", "iot", "active_directory", "thick_client"):
            r = admin_client.post(
                f"{API}/assets",
                {"organisation": str(w.org_a.pk), "name": f"A-{t}", "type": t, "identifier": f"id-{t}"},
                format="json",
            )
            assert r.status_code == 201, r.content
        aid = r.json()["id"]
        r = admin_client.patch(
            f"{API}/assets/{aid}", {"criticality": 5, "environment": "staging", "tags": ["pci"]}, format="json"
        )
        assert r.status_code == 200 and r.json()["criticality"] == 5
        assert (
            admin_client.patch(f"{API}/assets/{aid}", {"organisation": str(w.org_b.pk)}, format="json").status_code
            == 400
        )
        assert admin_client.patch(f"{API}/assets/{aid}", {"criticality": 6}, format="json").status_code == 400
        assert admin_client.patch(f"{API}/assets/{aid}", {"type": "nonsense"}, format="json").status_code == 400
        dup = {
            "organisation": str(w.org_a.pk),
            "name": "dup",
            "type": "web_app",
            "identifier": "https://shop.acme.test",
        }
        assert admin_client.post(f"{API}/assets", dup, format="json").status_code == 400
        assert admin_client.post(f"{API}/assets/{aid}/archive").json()["archived"] is True
        assert admin_client.patch(f"{API}/assets/{aid}", {"name": "x"}, format="json").status_code == 409
        assert admin_client.post(f"{API}/assets/{aid}/unarchive").json()["archived"] is False

    def test_pentester_sees_only_linked_assets(self, w):
        c = signed_in(w.p1)
        assert ids(c.get(f"{API}/assets")) == {str(w.asset_a.pk)}
        assert c.get(f"{API}/assets/{w.asset_b.pk}").status_code == 404
        assert c.get(f"{API}/organisations/{w.org_a.pk}/assets").status_code == 200
        assert c.get(f"{API}/organisations/{w.org_b.pk}/assets").status_code == 404
        assert (
            c.post(
                f"{API}/assets", {"organisation": str(w.org_a.pk), "name": "x", "type": "api"}, format="json"
            ).status_code
            == 403
        )

    def test_unlinked_asset_of_visible_org_is_hidden(self, admin, w):
        from apps.organisations import services

        spare = services.create_asset(
            None, admin, w.org_a, {"name": "Spare", "type": "api", "identifier": "https://api.acme.test"}
        )
        c = signed_in(w.p1)
        assert c.get(f"{API}/assets/{spare.pk}").status_code == 404
        listed = {a["id"] for a in c.get(f"{API}/organisations/{w.org_a.pk}/assets").json()}
        assert listed == {str(w.asset_a.pk)}


@pytest.mark.django_db
def test_custom_role_with_org_write_codes_can_work_without_membership(w):
    role = make_role("Org Manager", ["organisations.view", "organisations.update", "assets.view"])
    user = make_user("om@example.com", role)
    c = signed_in(user)
    assert ids(c.get(f"{API}/organisations")) == {str(w.org_a.pk), str(w.org_b.pk)}
    assert c.patch(f"{API}/organisations/{w.org_a.pk}", {"notes": "ok"}, format="json").status_code == 200


@pytest.mark.django_db
def test_org_services_leave_audit_chain_valid(admin, w):
    from apps.audit.service import verify_chain

    assert verify_chain().ok
