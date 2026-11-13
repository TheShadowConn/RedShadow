"""Section 3: External Vendor role. Own-scope isolation, publish rights, imports, exports, dashboard."""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.engagements.models import EngagementMembership
from apps.findings.models import Finding
from apps.rbac.catalogue import PERMISSIONS, SYSTEM_ROLES, VENDOR
from apps.rbac.models import Role
from tests.conftest import make_user, signed_in
from tests.test_findings import API, body, furl, ids, make, publish
from tests.test_imports import GOOD, commit, jurl, media_root, prepared, rows  # noqa: F401
from tests.world import build_world


def png() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (6, 6), "blue").save(out, "PNG")
    return out.getvalue()


@pytest.fixture
def w(admin):
    world = build_world(admin)
    world.v1 = make_user("v1@example.com", VENDOR)
    world.v2 = make_user("v2@example.com", VENDOR)
    for eng, user in ((world.eng_a, world.v1), (world.eng_a, world.v2), (world.eng_b, world.v1)):
        EngagementMembership.objects.create(engagement=eng, user=user, added_by=admin)
    return world


@pytest.fixture
def v1c(w):
    return signed_in(w.v1)


@pytest.fixture
def v2c(w):
    return signed_in(w.v2)


@pytest.fixture
def p1c(w):
    return signed_in(w.p1)


FORBIDDEN = {
    "findings.delete", "findings.assign", "findings.bulk_update", "findings.verify", "findings.close",
    "findings.reopen", "findings.risk_accept", "engagement_notes.view_team", "templates.manage",
    "organisations.create", "organisations.update", "engagements.create", "engagements.update",
    "reports.generate_pdf", "audit.view_engagement", "audit.view_all", "users.view", "roles.manage",
    "remediation.update_status", "retests.create", "retests.record", "documents.delete",
}  # fmt: skip


@pytest.mark.django_db
class TestRoleDefinition:
    def test_seeded_with_own_scope(self):
        role = Role.objects.get(system_key=VENDOR)
        assert role.name == "External Vendor"
        assert role.finding_scope == "own"
        assert not role.all_engagements
        assert set(role.role_permissions.values_list("permission_id", flat=True)) == set(SYSTEM_ROLES[VENDOR]["grants"])

    def test_grants_exclude_internal_powers(self):
        grants = set(SYSTEM_ROLES[VENDOR]["grants"])
        assert not FORBIDDEN & grants
        assert {"findings.publish", "imports.create", "findings.create", "evidence.upload"} <= grants
        assert "dashboards.vendor" in PERMISSIONS

    def test_admin_can_use_own_scope_on_custom_roles(self, admin_client):
        r = admin_client.post(
            f"{API}/roles", {"name": "Contractor", "finding_scope": "own", "permissions": []}, format="json"
        )
        assert r.status_code == 201, r.content
        assert r.json()["finding_scope"] == "own"


@pytest.mark.django_db
class TestOwnScope:
    def test_vendor_sees_only_own_findings(self, w, v1c, v2c, p1c):
        f1 = make(v1c, w.eng_a, title="Vendor one finding")
        f2 = make(v2c, w.eng_a, title="Vendor two finding")
        f3 = make(p1c, w.eng_a, title="Internal finding")
        assert ids(v1c.get(f"{API}/findings")) == {f1["id"]}
        assert ids(v2c.get(f"{API}/findings")) == {f2["id"]}
        assert {f1["id"], f2["id"], f3["id"]} <= ids(p1c.get(f"{API}/findings"))

    def test_other_findings_are_404_everywhere(self, w, v1c, v2c):
        f2 = make(v2c, w.eng_a)
        assert v1c.get(furl(f2)).status_code == 404
        assert v1c.patch(furl(f2), {"version": 1, "title": "x"}, format="json").status_code == 404
        assert v1c.post(furl(f2, "/publish"), {"version": 1}, format="json").status_code == 404
        assert v1c.get(furl(f2, "/notes")).status_code == 404
        assert v1c.get(furl(f2, "/evidence")).status_code == 404

    def test_assigned_internal_finding_becomes_visible(self, w, v1c, p1c):
        f = make(p1c, w.eng_a, title="Assigned to vendor")
        assert v1c.get(furl(f)).status_code == 404
        Finding.objects.filter(pk=f["id"]).update(assigned_pentester=w.v1)
        assert v1c.get(furl(f)).status_code == 200

    def test_no_access_to_engagement_without_membership(self, w, v2c):
        assert v2c.post(f"{API}/findings", body(w.eng_b), format="json").status_code in (400, 403, 404)
        assert Finding.objects.filter(engagement=w.eng_b).count() == 0
        assert all(e["id"] != str(w.eng_b.pk) for e in v2c.get(f"{API}/engagements").json()["results"])

    def test_same_vendor_on_two_engagements_sees_both(self, w, v1c):
        a = make(v1c, w.eng_a, title="On Acme")
        b = make(v1c, w.eng_b, title="On Borealis")
        assert ids(v1c.get(f"{API}/findings")) == {a["id"], b["id"]}

    def test_export_contains_only_own_rows(self, w, v1c, v2c):
        make(v1c, w.eng_a, title="Mine alpha")
        make(v2c, w.eng_a, title="Theirs beta")
        text = b"".join(v1c.get(f"{API}/findings/export.csv").streaming_content).decode()
        assert "Mine alpha" in text and "Theirs beta" not in text

    def test_membership_can_override_scope(self, w, v1c, v2c):
        f2 = make(v2c, w.eng_a)
        EngagementMembership.objects.filter(engagement=w.eng_a, user=w.v1).update(finding_scope="all")
        assert v1c.get(furl(f2)).status_code == 200


@pytest.mark.django_db
class TestVendorPowers:
    def test_vendor_publishes_own_finding(self, w, v1c):
        f = make(v1c, w.eng_a)
        assert f["status"] == "draft"
        assert publish(v1c, f)["status"] == "open"

    def test_vendor_cannot_verify_close_assign_or_delete(self, w, v1c):
        f = publish(v1c, make(v1c, w.eng_a))
        assert v1c.delete(furl(f)).status_code == 403
        r = v1c.post(furl(f, "/transition"), {"to": "closed", "version": f["version"]}, format="json")
        assert r.status_code in (400, 403)
        r = v1c.post(f"{API}/findings/bulk", {"action": "publish", "ids": [f["id"]]}, format="json")
        assert r.status_code == 403
        assert v1c.get(f"{API}/queues/verification").status_code == 403
        assert v1c.post(f"{API}/reports", {}, format="json").status_code == 403

    def test_vendor_cannot_reach_admin_surfaces(self, v1c):
        for path in ("/users", "/roles", "/report-templates", "/dashboards/admin", "/dashboards/pentester"):
            assert v1c.get(f"{API}{path}").status_code == 403, path

    def test_vendor_dashboard(self, w, v1c, p1c):
        make(v1c, w.eng_a)
        make(p1c, w.eng_a, title="Not the vendor's")
        r = v1c.get(f"{API}/dashboards/vendor")
        assert r.status_code == 200
        assert r.json()["mine"]["drafts"] == 1
        assert p1c.get(f"{API}/dashboards/vendor").status_code == 403

    def test_evidence_upload_follows_finding_scope(self, w, v1c, v2c):
        f = make(v1c, w.eng_a)
        up = SimpleUploadedFile("shot.png", png(), "image/png")
        assert v2c.post(furl(f, "/evidence"), {"file": up}, format="multipart").status_code == 404
        up = SimpleUploadedFile("shot.png", png(), "image/png")
        assert v1c.post(furl(f, "/evidence"), {"file": up}, format="multipart").status_code == 201


@pytest.mark.django_db
class TestVendorImports:
    def test_vendor_imports_findings_as_own(self, w, v1c, v2c, media_root):  # noqa: F811
        job = prepared(v1c, w.eng_a, [GOOD])
        assert commit(v1c, job).status_code == 202
        imported = Finding.objects.get(source="import")
        assert imported.reported_by_id == w.v1.pk
        assert ids(v1c.get(f"{API}/findings")) == {str(imported.pk)}
        assert v2c.get(f"{API}/findings").json()["results"] == []

    def test_other_vendors_cannot_see_import_jobs(self, w, v1c, v2c, p1c, media_root):  # noqa: F811
        job = prepared(v1c, w.eng_a, [GOOD])
        assert v2c.get(jurl(job)).status_code == 404
        assert v2c.get(jurl(job, "/rows")).status_code == 404
        assert v2c.get(f"{API}/imports").json()["results"] == []
        assert v1c.get(jurl(job)).status_code == 200
        assert p1c.get(jurl(job)).status_code == 200

    def test_duplicate_check_does_not_reveal_other_vendors_findings(self, w, v1c, v2c, media_root):  # noqa: F811
        job1 = prepared(v1c, w.eng_a, [GOOD])
        assert commit(v1c, job1).status_code == 202
        job2 = prepared(v2c, w.eng_a, [GOOD])
        assert [r["status"] for r in rows(v2c, job2)] == ["valid"]


@pytest.mark.django_db
class TestAdoptCustomRole:
    def test_existing_custom_role_with_the_same_name_becomes_the_system_role(self):
        from apps.rbac.models import RolePermission
        from apps.rbac.seed import seed_rbac

        Role.objects.filter(system_key=VENDOR).delete()
        legacy = Role.objects.create(name="External Vendor", finding_scope="all", all_engagements=False)
        RolePermission.objects.create(role=legacy, permission_id="findings.delete")
        user = make_user("legacy@example.com", legacy)
        seed_rbac()
        legacy.refresh_from_db()
        user.refresh_from_db()
        assert legacy.system_key == VENDOR and legacy.finding_scope == "own"
        assert set(legacy.role_permissions.values_list("permission_id", flat=True)) == set(
            SYSTEM_ROLES[VENDOR]["grants"]
        )
        assert user.role_id == legacy.pk and user.session_version == 2
        assert Role.objects.filter(name="External Vendor").count() == 1
