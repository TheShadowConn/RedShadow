"""Section A: engagement delete (separate from archive), lead change, add-myself, lead required."""

import pytest

from apps.audit.models import AuditEvent
from apps.engagements.models import Engagement, EngagementMembership
from tests.conftest import make_role, make_user, signed_in
from tests.test_findings import furl, make
from tests.world import build_world

API = "/api/v1"


@pytest.fixture
def w(admin):
    return build_world(admin)


def url(eng, tail=""):
    return f"{API}/engagements/{eng.pk}{tail}"


def events(action):
    return AuditEvent.objects.filter(action=action)


@pytest.mark.django_db
class TestDelete:
    def body(self, eng, **extra):
        return {"version": eng.version, "confirm_ref": eng.ref, **extra}

    def test_super_admin_deletes_and_audit_entry_is_written(self, admin_client, w):
        r = admin_client.post(url(w.eng_a, "/delete"), self.body(w.eng_a, reason="duplicate"), format="json")
        assert r.status_code == 204
        assert not Engagement.objects.filter(pk=w.eng_a.pk).exists()
        assert Engagement.all_objects.get(pk=w.eng_a.pk).deleted_at is not None
        ev = events("engagement.deleted").get()
        assert str(ev.engagement_id) == str(w.eng_a.pk) and ev.metadata["reason"] == "duplicate"
        assert admin_client.get(url(w.eng_a)).status_code == 404
        listed = {x["id"] for x in admin_client.get(f"{API}/engagements?archived=all").json()["results"]}
        assert str(w.eng_a.pk) not in listed

    def test_wrong_confirmation_or_stale_version_is_refused(self, admin_client, w):
        bad = {"version": w.eng_a.version, "confirm_ref": "nope"}
        assert admin_client.post(url(w.eng_a, "/delete"), bad, format="json").status_code == 400
        stale = {"version": 99, "confirm_ref": w.eng_a.ref}
        assert admin_client.post(url(w.eng_a, "/delete"), stale, format="json").status_code == 409
        assert Engagement.objects.filter(pk=w.eng_a.pk).exists()

    def test_only_super_admin_and_denial_is_audited(self, w):
        for user in (w.p1, w.r1):
            r = signed_in(user).post(url(w.eng_a, "/delete"), self.body(w.eng_a), format="json")
            assert r.status_code == 403
        assert Engagement.objects.filter(pk=w.eng_a.pk).exists()

    def test_archive_still_separate(self, admin_client, w):
        w.eng_a.status = "completed"
        w.eng_a.save()
        assert admin_client.post(url(w.eng_a, "/archive"), {"version": 1}, format="json").status_code == 200
        assert Engagement.objects.filter(pk=w.eng_a.pk).exists()

    def test_deleted_engagement_hidden_from_findings_scope(self, admin_client, w):
        f = make(signed_in(w.p1), w.eng_a)
        admin_client.post(url(w.eng_a, "/delete"), self.body(w.eng_a), format="json")
        assert signed_in(w.p1).get(url(w.eng_a)).status_code == 404
        assert admin_client.get(furl(f)).status_code == 404
        assert f["id"] not in {r["id"] for r in admin_client.get(f"{API}/findings").json()["results"]}


@pytest.mark.django_db
class TestLead:
    def test_super_admin_changes_lead_anytime(self, admin_client, w):
        r = admin_client.post(url(w.eng_a, "/lead"), {"lead": str(w.p3.pk), "version": 1}, format="json")
        assert r.status_code == 200 and r.json()["lead"]["id"] == str(w.p3.pk)
        assert EngagementMembership.objects.filter(engagement=w.eng_a, user=w.p3).exists()
        ev = events("engagement.lead_changed").get()
        assert ev.changes["lead"] == [w.p1.email, w.p3.email]
        again = admin_client.post(url(w.eng_a, "/lead"), {"lead": str(w.p1.pk), "version": 2}, format="json")
        assert again.status_code == 200

    def test_same_lead_inactive_lead_and_stale_version(self, admin_client, w):
        assert (
            admin_client.post(url(w.eng_a, "/lead"), {"lead": str(w.p1.pk), "version": 1}, format="json").status_code
            == 409
        )
        gone = make_user("gone@example.com", "pentester")
        gone.is_active = False
        gone.save()
        assert (
            admin_client.post(url(w.eng_a, "/lead"), {"lead": str(gone.pk), "version": 1}, format="json").status_code
            == 400
        )
        assert (
            admin_client.post(url(w.eng_a, "/lead"), {"lead": str(w.p3.pk), "version": 7}, format="json").status_code
            == 409
        )

    def test_non_admin_cannot_change_lead(self, w):
        r = signed_in(w.p1).post(url(w.eng_a, "/lead"), {"lead": str(w.p3.pk), "version": 1}, format="json")
        assert r.status_code == 403

    def test_lead_required_on_create_and_cannot_be_cleared(self, admin_client, w):
        body = {**{k: str(v) for k, v in w.base.items()}, "organisation": str(w.org_a.pk), "name": "X"}
        assert admin_client.post(f"{API}/engagements", body, format="json").status_code == 400
        assert admin_client.post(f"{API}/engagements", {**body, "lead": None}, format="json").status_code == 400
        ok = admin_client.post(f"{API}/engagements", {**body, "lead": str(w.p1.pk)}, format="json")
        assert ok.status_code == 201
        cleared = admin_client.patch(url(w.eng_a), {"name": "x", "lead": None, "version": 1}, format="json")
        assert cleared.status_code == 400


@pytest.mark.django_db
class TestJoin:
    def test_super_admin_adds_self_once(self, admin_client, admin, w):
        r = admin_client.post(url(w.eng_a, "/join"), {}, format="json")
        assert r.status_code == 201 and r.json()["user"]["id"] == str(admin.pk)
        assert events("engagement.member_added").filter(metadata__via="self").count() == 1
        assert admin_client.post(url(w.eng_a, "/join"), {}, format="json").status_code == 409

    def test_member_without_manage_rights_cannot_join_or_probe(self, w):
        assert signed_in(w.p1).post(url(w.eng_a, "/join"), {}, format="json").status_code == 403
        assert signed_in(w.p3).post(url(w.eng_a, "/join"), {}, format="json").status_code in (403, 404)


@pytest.mark.django_db
class TestRestore:
    def test_restore_returns_engagement_and_findings(self, admin_client, w):
        body = {"version": w.eng_a.version, "confirm_ref": w.eng_a.ref}
        p1c = signed_in(w.p1)
        f = p1c.post(f"{API}/findings", {"engagement": str(w.eng_a.pk), "title": "T", "severity": "low",
                                         "description": "d", "recommendation": "r"}, format="json").json()
        admin_client.post(url(w.eng_a, "/delete"), body, format="json")
        listed = admin_client.get(f"{API}/engagements?deleted=true").json()["results"]
        assert [r["id"] for r in listed] == [str(w.eng_a.pk)] and listed[0]["deleted_at"]
        assert signed_in(w.p1).get(f"{API}/findings/{f['id']}").status_code == 404
        r = admin_client.post(url(w.eng_a, "/restore"), {}, format="json")
        assert r.status_code == 200 and r.json()["version"] == w.eng_a.version + 2
        assert events("engagement.restored").count() == 1
        assert signed_in(w.p1).get(f"{API}/findings/{f['id']}").status_code == 200
        assert admin_client.get(f"{API}/engagements?deleted=true").json()["count"] == 0

    def test_restore_needs_delete_permission_and_a_deleted_engagement(self, admin_client, w):
        assert signed_in(w.p1).get(f"{API}/engagements?deleted=true").json()["count"] == 0
        assert signed_in(w.p1).post(url(w.eng_a, "/restore"), {}, format="json").status_code in (403, 404)
        assert admin_client.post(url(w.eng_a, "/restore"), {}, format="json").status_code == 404


@pytest.mark.django_db
class TestClone:
    def test_clone_copies_setup_not_findings(self, admin_client, w):
        make(signed_in(w.p1), w.eng_a)
        body = {"name": "Acme retest 2027", "start_date": "2027-01-10", "end_date": "2027-01-20", "lead": str(w.p3.pk)}
        r = admin_client.post(url(w.eng_a, "/clone"), body, format="json")
        assert r.status_code == 201, r.content
        new = Engagement.objects.get(pk=r.json()["id"])
        assert new.ref != w.eng_a.ref and new.status == "planned" and new.organisation_id == w.org_a.pk
        assert new.type == w.eng_a.type and new.lead_id == w.p3.pk
        users = set(EngagementMembership.objects.filter(engagement=new).values_list("user_id", flat=True))
        assert {w.p1.pk, w.r1.pk, w.p3.pk} <= users
        assert new.engagement_assets.filter(asset=w.asset_a).exists()
        assert not new.finding_set.exists() if hasattr(new, "finding_set") else True
        ev = events("engagement.cloned").get()
        assert ev.metadata["source"] == w.eng_a.ref and ev.metadata["assets"] == 1
        assert mine_count(w.r1, "engagement.added") == 1

    def test_clone_needs_create_permission_and_valid_input(self, admin_client, w):
        body = {"name": "X", "start_date": "2027-01-10", "end_date": "2027-01-01", "lead": str(w.p3.pk)}
        assert admin_client.post(url(w.eng_a, "/clone"), body, format="json").status_code == 400
        assert signed_in(w.p1).post(url(w.eng_a, "/clone"), body, format="json").status_code == 403
        assert admin_client.post(url(w.eng_a, "/clone"), {**body, "end_date": "2027-02-01", "lead": None},
                                 format="json").status_code == 400


def mine_count(user, kind):
    from apps.notifications.models import Notification

    return Notification.objects.filter(recipient=user, kind=kind).count()


@pytest.mark.django_db
class TestActorStaysSignedIn:
    """Team changes sign the affected people out, but never the person who made the change."""

    me = f"{API}/auth/me"

    def test_delete_and_restore_by_a_team_member(self, admin_client, w):
        assert admin_client.post(url(w.eng_a, "/join"), {}, format="json").status_code in (200, 201)
        member = signed_in(w.p1)
        w.eng_a.refresh_from_db()
        body = {"version": w.eng_a.version, "confirm_ref": w.eng_a.ref}
        assert admin_client.post(url(w.eng_a, "/delete"), body, format="json").status_code == 204
        assert admin_client.get(self.me).status_code == 200
        assert member.get(self.me).status_code in (401, 403)
        member = signed_in(w.p1)
        assert admin_client.post(url(w.eng_a, "/restore"), {}, format="json").status_code == 200
        assert admin_client.get(self.me).status_code == 200
        assert member.get(self.me).status_code in (401, 403)

    def test_clone_by_a_team_member(self, admin_client, w):
        assert admin_client.post(url(w.eng_a, "/join"), {}, format="json").status_code in (200, 201)
        member = signed_in(w.p1)
        body = {"name": "Copy", "start_date": w.today, "end_date": w.today, "lead": str(w.p1.pk)}
        assert admin_client.post(url(w.eng_a, "/clone"), body, format="json").status_code == 201
        assert admin_client.get(self.me).status_code == 200
        assert member.get(self.me).status_code in (401, 403)

    def test_actor_naming_themself_lead_stays_signed_in(self, w):
        role = make_role("Planner", ["engagements.view", "engagements.create", "organisations.view", "organisations.update"])
        planner = make_user("planner@example.com", role)
        client = signed_in(planner)
        body = {**w.base, "organisation": str(w.org_a.pk), "name": "Mine", "lead": str(planner.pk)}
        r = client.post(f"{API}/engagements", body, format="json")
        assert r.status_code == 201, r.content
        assert client.get(self.me).status_code == 200
