import pytest

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.rbac.models import Role
from tests.conftest import PASSWORD, Api, make_role, make_user, signed_in

USERS = "/api/v1/users"
ROLES = "/api/v1/roles"


def role_id(key):
    return str(Role.objects.get(system_key=key).pk)


def audit_actions():
    return list(AuditEvent.objects.values_list("action", flat=True))


@pytest.mark.django_db
class TestUserAdmin:
    def test_only_users_view_can_list(self, admin_client, pentester, remediation, api):
        assert admin_client.get(USERS).status_code == 200
        assert signed_in(pentester).get(USERS).status_code == 403
        assert signed_in(remediation).get(USERS).status_code == 403
        assert api.get(USERS).status_code == 401

    def test_create_returns_temp_password_once_and_forces_change(self, admin_client):
        r = admin_client.post(
            USERS,
            {"email": "New.User@Example.com", "display_name": "New", "role": role_id("remediation")},
            format="json",
        )
        assert r.status_code == 201, r.content
        body = r.json()
        temp = body["temporary_password"]
        assert body["email"] == "new.user@example.com" and body["must_change_password"] is True
        assert "temporary_password" not in admin_client.get(f"{USERS}/{body['id']}").json()
        login = Api().login(User.objects.get(pk=body["id"]), temp)
        assert login.json()["restriction"] == "password_change"
        event = AuditEvent.objects.get(action="user.created")
        assert temp not in str(event.changes) + str(event.metadata)

    def test_duplicate_email_case_insensitive(self, admin_client, pentester):
        r = admin_client.post(
            USERS, {"email": "PEN@example.com", "display_name": "x", "role": role_id("pentester")}, format="json"
        )
        assert r.status_code == 400 and "email" in r.json()["error"]["fields"]

    def test_mass_assignment_rejected(self, admin_client, pentester):
        for field, value in [
            ("is_active", False),
            ("session_version", 99),
            ("mfa_enabled", True),
            ("password", "x"),
            ("email", "h@example.com"),
            ("failed_login_count", 0),
        ]:
            r = admin_client.patch(f"{USERS}/{pentester.pk}", {field: value}, format="json")
            assert r.status_code == 400, field
            assert field in r.json()["error"]["fields"]
        pentester.refresh_from_db()
        assert pentester.is_active and pentester.session_version == 1
        r = admin_client.post(
            USERS,
            {"email": "a@example.com", "display_name": "a", "role": role_id("pentester"), "is_active": False},
            format="json",
        )
        assert r.status_code == 400

    def test_response_never_exposes_secrets(self, admin_client, admin):
        body = admin_client.get(f"{USERS}/{admin.pk}").json()
        assert not {"password", "mfa_secret", "mfa_secret_enc", "session_version"} & set(body)

    def test_nobody_changes_own_role_even_super_admin(self, admin_client, admin):
        r = admin_client.patch(f"{USERS}/{admin.pk}", {"role": role_id("pentester")}, format="json")
        assert r.status_code == 403
        assert "user.role_change_denied" in audit_actions()
        assert AuditEvent.objects.get(action="user.role_change_denied").outcome == "denied"

    def test_cannot_deactivate_self(self, admin_client, admin):
        assert admin_client.post(f"{USERS}/{admin.pk}/deactivate").status_code == 403

    def test_role_change_bumps_sessions(self, admin_client, pentester):
        victim = signed_in(pentester)
        r = admin_client.patch(f"{USERS}/{pentester.pk}", {"role": role_id("remediation")}, format="json")
        assert r.status_code == 200 and r.json()["role"]["name"] == "Remediation"
        assert victim.get("/api/v1/auth/me").status_code == 401
        assert "user.role_changed" in audit_actions()

    def test_deactivate_reactivate(self, admin_client, pentester):
        victim = signed_in(pentester)
        assert admin_client.post(f"{USERS}/{pentester.pk}/deactivate").status_code == 200
        assert victim.get("/api/v1/auth/me").status_code == 401
        assert (
            Api()
            .post("/api/v1/auth/login", {"email": pentester.email, "password": PASSWORD}, format="json")
            .status_code
            == 401
        )
        assert admin_client.post(f"{USERS}/{pentester.pk}/reactivate").status_code == 200
        assert Api().login(pentester).status_code == 200

    def test_last_super_admin_cannot_be_deactivated_or_demoted(self, admin):
        everything = make_role(
            "Everything", list(__import__("apps.rbac.catalogue", fromlist=["x"]).PERMISSIONS), all_engagements=True
        )
        deputy = make_user("deputy@example.com", everything)
        c = signed_in(deputy)
        assert c.post(f"{USERS}/{admin.pk}/deactivate").status_code == 403
        assert c.patch(f"{USERS}/{admin.pk}", {"role": str(everything.pk)}, format="json").status_code == 403
        admin.refresh_from_db()
        assert admin.is_active and admin.role.system_key == "super_admin"

    def test_second_super_admin_can_be_deactivated(self, admin_client, admin):
        other = make_user("sa2@example.com", "super_admin")
        assert admin_client.post(f"{USERS}/{other.pk}/deactivate").status_code == 200

    def test_reset_password(self, admin_client, pentester):
        victim = signed_in(pentester)
        r = admin_client.post(f"{USERS}/{pentester.pk}/reset-password")
        temp = r.json()["temporary_password"]
        assert victim.get("/api/v1/auth/me").status_code == 401
        assert (
            Api()
            .post("/api/v1/auth/login", {"email": pentester.email, "password": PASSWORD}, format="json")
            .status_code
            == 401
        )
        assert Api().login(pentester, temp).json()["restriction"] == "password_change"
        assert temp not in str(AuditEvent.objects.get(action="user.password_reset").metadata)

    def test_reset_mfa(self, admin_client):
        role = make_role("MFA", ["findings.view"], mfa_required=True)
        target = make_user("t@example.com", role, mfa_enabled=True)
        r = admin_client.post(f"{USERS}/{target.pk}/reset-mfa")
        assert r.status_code == 200 and r.json()["mfa_enabled"] is False
        assert "user.mfa_reset" in audit_actions()

    def test_revoke_sessions(self, admin_client, pentester):
        victim = signed_in(pentester)
        assert admin_client.post(f"{USERS}/{pentester.pk}/sessions/revoke").status_code == 204
        assert victim.get("/api/v1/auth/me").status_code == 401

    def test_pagination_search_and_cap(self, admin_client):
        for i in range(3):
            make_user(f"bulk{i}@example.com", "remediation")
        r = admin_client.get(USERS, {"search": "bulk", "page_size": 1000})
        assert r.json()["count"] == 3


@pytest.mark.django_db
class TestEscalation:
    def helpdesk(self):
        from apps.rbac.catalogue import SYSTEM_ROLES

        codes = set(SYSTEM_ROLES["remediation"]["grants"]) | {
            "users.view",
            "users.create",
            "users.update",
            "roles.assign",
            "roles.view",
        }
        return make_user("help@example.com", make_role("Helpdesk", codes))

    def test_cannot_assign_role_broader_than_own(self):
        c = signed_in(self.helpdesk())
        for key in ("super_admin", "pentester"):
            r = c.post(USERS, {"email": f"{key}@example.com", "display_name": "x", "role": role_id(key)}, format="json")
            assert r.status_code == 403, key
        ok = c.post(
            USERS, {"email": "okrem@example.com", "display_name": "x", "role": role_id("remediation")}, format="json"
        )
        assert ok.status_code == 201

    def test_cannot_manage_more_powerful_user(self, pentester):
        c = signed_in(self.helpdesk())
        assert c.post(f"{USERS}/{pentester.pk}/reset-password").status_code == 403
        assert c.patch(f"{USERS}/{pentester.pk}", {"display_name": "pwned"}, format="json").status_code == 403
        assert c.post(f"{USERS}/{pentester.pk}/reset-mfa").status_code == 403
        assert c.post(f"{USERS}/{pentester.pk}/deactivate").status_code == 403

    def test_without_roles_assign_cannot_set_roles(self):
        user = make_user("nr@example.com", make_role("NoAssign", ["users.view", "users.create", "users.update"]))
        c = signed_in(user)
        r = c.post(
            USERS, {"email": "z@example.com", "display_name": "x", "role": role_id("remediation")}, format="json"
        )
        assert r.status_code == 403

    def test_stale_session_after_demotion(self, admin_client, pentester):
        c = signed_in(pentester)
        admin_client.patch(f"{USERS}/{pentester.pk}", {"role": role_id("remediation")}, format="json")
        assert c.get(USERS).status_code == 401

    def test_denials_are_audited_with_actor(self, pentester):
        c = signed_in(self.helpdesk())
        c.post(USERS, {"email": "q@example.com", "display_name": "x", "role": role_id("super_admin")}, format="json")
        e = AuditEvent.objects.get(action="user.create_denied")
        assert e.outcome == "denied" and e.actor_label == "help@example.com"


@pytest.mark.django_db
class TestRoles:
    def payload(self, **kw):
        return {"name": "Auditor", "description": "read only", "permissions": ["findings.view", "audit.view_all"], **kw}

    def test_create_edit_delete_custom_role(self, admin_client):
        r = admin_client.post(ROLES, self.payload(), format="json")
        assert r.status_code == 201 and r.json()["permissions"] == ["audit.view_all", "findings.view"]
        rid = r.json()["id"]
        r = admin_client.patch(
            f"{ROLES}/{rid}", {"permissions": ["findings.view"], "mfa_required": True}, format="json"
        )
        assert r.json()["permissions"] == ["findings.view"] and r.json()["mfa_required"] is True
        assert admin_client.delete(f"{ROLES}/{rid}").status_code == 204
        assert {"role.created", "role.updated", "role.deleted"} <= set(audit_actions())

    def test_unknown_permission_rejected(self, admin_client):
        r = admin_client.post(ROLES, self.payload(permissions=["nope.nothing"]), format="json")
        assert r.status_code == 400

    def test_duplicate_name(self, admin_client):
        assert admin_client.post(ROLES, self.payload(name="Pentester"), format="json").status_code == 400

    def test_super_admin_immutable(self, admin_client):
        rid = role_id("super_admin")
        assert admin_client.patch(f"{ROLES}/{rid}", {"permissions": []}, format="json").status_code == 403
        assert admin_client.delete(f"{ROLES}/{rid}").status_code == 403

    def test_system_roles_not_deletable_or_renamable(self, admin_client):
        rid = role_id("pentester")
        assert admin_client.delete(f"{ROLES}/{rid}").status_code == 403
        assert admin_client.patch(f"{ROLES}/{rid}", {"name": "Hackers"}, format="json").status_code == 403
        assert admin_client.patch(f"{ROLES}/{rid}", {"description": "ok"}, format="json").status_code == 200

    def test_role_in_use_cannot_be_deleted(self, admin_client, pentester):
        assert admin_client.delete(f"{ROLES}/{role_id('pentester')}").status_code == 403  # system first
        custom = make_role("InUse", ["findings.view"])
        make_user("iu@example.com", custom)
        assert admin_client.delete(f"{ROLES}/{custom.pk}").status_code == 409

    def test_permission_change_forces_relogin_of_role_members(self, admin_client, remediation):
        c = signed_in(remediation)
        r = admin_client.patch(f"{ROLES}/{role_id('remediation')}", {"permissions": ["findings.view"]}, format="json")
        assert r.status_code == 200
        assert c.get("/api/v1/auth/me").status_code == 401

    def test_cannot_grant_permissions_you_do_not_hold(self):
        mgr = make_user("mgr@example.com", make_role("RoleMgr", ["roles.view", "roles.manage", "findings.view"]))
        c = signed_in(mgr)
        r = c.post(ROLES, self.payload(permissions=["findings.view", "users.create"]), format="json")
        assert r.status_code == 403
        ok = c.post(ROLES, self.payload(permissions=["findings.view"]), format="json")
        assert ok.status_code == 201

    def test_cannot_edit_own_role(self):
        role = make_role("RoleMgr", ["roles.view", "roles.manage", "findings.view"])
        c = signed_in(make_user("mgr@example.com", role))
        r = c.patch(
            f"{ROLES}/{role.pk}",
            {"permissions": ["roles.view", "roles.manage", "findings.view", "users.view"]},
            format="json",
        )
        assert r.status_code == 403

    def test_cannot_grant_all_engagements_without_having_it(self):
        mgr = make_user("mgr2@example.com", make_role("RoleMgr2", ["roles.view", "roles.manage"]))
        r = signed_in(mgr).post(ROLES, self.payload(permissions=[], all_engagements=True), format="json")
        assert r.status_code == 403

    def test_non_admins_cannot_read_roles_or_catalogue(self, pentester):
        c = signed_in(pentester)
        assert c.get(ROLES).status_code == 403
        assert c.get("/api/v1/permissions").status_code == 403

    def test_catalogue_listing(self, admin_client):
        r = admin_client.get("/api/v1/permissions")
        assert r.status_code == 200 and any(p["code"] == "findings.view" for p in r.json())
        assert admin_client.post("/api/v1/permissions", {}, format="json").status_code == 405


@pytest.mark.django_db
class TestAccountHygiene:
    def test_sign_out_everywhere_ends_all_sessions(self, admin_client, admin):
        from tests.conftest import signed_in

        other = signed_in(admin)
        assert other.get("/api/v1/auth/me").status_code == 200
        assert admin_client.post("/api/v1/auth/sessions/revoke", {}, format="json").status_code == 204
        assert admin_client.get("/api/v1/auth/me").status_code == 401
        assert other.get("/api/v1/auth/me").status_code == 401

    def test_me_reports_idle_limit_and_mfa_filter(self, admin_client, admin):
        from tests.conftest import make_user

        assert admin_client.get("/api/v1/auth/me").json()["session_idle_seconds"] > 0
        make_user("nomfa@example.com", "pentester")
        rows = admin_client.get("/api/v1/users?mfa=missing").json()["results"]
        assert "nomfa@example.com" in {r["email"] for r in rows}
        assert all(not r["mfa_enabled"] for r in rows)
        enabled = admin_client.get("/api/v1/users?mfa=enabled").json()["results"]
        assert all(r["mfa_enabled"] for r in enabled)
