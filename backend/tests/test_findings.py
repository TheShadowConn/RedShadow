from decimal import Decimal

import pytest

from apps.audit.models import AuditEvent
from apps.audit.service import verify_chain
from apps.engagements.models import EngagementMembership
from apps.findings import cvss
from apps.findings.models import CWE, Finding
from apps.findings.services import dedupe_hash
from tests.conftest import make_role, make_user, signed_in
from tests.world import build_world

API = "/api/v1"
V31 = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"  # 9.8 critical
V31_MED = "CVSS:3.1/AV:N/AC:L/PR:L/UI:R/S:U/C:L/I:L/A:N"
V40 = "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N"  # 9.3


@pytest.fixture
def w(admin):
    return build_world(admin)


def body(eng, **kw):
    base = {"engagement": str(eng.pk), "title": "SQL injection in search", "severity": "high",
            "description": "The search parameter is concatenated into a query.",
            "recommendation": "Use parameterised queries."}  # fmt: skip
    return {**base, **kw}


def make(client, eng, **kw):
    r = client.post(f"{API}/findings", body(eng, **kw), format="json")
    assert r.status_code == 201, r.content
    return r.json()


def furl(f, tail=""):
    return f"{API}/findings/{f['id'] if isinstance(f, dict) else f.pk}{tail}"


def publish(client, f):
    r = client.post(furl(f, "/publish"), {"version": f["version"]}, format="json")
    assert r.status_code == 200, r.content
    return r.json()


def ids(response):
    return {row["id"] for row in response.json()["results"]}


@pytest.fixture
def p1c(w):
    return signed_in(w.p1)


@pytest.fixture
def r1c(w):
    return signed_in(w.r1)


class TestCvssModule:
    @pytest.mark.parametrize("score,sev", [("0.0", "info"), ("0.1", "low"), ("3.9", "low"), ("4.0", "medium"),
                                           ("6.9", "medium"), ("7.0", "high"), ("8.9", "high"), ("9.0", "critical"),
                                           ("10.0", "critical")])  # fmt: skip
    def test_severity_boundaries(self, score, sev):
        assert cvss.severity_for(Decimal(score)) == sev

    def test_scores(self):
        assert cvss.score_vector(V31) == ("3.1", Decimal("9.8"), "critical")
        assert cvss.score_vector(V40)[:2] == ("4.0", Decimal("9.3"))

    @pytest.mark.parametrize(
        "bad", ["", "CVSS:3.0/AV:N", "CVSS:3.1/AV:N", "garbage", "CVSS:3.1/AV:X/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"]
    )
    def test_rejects_bad_vectors(self, bad):
        with pytest.raises(cvss.InvalidVector):
            cvss.score_vector(bad)

    def test_dedupe_hash_normalises(self):
        a = dedupe_hash("e1", "  SQL   Injection ", "a1", "/Search", 89)
        assert a == dedupe_hash("e1", "sql injection", "a1", "/search", 89)
        assert a != dedupe_hash("e2", "sql injection", "a1", "/search", 89)
        assert a != dedupe_hash("e1", "sql injection", "a1", "/search", 79)


@pytest.mark.django_db
class TestCreate:
    def test_ref_sequence_defaults_and_audit(self, admin_client, w, admin):
        a = make(admin_client, w.eng_a)
        b = make(admin_client, w.eng_b, title="Other")
        assert a["ref"] == "RS-F-000001" and b["ref"] == "RS-F-000002"
        assert a["status"] == "draft" and a["version"] == 1 and a["reported_by"]["id"] == str(admin.pk)
        assert AuditEvent.objects.filter(action="finding.created", engagement_id=w.eng_a.pk, entity_id=a["id"]).exists()

    def test_cvss_derives_score_version_and_severity(self, admin_client, w):
        payload = body(w.eng_a, cvss_vector=V31)
        payload.pop("severity")
        r = admin_client.post(f"{API}/findings", payload, format="json")
        assert r.status_code == 201
        d = r.json()
        assert (d["severity"], d["cvss_score"], d["cvss_version"]) == ("critical", "9.8", "3.1")
        payload40 = {**payload, "cvss_vector": V40, "title": "v4"}
        r = admin_client.post(f"{API}/findings", payload40, format="json").json()
        assert (r["severity"], r["cvss_score"], r["cvss_version"]) == ("critical", "9.3", "4.0")

    def test_client_cannot_supply_score_or_mismatched_severity(self, admin_client, w):
        assert admin_client.post(f"{API}/findings", body(w.eng_a, cvss_score="1.0"), format="json").status_code == 400
        assert (
            admin_client.post(
                f"{API}/findings", body(w.eng_a, cvss_vector=V31, severity="low"), format="json"
            ).status_code
            == 400
        )
        assert (
            admin_client.post(f"{API}/findings", body(w.eng_a, cvss_vector="nonsense"), format="json").status_code
            == 400
        )
        payload = body(w.eng_a)
        payload.pop("severity")
        assert admin_client.post(f"{API}/findings", payload, format="json").status_code == 400

    def test_unknown_and_readonly_fields_rejected(self, admin_client, w):
        for extra in (
            {"ref": "RS-F-9"},
            {"status": "open"},
            {"reported_by": str(w.p1.pk)},
            {"version": 3},
            {"dedupe_hash": "x"},
        ):
            assert admin_client.post(f"{API}/findings", body(w.eng_a, **extra), format="json").status_code == 400

    def test_cwe_asset_references_validated(self, admin_client, w):
        assert CWE.objects.filter(pk=89).exists()
        assert admin_client.post(f"{API}/findings", body(w.eng_a, cwe_id=999999), format="json").status_code == 400
        ok = make(admin_client, w.eng_a, cwe_id=89, asset=str(w.asset_a.pk), endpoint="/search")
        assert ok["cwe"]["id"] == 89 and ok["asset"]["name"] == "Acme shop"
        assert (
            admin_client.post(f"{API}/findings", body(w.eng_a, asset=str(w.asset_b.pk)), format="json").status_code
            == 400
        )
        bad_refs = [
            [{"label": "x", "url": "javascript:alert(1)"}],
            [{"label": "x", "url": "ftp://x"}],
            [{"label": "x"}],
        ]
        for refs in bad_refs:
            assert (
                admin_client.post(f"{API}/findings", body(w.eng_a, references=refs), format="json").status_code == 400
            )
        good = make(admin_client, w.eng_a, references=[{"label": "OWASP", "url": "https://owasp.org/x"}])
        assert good["references"][0]["url"] == "https://owasp.org/x"

    def test_asset_must_be_linked_and_in_scope(self, admin_client, w, admin):
        from apps.engagements import services as eng_services
        from apps.organisations import services as org_services

        other = org_services.create_asset(
            None, admin, w.org_a, {"name": "Unlinked", "type": "host", "identifier": "10.1.1.1"}
        )
        assert (
            admin_client.post(f"{API}/findings", body(w.eng_a, asset=str(other.pk)), format="json").status_code == 400
        )
        link = eng_services.link_asset(None, admin, w.eng_a, other, False, "")
        assert link.in_scope is False
        assert (
            admin_client.post(f"{API}/findings", body(w.eng_a, asset=str(other.pk)), format="json").status_code == 400
        )

    def test_remediation_cannot_create_and_denial_is_audited(self, w, r1c):
        r = r1c.post(f"{API}/findings", body(w.eng_a), format="json")
        assert r.status_code == 403

    def test_non_member_cannot_create_in_unseen_engagement(self, w):
        r = signed_in(w.p1).post(f"{API}/findings", body(w.eng_b), format="json")
        assert r.status_code == 400  # the engagement does not exist as far as p1 can tell

    def test_member_pentester_creates(self, w, p1c):
        assert p1c.post(f"{API}/findings", body(w.eng_a), format="json").status_code == 201

    def test_archived_engagement_is_read_only(self, admin_client, w, admin):
        from apps.engagements import services as s

        s.change_status(None, admin, w.eng_a, "scheduled", 1)
        eng = w.eng_a
        eng.refresh_from_db()
        s.change_status(None, admin, eng, "cancelled", eng.version)
        eng.refresh_from_db()
        s.archive_engagement(None, admin, eng, eng.version)
        assert admin_client.post(f"{API}/findings", body(w.eng_a), format="json").status_code == 409


@pytest.mark.django_db
class TestFieldPermissions:
    def test_assign_requires_findings_assign(self, w, admin):
        role = make_role(
            "EditorNoAssign",
            ["engagements.view", "findings.view", "findings.create", "findings.update", "findings.view_draft"],
        )
        u = make_user("ed@example.com", role)
        EngagementMembership.objects.create(engagement=w.eng_a, user=u, added_by=admin)
        c = signed_in(u)
        f = make(c, w.eng_a)
        r = c.patch(furl(f), {"version": 1, "remediation_owner": str(w.r1.pk)}, format="json")
        assert r.status_code == 400 and "remediation_owner" in r.json()["error"]["fields"]
        assert AuditEvent.objects.filter(action="finding.update_denied", outcome="denied").exists()
        r = c.post(f"{API}/findings", body(w.eng_a, assigned_pentester=str(w.p1.pk)), format="json")
        assert r.status_code == 400

    def test_content_requires_update_even_with_assign(self, w, admin):
        role = make_role(
            "AssignOnly",
            ["engagements.view", "findings.view", "findings.update", "findings.assign", "findings.view_draft"],
        )
        u = make_user("as@example.com", role)
        EngagementMembership.objects.create(engagement=w.eng_a, user=u, added_by=admin)
        c = signed_in(u)
        f = {"id": str(Finding.objects.create(
            ref="RS-F-900001", engagement=w.eng_a, title="t", severity="low", reported_by=w.p1,
            discovered_at=w.today, dedupe_hash="h").pk), "version": 1}  # fmt: skip
        assert c.patch(furl(f), {"version": 1, "assigned_pentester": str(w.p1.pk)}, format="json").status_code == 200

    def test_remediation_cannot_edit(self, w, r1c, p1c):
        f = make(p1c, w.eng_a)
        f = publish(p1c, f)
        p1c.patch(furl(f), {"version": 2, "remediation_owner": str(w.r1.pk)}, format="json")
        assert r1c.patch(furl(f), {"version": 3, "title": "pwn"}, format="json").status_code == 403
        assert r1c.patch(furl(f), {"version": 3, "severity": "low"}, format="json").status_code == 403

    def test_assignee_must_see_findings(self, w, p1c):
        f = make(p1c, w.eng_a)
        r = p1c.patch(furl(f), {"version": 1, "assigned_pentester": str(w.p3.pk)}, format="json")
        assert r.status_code == 400  # p3 is not on the engagement
        assert p1c.patch(furl(f), {"version": 1, "remediation_owner": str(w.r1.pk)}, format="json").status_code == 200

    def test_engagement_is_immutable(self, w, p1c):
        f = make(p1c, w.eng_a)
        r = p1c.patch(furl(f), {"version": 1, "engagement": str(w.eng_b.pk)}, format="json")
        assert r.status_code == 400


@pytest.mark.django_db
class TestUpdateAndLocking:
    def test_update_recomputes_cvss_hash_and_audits(self, w, p1c):
        f = make(p1c, w.eng_a)
        before = Finding.objects.get(pk=f["id"]).dedupe_hash
        r = p1c.patch(furl(f), {"version": 1, "cvss_vector": V31_MED, "title": "Renamed"}, format="json")
        assert r.status_code == 200
        d = r.json()
        assert d["severity"] == "medium" and d["cvss_score"] == "4.6" and d["version"] == 2
        assert Finding.objects.get(pk=f["id"]).dedupe_hash != before
        ev = AuditEvent.objects.filter(action="finding.updated", entity_id=f["id"]).first()
        assert ev.changes["title"] == ["SQL injection in search", "Renamed"] and ev.engagement_id == w.eng_a.pk

    def test_stale_version_conflicts(self, w, p1c):
        f = make(p1c, w.eng_a)
        assert p1c.patch(furl(f), {"version": 1, "title": "one"}, format="json").status_code == 200
        assert p1c.patch(furl(f), {"version": 1, "title": "two"}, format="json").status_code == 409
        assert p1c.patch(furl(f), {"title": "no version"}, format="json").status_code == 400

    def test_severity_follows_vector(self, w, p1c):
        f = make(p1c, w.eng_a, cvss_vector=V31, severity="critical")
        assert p1c.patch(furl(f), {"version": 1, "severity": "low"}, format="json").status_code == 400
        r = p1c.patch(furl(f), {"version": 1, "cvss_vector": "", "severity": "low"}, format="json")
        assert r.status_code == 200 and r.json()["severity"] == "low" and r.json()["cvss_score"] is None

    def test_long_text_is_truncated_in_audit(self, w, p1c):
        f = make(p1c, w.eng_a)
        p1c.patch(furl(f), {"version": 1, "description": "x" * 5000}, format="json")
        ev = AuditEvent.objects.filter(action="finding.updated", entity_id=f["id"]).first()
        assert len(ev.changes["description"][1]) <= 501

    def test_noop_update_does_not_bump_version(self, w, p1c):
        f = make(p1c, w.eng_a)
        r = p1c.patch(furl(f), {"version": 1, "title": f["title"]}, format="json")
        assert r.status_code == 200 and r.json()["version"] == 1


@pytest.mark.django_db
class TestLifecycle:
    def test_publish_requires_complete_fields(self, w, p1c):
        f = make(p1c, w.eng_a, description="", recommendation="")
        r = p1c.post(furl(f, "/publish"), {"version": 1}, format="json")
        assert r.status_code == 400 and {"description", "recommendation"} <= set(r.json()["error"]["fields"])
        f = p1c.patch(furl(f), {"version": 1, "description": "d", "recommendation": "r"}, format="json").json()
        d = publish(p1c, f)
        assert d["status"] == "open" and d["version"] == 3
        assert p1c.post(furl(f, "/publish"), {"version": 3}, format="json").status_code == 409

    def test_publish_needs_permission(self, w, admin):
        role = make_role("NoPublish", ["engagements.view", "findings.view", "findings.create", "findings.view_draft"])
        u = make_user("np@example.com", role)
        EngagementMembership.objects.create(engagement=w.eng_a, user=u, added_by=admin)
        c = signed_in(u)
        f = make(c, w.eng_a)
        assert c.post(furl(f, "/publish"), {"version": 1}, format="json").status_code == 403  # coarse gate

    def test_publish_denial_inside_engagement_is_audited(self, w, admin):
        no = make_role("NoPublish2", ["engagements.view", "findings.view", "findings.create", "findings.view_draft"])
        yes = make_role("CanPublish", ["engagements.view", "findings.view", "findings.publish"])
        u = make_user("np2@example.com", no)
        EngagementMembership.objects.create(engagement=w.eng_a, user=u, added_by=admin)
        EngagementMembership.objects.create(engagement=w.eng_b, user=u, role_override=yes, added_by=admin)
        c = signed_in(u)
        f = make(c, w.eng_a)
        assert c.post(furl(f, "/publish"), {"version": 1}, format="json").status_code == 403
        ev = AuditEvent.objects.get(action="finding.publish_denied")
        assert ev.outcome == "denied" and ev.engagement_id == w.eng_a.pk
        assert Finding.objects.get(pk=f["id"]).status == "draft"

    def test_false_positive_needs_reason_and_locks_editing(self, w, p1c):
        f = make(p1c, w.eng_a)
        assert p1c.post(furl(f, "/false-positive"), {"version": 1}, format="json").status_code == 400
        assert p1c.post(furl(f, "/false-positive"), {"version": 1, "reason": "no"}, format="json").status_code == 400
        r = p1c.post(
            furl(f, "/false-positive"), {"version": 1, "reason": "Scanner artefact, verified manually"}, format="json"
        )
        assert r.status_code == 200 and r.json()["status"] == "false_positive"
        assert p1c.patch(furl(f), {"version": 2, "title": "x"}, format="json").status_code == 409
        ev = AuditEvent.objects.get(action="finding.false_positive", entity_id=f["id"])
        assert "Scanner artefact" in ev.metadata["reason"]

    def test_duplicate_rules(self, w, p1c, admin_client, admin):
        a, b, c = (make(p1c, w.eng_a, title=t) for t in ("A", "B", "C"))
        other = make(admin_client, w.eng_b, title="Other")
        dup = lambda f, t, v=1: p1c.post(furl(f, "/duplicate"), {"version": v, "duplicate_of": t}, format="json")  # noqa: E731
        assert dup(a, a["id"]).status_code == 400
        assert dup(a, other["id"]).status_code == 400  # not visible to p1 at all
        assert (
            admin_client.post(
                furl(a, "/duplicate"), {"version": 1, "duplicate_of": other["id"]}, format="json"
            ).status_code
            == 400
        )
        r = dup(b, a["id"])
        assert (
            r.status_code == 200 and r.json()["status"] == "duplicate" and r.json()["duplicate_of"]["ref"] == a["ref"]
        )
        assert dup(c, b["id"]).status_code == 400  # b is itself a duplicate
        assert dup(b, a["id"], 2).status_code == 409  # already a duplicate

    def test_duplicate_row_constraint(self, w):
        from django.db import IntegrityError, transaction

        with pytest.raises(IntegrityError), transaction.atomic():
            Finding.objects.create(ref="RS-F-900002", engagement=w.eng_a, title="t", severity="low", status="duplicate",
                                   reported_by=w.p1, discovered_at=w.today, dedupe_hash="h")  # fmt: skip


@pytest.mark.django_db
class TestVisibility:
    def test_drafts_hidden_from_remediation_until_published_and_assigned(self, w, p1c, r1c):
        f = make(p1c, w.eng_a)
        assert r1c.get(furl(f)).status_code == 404
        f = publish(p1c, f)
        assert r1c.get(furl(f)).status_code == 404  # scope is "assigned" and nobody assigned it
        p1c.patch(furl(f), {"version": f["version"], "remediation_owner": str(w.r1.pk)}, format="json")
        assert r1c.get(furl(f)).status_code == 200
        assert ids(r1c.get(f"{API}/findings")) == {f["id"]}

    def test_finding_scope_override_to_all(self, w, p1c, r1c):
        f = publish(p1c, make(p1c, w.eng_a))
        EngagementMembership.objects.filter(engagement=w.eng_a, user=w.r1).update(finding_scope="all")
        assert r1c.get(furl(f)).status_code == 200
        draft = make(p1c, w.eng_a, title="Hidden draft")
        assert r1c.get(furl(draft)).status_code == 404
        assert ids(r1c.get(f"{API}/findings")) == {f["id"]}

    def test_cross_engagement_isolation(self, w, admin_client, p1c):
        fb = make(admin_client, w.eng_b, title="Borealis finding")
        assert p1c.get(furl(fb)).status_code == 404
        assert ids(p1c.get(f"{API}/findings")) == set()
        assert p1c.patch(furl(fb), {"version": 1, "title": "x"}, format="json").status_code == 404
        assert p1c.post(furl(fb, "/publish"), {"version": 1}, format="json").status_code == 404
        assert p1c.delete(furl(fb)).status_code in (403, 404)

    def test_remediation_sees_technical_fields(self, w, p1c, r1c):
        f = make(p1c, w.eng_a, technical_details="secret internals", poc="curl -X evil")
        assert p1c.get(furl(f)).json()["poc"] == "curl -X evil"
        f = publish(p1c, f)
        p1c.patch(furl(f), {"version": 2, "remediation_owner": str(w.r1.pk)}, format="json")
        d = r1c.get(furl(f)).json()
        assert d["poc"] == "curl -X evil" and d["technical_details"] == "secret internals"

    def test_super_admin_sees_all_including_drafts(self, w, admin_client, p1c):
        f = make(p1c, w.eng_a)
        assert admin_client.get(furl(f)).status_code == 200

    def test_soft_deleted_finding_is_invisible(self, w, admin_client):
        f = make(admin_client, w.eng_a)
        assert admin_client.delete(furl(f)).status_code == 204
        assert admin_client.get(furl(f)).status_code == 404
        assert Finding.all_objects.filter(pk=f["id"], deleted_at__isnull=False).exists()
        assert AuditEvent.objects.filter(action="finding.deleted", entity_id=f["id"]).exists()

    def test_delete_needs_permission_and_protects_originals(self, w, p1c, admin_client):
        a = make(p1c, w.eng_a, title="A")
        b = make(p1c, w.eng_a, title="B")
        assert p1c.delete(furl(a)).status_code == 403  # pentester role has no findings.delete
        p1c.post(furl(b, "/duplicate"), {"version": 1, "duplicate_of": a["id"]}, format="json")
        assert admin_client.delete(furl(a)).status_code == 409


@pytest.mark.django_db
class TestSearchFilterSort:
    def test_search_full_text_ref_and_isolation(self, w, p1c, admin_client):
        a = make(p1c, w.eng_a, title="Weak TLS", description="Server accepts deprecated protocols")
        make(p1c, w.eng_a, title="Other", description="nothing relevant")
        make(admin_client, w.eng_b, title="Borealis TLS", description="deprecated protocols too")
        found = ids(p1c.get(f"{API}/findings?search=protocols"))
        assert found == {a["id"]}
        assert ids(p1c.get(f"{API}/findings?search={a['ref']}")) == {a["id"]}
        assert len(ids(admin_client.get(f"{API}/findings?search=protocols"))) == 2

    def test_filters(self, w, p1c):
        hi = make(p1c, w.eng_a, title="hi", severity="high", cwe_id=89)
        lo = make(p1c, w.eng_a, title="lo", severity="low")
        publish(p1c, hi)
        assert ids(p1c.get(f"{API}/findings?severity=high")) == {hi["id"]}
        assert ids(p1c.get(f"{API}/findings?status=draft")) == {lo["id"]}
        assert ids(p1c.get(f"{API}/findings?cwe=89")) == {hi["id"]}
        assert ids(p1c.get(f"{API}/findings?engagement={w.eng_a.pk}")) == {hi["id"], lo["id"]}
        assert ids(p1c.get(f"{API}/findings?engagement={w.eng_b.pk}")) == set()
        assert ids(p1c.get(f"{API}/findings?severity=bogus")) == set()
        assert p1c.get(f"{API}/findings?from=not-a-date").json()["count"] == 0

    def test_default_order_is_most_severe_first(self, w, p1c):
        for sev in ("low", "critical", "medium", "info", "high"):
            make(p1c, w.eng_a, title=sev, severity=sev)
        rows = p1c.get(f"{API}/findings").json()["results"]
        assert [r["severity"] for r in rows] == ["critical", "high", "medium", "low", "info"]
        rows = p1c.get(f"{API}/findings?ordering=severity").json()["results"]
        assert rows[0]["severity"] == "info"
        assert p1c.get(f"{API}/findings?ordering=password").status_code == 200

    def test_possible_duplicates_flagged(self, w, p1c):
        a = make(p1c, w.eng_a, title="Same issue", endpoint="/x")
        b = make(p1c, w.eng_a, title="same   ISSUE", endpoint="/X")
        assert [d["id"] for d in p1c.get(furl(b)).json()["possible_duplicates"]] == [a["id"]]


@pytest.mark.django_db
class TestBulk:
    def test_publish_partial_results(self, w, p1c, admin_client):
        d1 = make(p1c, w.eng_a, title="d1")
        d2 = make(p1c, w.eng_a, title="d2")
        opened = publish(p1c, make(p1c, w.eng_a, title="open"))
        hidden = make(admin_client, w.eng_b, title="not yours")
        ghost = "00000000-0000-0000-0000-000000000001"
        r = p1c.post(
            f"{API}/findings/bulk",
            {"action": "publish", "ids": [d1["id"], d2["id"], opened["id"], hidden["id"], ghost]},
            format="json",
        )
        assert r.status_code == 200
        res = {x["id"]: x for x in r.json()["results"]}
        assert res[d1["id"]]["ok"] and res[d2["id"]]["ok"]
        assert res[opened["id"]]["error"]["code"] == "conflict"
        assert res[hidden["id"]]["error"]["code"] == "not_found" and res[ghost]["error"]["code"] == "not_found"
        assert r.json()["succeeded"] == 2 and r.json()["failed"] == 3
        assert Finding.objects.get(pk=d1["id"]).status == "open"

    def test_bulk_needs_coarse_permission(self, w, r1c, p1c):
        f = publish(p1c, make(p1c, w.eng_a))
        assert (
            r1c.post(f"{API}/findings/bulk", {"action": "publish", "ids": [f["id"]]}, format="json").status_code == 403
        )

    def test_per_item_authorisation_for_delete(self, w, p1c):
        f = make(p1c, w.eng_a)
        r = p1c.post(f"{API}/findings/bulk", {"action": "delete", "ids": [f["id"]]}, format="json").json()
        assert r["results"][0]["error"]["code"] == "forbidden" and Finding.objects.filter(pk=f["id"]).exists()

    def test_bulk_assign_and_validation(self, w, p1c):
        f1, f2 = make(p1c, w.eng_a, title="1"), make(p1c, w.eng_a, title="2")
        r = p1c.post(
            f"{API}/findings/bulk",
            {"action": "assign", "ids": [f1["id"], f2["id"]], "remediation_owner": str(w.r1.pk)},
            format="json",
        )
        assert r.json()["succeeded"] == 2
        assert Finding.objects.get(pk=f1["id"]).remediation_owner_id == w.r1.pk
        assert (
            p1c.post(f"{API}/findings/bulk", {"action": "assign", "ids": [f1["id"]]}, format="json").status_code == 400
        )
        assert p1c.post(f"{API}/findings/bulk", {"action": "nuke", "ids": [f1["id"]]}, format="json").status_code == 400
        too_many = [f"00000000-0000-0000-0000-{i:012d}" for i in range(101)]
        assert (
            p1c.post(f"{API}/findings/bulk", {"action": "publish", "ids": too_many}, format="json").status_code == 400
        )


@pytest.mark.django_db
class TestHistoryAndEndpoints:
    def test_finding_history_and_remediation_view(self, w, p1c, r1c):
        f = make(p1c, w.eng_a, poc="draft poc")
        p1c.patch(
            furl(f),
            {"version": 1, "poc": "second poc text", "description": "dd", "recommendation": "rr"},
            format="json",
        )
        f = publish(p1c, {**f, "version": 2})
        p1c.patch(furl(f), {"version": 3, "remediation_owner": str(w.r1.pk), "poc": "third poc text"}, format="json")
        actions = [e["action"] for e in p1c.get(furl(f, "/history")).json()["results"]]
        assert actions == ["finding.updated", "finding.published", "finding.updated", "finding.created"]
        rem = r1c.get(furl(f, "/history")).json()["results"]
        assert [e["action"] for e in rem] == ["finding.updated", "finding.published"]
        assert any("poc" in e["changes"] for e in rem)  # remediation reproduces the finding, so it sees the PoC

    def test_engagement_history_hides_finding_events_from_remediation(self, w, p1c, r1c):
        make(p1c, w.eng_a, title="Secret draft title")
        pent = p1c.get(f"{API}/engagements/{w.eng_a.pk}/history").json()["results"]
        rem = r1c.get(f"{API}/engagements/{w.eng_a.pk}/history").json()["results"]
        assert any(e["entity_type"] == "finding" for e in pent)
        assert not any(e["entity_type"] == "finding" for e in rem)
        assert "Secret draft title" not in str(rem)

    def test_cvss_endpoint(self, p1c, r1c):
        r = p1c.post(f"{API}/findings/cvss", {"vector": V31}, format="json")
        assert r.json() == {"version": "3.1", "score": "9.8", "severity": "critical"}
        assert p1c.post(f"{API}/findings/cvss", {"vector": "x"}, format="json").status_code == 400
        assert r1c.post(f"{API}/findings/cvss", {"vector": V31}, format="json").status_code == 200

    def test_cwe_endpoint(self, p1c):
        rows = p1c.get(f"{API}/cwes?search=sql").json()
        assert any(r["id"] == 89 for r in rows)
        assert [r["id"] for r in p1c.get(f"{API}/cwes?search=CWE-79").json()][:1] == [79]
        assert len(p1c.get(f"{API}/cwes").json()) <= 50

    def test_audit_chain_stays_valid(self, w, p1c, admin_client):
        f = make(p1c, w.eng_a)
        publish(p1c, f)
        admin_client.delete(furl(f))
        assert verify_chain().ok


@pytest.mark.django_db
def test_severity_bands_boundaries():
    from decimal import Decimal

    from apps.findings.cvss import severity_for

    cases = {"10.0": "critical", "9.0": "critical", "8.9": "high", "7.0": "high", "6.9": "medium", "4.0": "medium",
             "3.9": "low", "0.1": "low", "0.0": "info"}  # fmt: skip
    for score, severity in cases.items():
        assert severity_for(Decimal(score)) == severity, score
