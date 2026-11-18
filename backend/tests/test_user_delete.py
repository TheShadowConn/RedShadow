"""User deletion: confirmation, permissions, protected accounts, and what happens to related records."""

import pytest

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.engagements.models import EngagementMembership
from apps.findings.models import Finding
from apps.findings.services import reserve_refs
from apps.imports.models import ImportJob, ImportMapping
from apps.rbac.models import Role
from tests.conftest import Api, make_role, make_user, signed_in
from tests.world import build_world

USERS = "/api/v1/users"


@pytest.fixture
def w(admin):
    return build_world(admin)


def remove(client, user, email=None, **kw):
    return client.delete(
        f"{USERS}/{user.pk}", {"confirm_email": email if email is not None else user.email}, format="json"
    )


def deactivated(email="gone@example.com", role="pentester"):
    u = make_user(email, role)
    User.objects.filter(pk=u.pk).update(is_active=False)
    u.refresh_from_db()
    return u


def finding_by(user, w, **extra):
    return Finding.objects.create(
        ref=reserve_refs(1)[0], engagement=w.eng_a, title="t", severity="low", status=extra.pop("status", "open"),
        reported_by=user, discovered_at=w.today, dedupe_hash="z" * 64, **extra,
    )  # fmt: skip


@pytest.mark.django_db
class TestDelete:
    def test_unused_account_is_removed_outright(self, admin_client):
        u = deactivated()
        r = remove(admin_client, u)
        assert r.status_code == 200 and r.json()["mode"] == "remove"
        assert not User.objects.filter(pk=u.pk).exists()
        ev = AuditEvent.objects.filter(action="user.deleted").get()
        assert ev.entity_label == "gone@example.com" and ev.metadata["mode"] == "remove"

    def test_account_with_history_is_anonymised_and_cannot_come_back(self, w, admin_client):
        u = deactivated("author@example.com")
        f = finding_by(u, w)
        r = remove(admin_client, u)
        assert r.status_code == 200 and r.json()["mode"] == "anonymise"
        u.refresh_from_db()
        assert u.email.endswith("@deleted.invalid") and u.display_name == "Deleted user"
        assert not u.has_usable_password() and u.deleted_at and not u.is_active and not u.mfa_enabled
        f.refresh_from_db()
        assert f.reported_by_id == u.pk  # history keeps its shape
        assert "Findings" in r.json()["history"]
        # not listed, not reachable, cannot sign in, the address is free again
        assert u.pk not in [x["id"] for x in admin_client.get(USERS, {"page_size": 100}).json()["results"]]
        assert admin_client.get(f"{USERS}/{u.pk}").status_code == 404
        assert (
            Api()
            .post("/api/v1/auth/login", {"email": "author@example.com", "password": "x"}, format="json")
            .status_code
            == 401
        )
        again = admin_client.post(
            USERS,
            {
                "email": "author@example.com",
                "display_name": "New author",
                "role": str(Role.objects.get(system_key="pentester").pk),
            },
            format="json",
        )
        assert again.status_code == 201
        # the audit log still names the person
        assert AuditEvent.objects.filter(action="user.deleted", entity_label="author@example.com").exists()

    def test_confirmation_must_match(self, admin_client):
        u = deactivated()
        assert remove(admin_client, u, "someone@else.com").status_code == 400
        assert admin_client.delete(f"{USERS}/{u.pk}").status_code == 400  # no body at all
        assert remove(admin_client, u, "  GONE@Example.com ").status_code == 200  # case and spaces do not matter

    def test_active_account_must_be_deactivated_first(self, admin_client, pentester):
        r = remove(admin_client, pentester)
        assert r.status_code == 409 and "Deactivate" in r.json()["error"]["message"]
        assert User.objects.filter(pk=pentester.pk).exists()

    def test_memberships_mappings_and_open_work_are_cleaned_up(self, w, admin, admin_client):
        u = deactivated("busy@example.com")
        EngagementMembership.objects.create(engagement=w.eng_a, user=u, added_by=admin)
        ImportMapping.objects.create(owner=u, name="mine", column_map={}, value_map={})
        w.eng_b.lead = u
        w.eng_b.save()
        open_f = finding_by(w.p1, w, assigned_pentester=u, remediation_owner=u)
        closed_f = finding_by(w.p1, w, status="closed", assigned_pentester=u)
        impact = admin_client.get(f"{USERS}/{u.pk}/deletion-impact").json()
        assert impact["removes"]["memberships"] == 1 and impact["clears"]["engagements_led"] == 1
        assert impact["clears"]["findings_assigned"] == 1 and impact["blockers"] == []
        assert remove(admin_client, u).status_code == 200
        assert not EngagementMembership.objects.filter(user=u).exists()
        assert not ImportMapping.objects.filter(owner=u).exists()
        w.eng_b.refresh_from_db()
        assert w.eng_b.lead_id is None
        open_f.refresh_from_db()
        closed_f.refresh_from_db()
        assert open_f.assigned_pentester_id is None and open_f.remediation_owner_id is None
        assert closed_f.assigned_pentester_id == u.pk  # closed history is not rewritten

    def test_active_retest_round_blocks_deletion(self, w, admin, admin_client):
        from apps.findings.models import RetestRound

        u = deactivated("assessor@example.com")
        RetestRound.objects.create(engagement=w.eng_a, number=1, requested_by=admin, assessor=u, status="queued")
        r = remove(admin_client, u)
        assert r.status_code == 409 and "retest" in r.json()["error"]["message"]
        assert User.objects.get(pk=u.pk).deleted_at is None

    def test_running_import_blocks_deletion(self, w, admin_client):
        u = deactivated("importer@example.com")
        ImportJob.objects.create(
            engagement=w.eng_a,
            uploaded_by=u,
            original_name="x.csv",
            file_sha256="0" * 64,
            file_size=1,
            status="importing",
        )
        assert remove(admin_client, u).status_code == 409

    def test_deleting_twice_is_a_conflict(self, w, admin_client):
        u = deactivated("twice@example.com")
        finding_by(u, w)
        assert remove(admin_client, u).status_code == 200
        assert admin_client.delete(f"{USERS}/{u.pk}", {"confirm_email": "x"}, format="json").status_code == 404


@pytest.mark.django_db
class TestProtected:
    def test_cannot_delete_yourself(self, admin_client, admin):
        r = remove(admin_client, admin)
        assert r.status_code == 403
        assert User.objects.filter(pk=admin.pk).exists()
        assert AuditEvent.objects.filter(action="user.delete_denied", outcome="denied").exists()

    def test_a_deactivated_super_admin_can_be_deleted_by_another_super_admin(self, admin_client):
        other = deactivated("boss@example.com", "super_admin")
        assert remove(admin_client, other).status_code == 200

    def test_an_active_super_admin_must_be_deactivated_first(self, admin, admin_client):
        other = make_user("second@example.com", "super_admin")
        r = remove(admin_client, other)
        assert r.status_code == 409
        assert User.objects.filter(pk=other.pk).exists()

    def test_needs_the_delete_permission(self, w):
        role = make_role("User manager", ["users.view", "users.update", "users.deactivate"], all_engagements=True)
        c = signed_in(make_user("mgr@example.com", role))
        u = deactivated()
        assert remove(c, u).status_code == 403
        assert c.get(f"{USERS}/{u.pk}/deletion-impact").status_code == 403
        assert User.objects.filter(pk=u.pk).exists()

    def test_pentester_cannot_delete(self, pentester):
        u = deactivated()
        assert remove(signed_in(pentester), u).status_code == 403

    def test_cannot_delete_a_user_with_more_access(self, admin):
        role = make_role("Deleter", ["users.view", "users.delete", "users.deactivate"], all_engagements=True)
        c = signed_in(make_user("deleter@example.com", role))
        boss = deactivated("boss2@example.com", "super_admin")
        r = remove(c, boss)
        assert r.status_code == 403
        assert User.objects.filter(pk=boss.pk).exists()
        assert AuditEvent.objects.filter(action="user.delete_denied", outcome="denied").exists()

    def test_anonymous_is_refused(self, api, pentester):
        assert (
            api.delete(f"{USERS}/{pentester.pk}", {"confirm_email": pentester.email}, format="json").status_code == 401
        )

    def test_tombstones_cannot_be_managed(self, w, admin_client):
        u = deactivated("tomb@example.com")
        finding_by(u, w)
        remove(admin_client, u)
        for action in ("reactivate", "reset-password", "reset-mfa", "deactivate"):
            assert admin_client.post(f"{USERS}/{u.pk}/{action}").status_code == 404
