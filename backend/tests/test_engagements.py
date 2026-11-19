from datetime import date, timedelta

import pytest
from django.db import IntegrityError, transaction

from apps.audit.models import AuditEvent
from apps.audit.service import verify_chain
from apps.engagements import services
from apps.engagements.models import EngagementAsset, EngagementMembership
from apps.rbac.models import Role
from tests.conftest import make_role, make_user, signed_in
from tests.world import build_world

API = "/api/v1"


@pytest.fixture
def w(admin):
    return build_world(admin)


def ids(response):
    return {row["id"] for row in response.json()["results"]}


def url(eng, tail=""):
    return f"{API}/engagements/{eng.pk}{tail}"


@pytest.mark.django_db
class TestCreateAndRefs:
    def test_ref_format_sequence_and_lead_membership(self, w):
        year = date.today().year
        assert w.eng_a.ref == f"RS-E-{year}-0001" and w.eng_b.ref == f"RS-E-{year}-0002"
        assert EngagementMembership.objects.filter(engagement=w.eng_a, user=w.p1).exists()

    def test_create_validations(self, admin_client, w):
        body = {
            "organisation": str(w.org_a.pk),
            "name": "N",
            "type": "api",
            "start_date": "2026-03-10",
            "end_date": "2026-03-01",
            "lead": str(w.p1.pk),
        }
        assert admin_client.post(f"{API}/engagements", body, format="json").status_code == 400
        body["end_date"] = "2026-03-20"
        assert admin_client.post(f"{API}/engagements", {**body, "type": "bogus"}, format="json").status_code == 400
        assert admin_client.post(f"{API}/engagements", {**body, "ref": "RS-E-1"}, format="json").status_code == 400
        assert admin_client.post(f"{API}/engagements", {**body, "version": 9}, format="json").status_code == 400
        r = admin_client.post(f"{API}/engagements", body, format="json")
        assert r.status_code == 201 and r.json()["version"] == 1 and "engagements.view" in r.json()["permissions"]

    def test_inactive_lead_and_unknown_org(self, admin_client, w):
        body = {
            "organisation": str(w.org_a.pk),
            "name": "N",
            "type": "api",
            "start_date": "2026-03-01",
            "end_date": "2026-03-20",
        }
        w.p3.is_active = False
        w.p3.save()
        assert admin_client.post(f"{API}/engagements", {**body, "lead": str(w.p3.pk)}, format="json").status_code == 400
        assert (
            admin_client.post(
                f"{API}/engagements", {**body, "organisation": "00000000-0000-0000-0000-000000000000"}, format="json"
            ).status_code
            == 400
        )

    def test_org_not_reachable_cannot_be_injected(self, w):
        role = make_role("Engagement Creator", ["engagements.create", "engagements.view"])
        c = signed_in(make_user("creator@example.com", role))
        body = {
            "organisation": str(w.org_a.pk),
            "name": "N",
            "type": "api",
            "start_date": "2026-03-01",
            "end_date": "2026-03-20",
        }
        r = c.post(f"{API}/engagements", body, format="json")
        assert r.status_code == 400 and "organisation" in r.json()["error"]["fields"]

    def test_pentester_cannot_create(self, w):
        body = {
            "organisation": str(w.org_a.pk),
            "name": "N",
            "type": "api",
            "start_date": "2026-03-01",
            "end_date": "2026-03-20",
        }
        assert signed_in(w.p1).post(f"{API}/engagements", body, format="json").status_code == 403

    def test_archived_org_rejected(self, admin, admin_client, w):
        from apps.engagements.models import Engagement

        Engagement.objects.all().update(status="completed")
        from apps.organisations import services as org_services

        org_services.archive_organisation(None, admin, w.org_a)
        body = {
            "organisation": str(w.org_a.pk),
            "name": "N",
            "type": "api",
            "start_date": "2026-03-01",
            "end_date": "2026-03-20",
            "lead": str(w.p1.pk),
        }
        assert admin_client.post(f"{API}/engagements", body, format="json").status_code == 409


@pytest.mark.django_db
def test_ref_counter_is_per_year_and_locks_its_row():
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as ctx:
        first, second = services.next_ref(2030), services.next_ref(2030)
    assert (first, second, services.next_ref(2031)) == ("RS-E-2030-0001", "RS-E-2030-0002", "RS-E-2031-0001")
    # concurrent creates serialise on this row lock (a real multi-connection race cannot run here:
    # transactional tests would TRUNCATE the append-only audit table, which the database forbids)
    assert any("FOR UPDATE" in q["sql"] for q in ctx.captured_queries)


@pytest.mark.django_db
class TestOptimisticLockAndLifecycle:
    def test_stale_version_conflicts(self, admin_client, w):
        r = admin_client.patch(url(w.eng_a), {"name": "Renamed", "version": 1}, format="json")
        assert r.status_code == 200 and r.json()["version"] == 2
        assert admin_client.patch(url(w.eng_a), {"name": "Again", "version": 1}, format="json").status_code == 409
        assert admin_client.patch(url(w.eng_a), {"name": "No version"}, format="json").status_code == 400
        assert (
            admin_client.patch(url(w.eng_a), {"organisation": str(w.org_b.pk), "version": 2}, format="json").status_code
            == 400
        )
        assert (
            admin_client.patch(url(w.eng_a), {"end_date": "2000-01-01", "version": 2}, format="json").status_code == 400
        )

    def test_status_transitions(self, admin_client, w):
        def go(status, version):
            return admin_client.post(url(w.eng_a, "/status"), {"status": status, "version": version}, format="json")

        assert go("completed", 1).status_code == 400  # planned -> completed not allowed
        assert go("scheduled", 1).json()["version"] == 2
        assert go("in_progress", 1).status_code == 409  # stale
        assert go("in_progress", 2).status_code == 200
        assert go("archived", 3).status_code == 400

    def test_pentester_member_changes_status_non_member_gets_404(self, w):
        assert (
            signed_in(w.p1)
            .post(url(w.eng_a, "/status"), {"status": "scheduled", "version": 1}, format="json")
            .status_code
            == 200
        )
        assert (
            signed_in(w.p3)
            .post(url(w.eng_a, "/status"), {"status": "scheduled", "version": 2}, format="json")
            .status_code
            == 404
        )
        assert (
            signed_in(w.p2)
            .post(url(w.eng_a, "/status"), {"status": "scheduled", "version": 2}, format="json")
            .status_code
            == 404
        )

    def test_remediation_member_cannot_change_status(self, w):
        assert (
            signed_in(w.r1)
            .post(url(w.eng_a, "/status"), {"status": "scheduled", "version": 1}, format="json")
            .status_code
            == 403
        )

    def test_archive_flow_and_read_only(self, admin_client, w):
        assert (
            admin_client.post(url(w.eng_a, "/archive"), {"version": 1}, format="json").status_code == 409
        )  # not completed
        w.eng_a.status = "completed"
        w.eng_a.save()
        r = admin_client.post(url(w.eng_a, "/archive"), {"version": 1}, format="json")
        assert r.status_code == 200 and r.json()["status"] == "archived"
        assert admin_client.patch(url(w.eng_a), {"name": "x", "version": 2}, format="json").status_code == 409
        assert admin_client.post(url(w.eng_a, "/notes"), {"body": "hi"}, format="json").status_code == 409
        assert admin_client.post(url(w.eng_a, "/members"), {"user": str(w.p3.pk)}, format="json").status_code == 409
        assert w.eng_a.pk not in {r["id"] for r in admin_client.get(f"{API}/engagements").json()["results"]}
        assert admin_client.get(f"{API}/engagements?archived=true").json()["count"] == 1
        r = admin_client.post(url(w.eng_a, "/unarchive"), {"version": 2}, format="json")
        assert r.status_code == 200 and r.json()["status"] == "completed"

    def test_delete_is_not_allowed(self, admin_client, w):
        assert admin_client.delete(url(w.eng_a)).status_code == 405
        assert signed_in(w.p1).delete(url(w.eng_a)).status_code == 403

    def test_overdue_is_derived(self, admin_client, w):
        from apps.engagements.models import Engagement

        Engagement.objects.filter(pk=w.eng_a.pk).update(
            start_date=date.today() - timedelta(days=20), end_date=date.today() - timedelta(days=5)
        )
        rows = {r["ref"]: r["overdue"] for r in admin_client.get(f"{API}/engagements").json()["results"]}
        assert rows[w.eng_a.ref] is True and rows[w.eng_b.ref] is False
        assert admin_client.get(f"{API}/engagements?overdue=true").json()["count"] == 1


@pytest.mark.django_db
class TestIsolation:
    def test_lists_and_details(self, admin_client, w):
        assert ids(admin_client.get(f"{API}/engagements")) == {str(w.eng_a.pk), str(w.eng_b.pk)}
        assert ids(signed_in(w.p1).get(f"{API}/engagements")) == {str(w.eng_a.pk)}
        assert ids(signed_in(w.p2).get(f"{API}/engagements")) == {str(w.eng_b.pk)}
        assert ids(signed_in(w.r1).get(f"{API}/engagements")) == {str(w.eng_a.pk)}
        assert ids(signed_in(w.p3).get(f"{API}/engagements")) == set()

    def test_every_sub_resource_is_404_out_of_scope(self, w):
        c = signed_in(w.p1)
        for tail in ("", "/members", "/assets", "/notes", "/history"):
            assert c.get(url(w.eng_b, tail)).status_code == 404, tail
        assert c.post(url(w.eng_b, "/notes"), {"body": "x"}, format="json").status_code == 404
        assert c.patch(url(w.eng_b), {"name": "x", "version": 1}, format="json").status_code == 403  # no platform perm

    def test_search_filter_ordering_cannot_leak(self, w):
        c = signed_in(w.p1)
        assert c.get(f"{API}/engagements?search=Borealis").json()["count"] == 0
        assert c.get(f"{API}/engagements?organisation={w.org_b.pk}").json()["count"] == 0
        assert c.get(f"{API}/engagements?type=internal_network").json()["count"] == 0
        assert c.get(f"{API}/engagements?ordering=-secret_field").json()["count"] == 1
        assert c.get(f"{API}/engagements?organisation=zzz").json()["count"] == 0

    def test_counts_match_scoped_list(self, w):
        c = signed_in(w.p1)
        body = c.get(f"{API}/engagements").json()
        assert body["count"] == len(body["results"]) == 1

    def test_inactive_user_loses_everything(self, w):
        c = signed_in(w.p1)
        w.p1.is_active = False
        w.p1.save()
        assert c.get(f"{API}/engagements").status_code in (401, 403)


@pytest.mark.django_db
class TestMembership:
    def test_admin_adds_and_removes_member(self, admin_client, w):
        version = w.p3.session_version
        r = admin_client.post(url(w.eng_b, "/members"), {"user": str(w.p3.pk)}, format="json")
        assert r.status_code == 201
        w.p3.refresh_from_db()
        assert w.p3.session_version == version + 1
        assert ids(signed_in(w.p3).get(f"{API}/engagements")) == {str(w.eng_b.pk)}
        assert admin_client.post(url(w.eng_b, "/members"), {"user": str(w.p3.pk)}, format="json").status_code == 409
        assert admin_client.delete(url(w.eng_b, f"/members/{w.p3.pk}")).status_code == 204
        assert ids(signed_in(w.p3).get(f"{API}/engagements")) == set()

    def test_member_endpoint_validation(self, admin_client, w):
        w.p3.is_active = False
        w.p3.save()
        assert admin_client.post(url(w.eng_b, "/members"), {"user": str(w.p3.pk)}, format="json").status_code == 400
        assert admin_client.post(url(w.eng_b, "/members"), {"user": "nope"}, format="json").status_code == 400
        assert (
            admin_client.post(
                url(w.eng_b, "/members"), {"user": str(w.p1.pk), "finding_scope": "x"}, format="json"
            ).status_code
            == 400
        )
        assert (
            admin_client.patch(
                url(w.eng_b, f"/members/{w.p1.pk}"), {"finding_scope": "assigned"}, format="json"
            ).status_code
            == 404
        )
        assert admin_client.delete(url(w.eng_b, "/members/not-a-uuid")).status_code == 404

    def test_lead_cannot_be_removed(self, admin_client, w):
        assert admin_client.delete(url(w.eng_a, f"/members/{w.p1.pk}")).status_code == 409

    def test_role_override_limits_object_permissions(self, admin_client, w):
        rem = Role.objects.get(system_key="remediation")
        r = admin_client.post(
            url(w.eng_b, "/members"),
            {"user": str(w.p3.pk), "role_override": str(rem.pk), "finding_scope": "assigned"},
            format="json",
        )
        assert r.status_code == 201 and r.json()["role"]["name"] == "Remediation"
        c = signed_in(w.p3)
        assert c.get(url(w.eng_b)).status_code == 200
        assert c.post(url(w.eng_b, "/status"), {"status": "scheduled", "version": 1}, format="json").status_code == 403
        assert "engagements.update_status" not in c.get(url(w.eng_b)).json()["permissions"]

    def test_delegate_cannot_escalate(self, admin_client, w):
        delegate_role = make_role("Delegate", ["engagements.view", "engagements.manage_members", "organisations.view"])
        delegate = make_user("delegate@example.com", delegate_role)
        admin_client.post(url(w.eng_b, "/members"), {"user": str(delegate.pk)}, format="json")
        c = signed_in(delegate)
        pen = Role.objects.get(system_key="pentester")
        # cannot add a user whose role is broader than the delegate's own
        assert c.post(url(w.eng_b, "/members"), {"user": str(w.p3.pk)}, format="json").status_code == 403
        # cannot grant an override role broader than their own permissions
        narrow = make_user("narrow@example.com", make_role("Narrow", ["engagements.view"]))
        assert (
            c.post(
                url(w.eng_b, "/members"), {"user": str(narrow.pk), "role_override": str(pen.pk)}, format="json"
            ).status_code
            == 403
        )
        assert c.post(url(w.eng_b, "/members"), {"user": str(narrow.pk)}, format="json").status_code == 201
        # cannot alter own membership
        assert (
            c.patch(url(w.eng_b, f"/members/{delegate.pk}"), {"finding_scope": "all"}, format="json").status_code == 403
        )
        denied = AuditEvent.objects.filter(action="engagement.member_denied", outcome="denied").count()
        assert denied >= 3

    def test_member_without_manage_permission_is_forbidden(self, w):
        assert signed_in(w.p1).post(url(w.eng_a, "/members"), {"user": str(w.p3.pk)}, format="json").status_code == 403

    def test_members_list_visible_to_members_only(self, w):
        assert signed_in(w.p1).get(url(w.eng_a, "/members")).status_code == 200
        assert signed_in(w.p3).get(url(w.eng_a, "/members")).status_code == 404


@pytest.mark.django_db
class TestScopeAssets:
    def test_admin_links_and_unlinks(self, admin, admin_client, w):
        from apps.organisations import services as org_services

        spare = org_services.create_asset(
            None, admin, w.org_a, {"name": "Spare", "type": "api", "identifier": "https://api.acme.test"}
        )
        r = admin_client.post(
            url(w.eng_a, "/assets"), {"asset": str(spare.pk), "in_scope": False, "notes": "later"}, format="json"
        )
        assert r.status_code == 201 and r.json()["in_scope"] is False
        lid = r.json()["id"]
        assert admin_client.post(url(w.eng_a, "/assets"), {"asset": str(spare.pk)}, format="json").status_code == 409
        assert (
            admin_client.patch(url(w.eng_a, f"/assets/{lid}"), {"in_scope": True}, format="json").json()["in_scope"]
            is True
        )
        assert admin_client.delete(url(w.eng_a, f"/assets/{lid}")).status_code == 204

    def test_other_organisation_asset_rejected_by_service_and_database(self, admin_client, w):
        r = admin_client.post(url(w.eng_a, "/assets"), {"asset": str(w.asset_b.pk)}, format="json")
        assert r.status_code == 400
        with pytest.raises(IntegrityError), transaction.atomic():
            EngagementAsset.objects.create(engagement=w.eng_a, asset=w.asset_b)

    def test_pentester_reads_but_cannot_link(self, w):
        c = signed_in(w.p1)
        assert len(c.get(url(w.eng_a, "/assets")).json()) == 1
        assert c.post(url(w.eng_a, "/assets"), {"asset": str(w.asset_a.pk)}, format="json").status_code == 403


@pytest.mark.django_db
class TestNotesAndHistory:
    def test_note_visibility_by_permission(self, w):
        pen, rem = signed_in(w.p1), signed_in(w.r1)
        assert pen.post(url(w.eng_a, "/notes"), {"body": "team secret"}, format="json").status_code == 201
        assert (
            pen.post(url(w.eng_a, "/notes"), {"body": "for everyone", "visibility": "all"}, format="json").status_code
            == 201
        )
        assert {n["body"] for n in pen.get(url(w.eng_a, "/notes")).json()["results"]} == {"team secret", "for everyone"}
        assert {n["body"] for n in rem.get(url(w.eng_a, "/notes")).json()["results"]} == {"for everyone"}
        assert rem.post(url(w.eng_a, "/notes"), {"body": "x"}, format="json").status_code == 403
        assert signed_in(w.p2).get(url(w.eng_a, "/notes")).status_code == 404
        assert pen.post(url(w.eng_a, "/notes"), {"body": "x", "visibility": "bogus"}, format="json").status_code == 400

    def test_history_is_scoped_and_complete(self, admin_client, w):
        admin_client.patch(url(w.eng_a), {"name": "Renamed", "version": 1}, format="json")
        rows = signed_in(w.p1).get(url(w.eng_a, "/history")).json()["results"]
        actions = {r["action"] for r in rows}
        assert {"engagement.created", "engagement.updated", "engagement.asset_linked"} <= actions
        assert all("Borealis" not in str(r) for r in rows)
        assert signed_in(w.r1).get(url(w.eng_a, "/history")).status_code == 200
        assert signed_in(w.p2).get(url(w.eng_a, "/history")).status_code == 404

    def test_audit_chain_still_verifies(self, admin_client, w):
        admin_client.post(url(w.eng_a, "/notes"), {"body": "x"}, format="json")
        assert verify_chain().ok
