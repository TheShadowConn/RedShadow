import os
from pathlib import Path

import pytest
from django.core.management import call_command
from django.urls import get_resolver
from rest_framework.permissions import AllowAny
from rest_framework.viewsets import ModelViewSet

from apps.rbac import authz
from apps.rbac.catalogue import ENGAGEMENT, PERMISSIONS, SYSTEM_ROLES, matrix_markdown
from apps.rbac.models import Permission, Role, RolePermission
from apps.rbac.seed import seed_rbac
from apps.rbac.viewsets import ScopedModelViewSet
from tests.conftest import make_user, signed_in


def walk(patterns):
    for p in patterns:
        if hasattr(p, "url_patterns"):
            yield from walk(p.url_patterns)
        else:
            yield p


def view_classes():
    for p in walk(get_resolver().url_patterns):
        cb = p.callback
        cls = getattr(cb, "cls", None) or getattr(cb, "view_class", None)
        if cls is not None:
            yield p, cls, getattr(cb, "actions", None)


@pytest.mark.django_db
class TestSeed:
    def test_catalogue_and_system_roles_seeded(self):
        assert Permission.objects.count() == len(PERMISSIONS)
        for key in SYSTEM_ROLES:
            assert Role.objects.filter(system_key=key).exists()
        sa = Role.objects.get(system_key="super_admin")
        assert set(sa.role_permissions.values_list("permission_id", flat=True)) == set(PERMISSIONS)
        assert sa.all_engagements and sa.mfa_required

    def test_default_role_boundaries(self):
        rem = set(Role.objects.get(system_key="remediation").role_permissions.values_list("permission_id", flat=True))
        pen = set(Role.objects.get(system_key="pentester").role_permissions.values_list("permission_id", flat=True))
        assert not {"users.view", "findings.create", "findings.view_draft", "findings.close", "findings.verify"} & rem
        assert "findings.view_draft" in pen and "users.view" not in pen and "roles.manage" not in pen
        assert Role.objects.get(system_key="remediation").finding_scope == "assigned"

    def test_seed_is_idempotent_and_keeps_admin_edits(self):
        RolePermission.objects.filter(role__system_key="pentester", permission_id="findings.close").delete()
        seed_rbac()
        seed_rbac()
        assert not RolePermission.objects.filter(role__system_key="pentester", permission_id="findings.close").exists()
        assert Role.objects.filter(system_key="pentester").count() == 1

    def test_super_admin_resynced_to_full_catalogue(self):
        RolePermission.objects.filter(role__system_key="super_admin", permission_id="findings.close").delete()
        seed_rbac()
        assert RolePermission.objects.filter(role__system_key="super_admin", permission_id="findings.close").exists()

    def test_matrix_doc_matches_catalogue(self):
        docs = os.environ.get("DOCS_DIR")
        path = Path(docs or "/nonexistent") / "RBAC_PERMISSION_MATRIX.md"
        if not path.exists():
            pytest.skip("DOCS_DIR not mounted")
        assert path.read_text(encoding="utf-8") == matrix_markdown()
        call_command("rbac_matrix", check=str(path))


@pytest.mark.django_db
class TestResolver:
    def test_platform_permissions(self, admin, pentester):
        assert authz.has_platform_perm(admin, "users.create")
        assert not authz.has_platform_perm(pentester, "users.create")

    def test_scope_mismatch_is_a_programming_error(self, admin):
        with pytest.raises(ValueError):
            authz.has_platform_perm(admin, "findings.view")
        with pytest.raises(ValueError):
            authz.has_engagement_perm(admin, "e1", "users.view")

    def test_inactive_user_has_nothing(self, pentester):
        pentester.is_active = False
        assert authz.user_permissions(pentester) == frozenset()
        assert authz.engagement_permissions(pentester, "e1") == frozenset()

    def test_all_engagement_role_reaches_every_engagement(self, admin):
        codes = authz.engagement_permissions(admin, "any-engagement")
        assert "findings.view" in codes and all(PERMISSIONS[c][0] == ENGAGEMENT for c in codes)

    def test_non_member_has_no_engagement_access(self, pentester):
        assert authz.engagement_permissions(pentester, "e1") == frozenset()

    def test_membership_provider_hook(self, pentester):
        pen_role = Role.objects.get(system_key="pentester")
        rem_role = Role.objects.get(system_key="remediation")
        grants = {"e-member": pen_role, "e-override": rem_role}
        provider = lambda user, eid: grants.get(eid)  # noqa: E731
        authz.register_membership_provider(provider)
        try:
            assert "findings.create" in authz.engagement_permissions(pentester, "e-member")
            assert "findings.create" not in authz.engagement_permissions(pentester, "e-override")
            assert authz.engagement_permissions(pentester, "e-other") == frozenset()
            assert authz.has_engagement_perm(pentester, "e-member", "findings.view")
        finally:
            authz.unregister_membership_provider(provider)

    def test_permission_cache_is_per_user_object(self, pentester):
        first = authz.user_permissions(pentester)
        RolePermission.objects.filter(role=pentester.role).delete()
        assert authz.user_permissions(pentester) == first  # cached on this request's user object
        fresh = type(pentester).objects.select_related("role").get(pk=pentester.pk)
        assert authz.user_permissions(fresh) == frozenset()  # next request sees the revocation


class TestRouteGuards:
    """Meta-tests: new routes cannot silently bypass the permission model."""

    def test_every_model_viewset_is_scoped(self):
        offenders = [
            cls.__name__
            for _, cls, _ in view_classes()
            if issubclass(cls, ModelViewSet) and not issubclass(cls, ScopedModelViewSet)
        ]
        assert offenders == []

    def test_scoped_viewset_requires_get_queryset(self):
        from django.core.exceptions import ImproperlyConfigured

        with pytest.raises(ImproperlyConfigured):
            ScopedModelViewSet().get_queryset()

    def test_every_viewset_action_has_a_permission(self):
        missing = []
        for _, cls, actions in view_classes():
            if issubclass(cls, ScopedModelViewSet) and actions:
                for method, action in actions.items():
                    if method in cls.http_method_names and action not in cls.permission_map:
                        missing.append(f"{cls.__name__}.{action}")
        assert missing == []

    def test_only_allowlisted_views_are_public(self):
        public = sorted({cls.__name__ for _, cls, _ in view_classes()
                         if any(issubclass(p, AllowAny) for p in getattr(cls, "permission_classes", []))})  # fmt: skip
        assert public == ["CsrfView", "LiveView", "LoginView", "ReadyView"]


# endpoint x role matrix scaffold (grows each phase). status codes by role key.
MATRIX = [
    ("GET", "/api/v1/users", None, {"super_admin": 200, "pentester": 403, "remediation": 403}),
    ("GET", "/api/v1/roles", None, {"super_admin": 200, "pentester": 403, "remediation": 403}),
    ("GET", "/api/v1/permissions", None, {"super_admin": 200, "pentester": 403, "remediation": 403}),
    ("GET", "/api/v1/auth/me", None, {"super_admin": 200, "pentester": 200, "remediation": 200}),
    ("POST", "/api/v1/users", {"email": "m@example.com", "display_name": "m", "role": "REMEDIATION"},
     {"super_admin": 201, "pentester": 403, "remediation": 403}),
    ("POST", "/api/v1/roles", {"name": "MatrixRole", "permissions": []},
     {"super_admin": 201, "pentester": 403, "remediation": 403}),
    ("GET", "/api/v1/organisations", None, {"super_admin": 200, "pentester": 200, "remediation": 200}),
    ("GET", "/api/v1/assets", None, {"super_admin": 200, "pentester": 200, "remediation": 200}),
    ("GET", "/api/v1/contacts", None, {"super_admin": 200, "pentester": 200, "remediation": 200}),
    ("GET", "/api/v1/engagements", None, {"super_admin": 200, "pentester": 200, "remediation": 200}),
    ("POST", "/api/v1/organisations", {"name": "MatrixOrg"},
     {"super_admin": 201, "pentester": 403, "remediation": 403}),
    ("POST", "/api/v1/engagements", {},
     {"super_admin": 400, "pentester": 403, "remediation": 403}),
    ("DELETE", "/api/v1/engagements/00000000-0000-0000-0000-000000000000", None,
     {"super_admin": 405, "pentester": 403, "remediation": 403}),
    ("GET", "/api/v1/findings", None, {"super_admin": 200, "pentester": 200, "remediation": 200}),
    ("GET", "/api/v1/cwes", None, {"super_admin": 200, "pentester": 200, "remediation": 200}),
    ("POST", "/api/v1/findings", {}, {"super_admin": 400, "pentester": 400, "remediation": 403}),
    ("POST", "/api/v1/findings/cvss", {"vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"},
     {"super_admin": 200, "pentester": 200, "remediation": 200}),
    ("POST", "/api/v1/findings/bulk", {"action": "publish", "ids": ["00000000-0000-0000-0000-000000000001"]},
     {"super_admin": 200, "pentester": 200, "remediation": 403}),
    ("DELETE", "/api/v1/findings/00000000-0000-0000-0000-000000000000", None,
     {"super_admin": 404, "pentester": 403, "remediation": 403}),
    ("PATCH", "/api/v1/findings/00000000-0000-0000-0000-000000000000", {"version": 1},
     {"super_admin": 404, "pentester": 404, "remediation": 403}),
    ("GET", "/api/v1/finding-templates", None, {"super_admin": 200, "pentester": 200, "remediation": 403}),
    ("POST", "/api/v1/finding-templates", {}, {"super_admin": 400, "pentester": 403, "remediation": 403}),
    ("GET", "/api/v1/findings/00000000-0000-0000-0000-000000000000/notes", None,
     {"super_admin": 404, "pentester": 404, "remediation": 404}),
    ("POST", "/api/v1/findings/00000000-0000-0000-0000-000000000000/transition", {"to": "open", "version": 1},
     {"super_admin": 404, "pentester": 404, "remediation": 404}),
    ("GET", "/api/v1/imports", None, {"super_admin": 200, "pentester": 200, "remediation": 403}),
    ("POST", "/api/v1/imports", {}, {"super_admin": 400, "pentester": 400, "remediation": 403}),
    ("GET", "/api/v1/imports/template.csv", None, {"super_admin": 200, "pentester": 200, "remediation": 403}),
    ("GET", "/api/v1/imports/00000000-0000-0000-0000-000000000000", None, {"super_admin": 404, "pentester": 404, "remediation": 403}),
    ("GET", "/api/v1/imports/00000000-0000-0000-0000-000000000000/rows", None, {"super_admin": 404, "pentester": 404, "remediation": 403}),
    ("GET", "/api/v1/imports/00000000-0000-0000-0000-000000000000/errors.csv", None, {"super_admin": 404, "pentester": 404, "remediation": 403}),
    ("POST", "/api/v1/imports/00000000-0000-0000-0000-000000000000/mapping", {}, {"super_admin": 404, "pentester": 404, "remediation": 403}),
    ("POST", "/api/v1/imports/00000000-0000-0000-0000-000000000000/commit", {}, {"super_admin": 404, "pentester": 404, "remediation": 403}),
    ("POST", "/api/v1/imports/00000000-0000-0000-0000-000000000000/cancel", {}, {"super_admin": 404, "pentester": 404, "remediation": 403}),
    ("GET", "/api/v1/import-mappings", None, {"super_admin": 200, "pentester": 200, "remediation": 403}),
    ("GET", "/api/v1/findings/export.csv", None, {"super_admin": 200, "pentester": 200, "remediation": 200}),
    ("GET", "/api/v1/calendar/events?start=2026-01-01&end=2026-02-01", None,
     {"super_admin": 200, "pentester": 200, "remediation": 200}),
    ("POST", "/api/v1/calendar/events/00000000-0000-0000-0000-000000000000/reschedule",
     {"start_date": "2026-01-01", "end_date": "2026-01-02", "version": 1},
     {"super_admin": 404, "pentester": 403, "remediation": 403}),
    ("GET", "/api/v1/audit/events", None, {"super_admin": 200, "pentester": 200, "remediation": 200}),
    ("GET", "/api/v1/audit/events/999999999", None, {"super_admin": 404, "pentester": 404, "remediation": 404}),
    ("GET", "/api/v1/audit/facets", None, {"super_admin": 200, "pentester": 200, "remediation": 200}),
    ("POST", "/api/v1/audit/verify", {}, {"super_admin": 202, "pentester": 403, "remediation": 403}),
    ("GET", "/api/v1/audit/integrity", None, {"super_admin": 200, "pentester": 403, "remediation": 403}),
    ("GET", "/api/v1/audit/export", None, {"super_admin": 200, "pentester": 403, "remediation": 403}),
    ("GET", "/api/v1/retest-rounds", None, {"super_admin": 200, "pentester": 200, "remediation": 200}),
    ("POST", "/api/v1/retest-rounds", {}, {"super_admin": 400, "pentester": 400, "remediation": 403}),
    ("GET", "/api/v1/retest-rounds/00000000-0000-0000-0000-000000000000", None,
     {"super_admin": 404, "pentester": 404, "remediation": 404}),
    ("POST", "/api/v1/retest-rounds/00000000-0000-0000-0000-000000000000/cancel", {"version": 1},
     {"super_admin": 404, "pentester": 404, "remediation": 404}),
    ("POST", "/api/v1/retest-rounds/00000000-0000-0000-0000-000000000000/assign", {"version": 1},
     {"super_admin": 404, "pentester": 404, "remediation": 404}),
    ("POST",
     "/api/v1/retest-rounds/00000000-0000-0000-0000-000000000000/items/00000000-0000-0000-0000-000000000000/result",
     {}, {"super_admin": 404, "pentester": 404, "remediation": 404}),
    ("GET", "/api/v1/retest-rounds/assessors?engagement=00000000-0000-0000-0000-000000000000", None,
     {"super_admin": 404, "pentester": 404, "remediation": 403}),
    ("GET", "/api/v1/queues/remediation", None, {"super_admin": 200, "pentester": 200, "remediation": 200}),
    ("GET", "/api/v1/queues/verification", None, {"super_admin": 200, "pentester": 200, "remediation": 403}),
    ("GET", "/api/v1/findings/00000000-0000-0000-0000-000000000000/activity", None,
     {"super_admin": 404, "pentester": 404, "remediation": 404}),
    ("GET", "/api/v1/findings/00000000-0000-0000-0000-000000000000/evidence", None,
     {"super_admin": 404, "pentester": 404, "remediation": 404}),
    ("DELETE", "/api/v1/findings/00000000-0000-0000-0000-000000000000/evidence/00000000-0000-0000-0000-000000000000",
     None, {"super_admin": 404, "pentester": 404, "remediation": 404}),
    ("GET", "/api/v1/reports", None, {"super_admin": 200, "pentester": 200, "remediation": 403}),
    ("GET", "/api/v1/report-templates", None, {"super_admin": 200, "pentester": 200, "remediation": 403}),
    ("POST", "/api/v1/reports", {}, {"super_admin": 400, "pentester": 400, "remediation": 403}),
    ("POST", "/api/v1/report-templates", {}, {"super_admin": 400, "pentester": 403, "remediation": 403}),
    ("GET", "/api/v1/reports/00000000-0000-0000-0000-000000000000", None, {"super_admin": 404, "pentester": 404, "remediation": 403}),
    ("GET", "/api/v1/reports/00000000-0000-0000-0000-000000000000/download", None, {"super_admin": 404, "pentester": 404, "remediation": 403}),
    ("DELETE", "/api/v1/report-templates/00000000-0000-0000-0000-000000000000", None, {"super_admin": 404, "pentester": 403, "remediation": 403}),
    ("GET", "/api/v1/report-templates/00000000-0000-0000-0000-000000000000/logo", None, {"super_admin": 404, "pentester": 403, "remediation": 403}),
    ("GET", "/api/v1/dashboards/admin", None, {"super_admin": 200, "pentester": 403, "remediation": 403}),
    ("GET", "/api/v1/dashboards/pentester", None, {"super_admin": 200, "pentester": 200, "remediation": 403}),
    ("GET", "/api/v1/dashboards/remediation", None, {"super_admin": 200, "pentester": 403, "remediation": 200}),
]  # fmt: skip


@pytest.mark.django_db
@pytest.mark.parametrize("method,path,body,expected", MATRIX)
@pytest.mark.parametrize("role_key", ["super_admin", "pentester", "remediation"])
def test_rbac_matrix(role_key, method, path, body, expected, admin):
    user = admin if role_key == "super_admin" else make_user(f"{role_key}@example.com", role_key)
    client = signed_in(user)
    if body and body.get("role") == "REMEDIATION":
        body = {**body, "role": str(Role.objects.get(system_key="remediation").pk)}
    response = client.generic(
        method, path, __import__("json").dumps(body) if body else "", content_type="application/json"
    )
    assert response.status_code == expected[role_key]


# Every named /api/v1 route must be listed here once its role behaviour is covered by a test
# (MATRIX above or the admin/auth suites). A new route fails this test until it is added.
COVERED_ROUTES = {
    "about",  # tests/test_about.py
    "auth-csrf", "auth-login", "auth-logout", "auth-me", "auth-password-change", "auth-sessions-revoke",
    "auth-mfa-setup", "auth-mfa-confirm", "auth-mfa-verify",
    "user-list", "user-detail", "user-deactivate", "user-reactivate", "user-reset-password",
    "user-reset-mfa", "user-revoke-sessions", "role-list", "role-detail", "permission-list",
    # Phase 3: covered by tests/test_organisations.py and tests/test_engagements.py
    "organisation-list", "organisation-detail", "organisation-archive", "organisation-unarchive",
    "organisation-assets", "organisation-contacts", "contact-list", "contact-detail",
    "asset-list", "asset-detail", "asset-archive", "asset-unarchive",
    "engagement-list", "engagement-detail", "engagement-archive", "engagement-unarchive",
    "engagement-change-status", "engagement-members", "engagement-update-member",
    "engagement-assets", "engagement-update-asset-link", "engagement-notes", "engagement-history",
    # Engagement costs: covered by tests/test_costs.py
    "engagement-costs", "engagement-update-cost",
    # Section A (lead, delete, join): covered by tests/test_engagement_lifecycle.py
    "engagement-change-lead", "engagement-delete-engagement", "engagement-join", "engagement-restore", "engagement-clone",
    # Section E: own notifications only, covered by tests/test_notifications.py
    "notification-list", "notification-unread-count", "notification-read", "notification-read-all", "notification-settings",
    # Phase 3B: covered by tests/test_files.py
    "engagement-documents", "organisation-logo", "attachment-list", "attachment-detail", "attachment-download",
    # Phase 4A: covered by tests/test_findings.py and the MATRIX rows above
    "finding-list", "finding-detail", "finding-publish", "finding-mark-false-positive", "finding-mark-duplicate",
    "finding-transition", "finding-activity", "finding-history", "finding-bulk", "finding-cvss", "cwe-list", "cwe-detail",
    # Phase 4B: covered by tests/test_findings_extras.py and the MATRIX rows above
    # Phase 5B: covered by tests/test_retests.py and the MATRIX rows above
    "retest-round-list", "retest-round-detail", "retest-round-assign", "retest-round-cancel",
    "retest-round-record-result", "retest-round-assessors", "queue-remediation", "queue-verification",
    # Phase 8: covered by tests/test_imports.py, tests/test_findings_export.py and the MATRIX rows above
    "import-list", "import-detail", "import-set-mapping", "import-rows", "import-commit", "import-cancel",
    "import-errors", "import-template", "import-mapping-list", "import-mapping-detail", "finding-export",
    # Phase 7: covered by tests/test_calendar.py and the MATRIX rows above
    "calendar-events", "calendar-reschedule",
    # Phase 6A: covered by tests/test_audit_explorer.py and the MATRIX rows above
    "audit-events", "audit-event", "audit-facets", "audit-verify", "audit-integrity", "audit-export",
    # Phase 9: covered by tests/test_reports.py and the MATRIX rows above
    "report-list", "report-detail", "report-download", "report-template-list", "report-template-detail",
    "report-template-logo",
    # Phase 10: covered by tests/test_dashboards.py and the MATRIX rows above
    "dashboard-admin", "dashboard-pentester", "dashboard-remediation", "dashboard-vendor",
    # Assets, identifiers, onboarding, import management, user deletion: tests/test_assets.py, tests/test_asset_imports.py,
    # tests/test_import_management.py, tests/test_user_delete.py
    "asset-summary", "asset-usage", "asset-identifiers", "asset-identifier-detail", "asset-check-identifiers",
    "asset-onboard", "asset-onboard-many", "asset-archive-many", "asset-merge", "import-reupload", "import-retry", "import-history",
    "import-asset-template", "user-deletion-impact",
    "finding-notes", "finding-evidence", "finding-remove-evidence", "finding-template-list", "finding-template-detail",
}  # fmt: skip


def test_every_route_is_covered_by_a_test():
    names = {p.name for p, _, _ in view_classes() if p.name and not p.name.startswith("health-")}
    assert names - COVERED_ROUTES == set(), "new route without role-matrix coverage"
    assert COVERED_ROUTES - names == set(), "stale entry in COVERED_ROUTES"
