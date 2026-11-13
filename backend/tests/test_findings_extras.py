import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection, transaction
from PIL import Image

from apps.audit.models import AuditEvent
from apps.audit.service import verify_chain
from apps.core.markdown import render_markdown
from apps.engagements import services as eng_services
from apps.engagements.models import EngagementMembership
from apps.files import services as file_services
from apps.files.models import Attachment
from apps.findings.models import Finding, FindingNote, FindingTemplate
from tests.conftest import make_role, make_user, signed_in
from tests.test_findings import V31, furl, ids, make, publish
from tests.world import build_world

API = "/api/v1"


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)


@pytest.fixture
def w(admin):
    return build_world(admin)


@pytest.fixture
def p1c(w):
    return signed_in(w.p1)


@pytest.fixture
def r1c(w):
    return signed_in(w.r1)


def png():
    out = io.BytesIO()
    Image.new("RGB", (6, 6), "blue").save(out, "PNG")
    return out.getvalue()


def up(client, f, name="shot.png", content=None, ctype="image/png"):
    file = SimpleUploadedFile(name, content if content is not None else png(), content_type=ctype)
    return client.post(furl(f, "/evidence"), {"file": file}, format="multipart")


@pytest.fixture
def open_finding(w, p1c):
    """Published finding assigned to remediation user r1."""
    f = publish(p1c, make(p1c, w.eng_a))
    r = p1c.patch(furl(f), {"version": f["version"], "remediation_owner": str(w.r1.pk)}, format="json")
    assert r.status_code == 200
    return r.json()


@pytest.mark.django_db
class TestEvidence:
    def test_upload_list_download_and_audit(self, w, p1c):
        f = make(p1c, w.eng_a)
        r = up(p1c, f)
        assert r.status_code == 201
        d = r.json()
        assert d["kind"] == "evidence" and d["is_image"] is True and d["finding"] == f["id"]
        listed = p1c.get(furl(f, "/evidence")).json()["results"]
        assert [x["id"] for x in listed] == [d["id"]]
        dl = p1c.get(d["download_url"])
        assert dl.status_code == 200 and dl["X-Accel-Redirect"].startswith("/protected/")
        assert dl["Content-Disposition"].startswith("attachment") and dl["X-Content-Type-Options"] == "nosniff"
        assert AuditEvent.objects.filter(action="attachment.downloaded", engagement_id=w.eng_a.pk).exists()
        up_ev = AuditEvent.objects.get(action="attachment.uploaded", entity_id=d["id"])
        assert up_ev.metadata["finding_id"] == f["id"] and up_ev.engagement_id == w.eng_a.pk

    def test_validation_reuses_upload_rules(self, w, p1c):
        f = make(p1c, w.eng_a)
        assert up(p1c, f, "x.txt", b"<!doctype html><script>1</script>", "text/plain").status_code == 400
        assert up(p1c, f, "x.png", b"not an image", "image/png").status_code == 400
        assert up(p1c, f, "log.txt", b"nmap output\n", "text/plain").status_code == 201
        assert up(p1c, f, "x.png", b"", "image/png").status_code == 400

    def test_evidence_stays_out_of_documents_and_attachment_list(self, w, p1c):
        f = make(p1c, w.eng_a)
        d = up(p1c, f).json()
        docs = p1c.get(f"{API}/engagements/{w.eng_a.pk}/documents").json()["results"]
        assert d["id"] not in {x["id"] for x in docs}
        assert d["id"] not in ids(p1c.get(f"{API}/attachments"))
        assert p1c.get(f"{API}/attachments/{d['id']}").status_code == 200

    def test_visibility_follows_the_finding(self, w, p1c, r1c):
        draft = make(p1c, w.eng_a)
        ev = up(p1c, draft).json()
        assert r1c.get(furl(draft, "/evidence")).status_code == 404
        assert r1c.get(f"{API}/attachments/{ev['id']}").status_code == 404
        assert r1c.get(f"{API}/attachments/{ev['id']}/download").status_code == 404
        assert up(r1c, draft).status_code == 404
        outsider = signed_in(w.p2)
        assert outsider.get(furl(draft, "/evidence")).status_code == 404
        assert outsider.get(f"{API}/attachments/{ev['id']}/download").status_code == 404
        assert signed_in(w.p3).get(furl(draft, "/evidence")).status_code == 404

    def test_remediation_can_attach_and_read_on_assigned_finding(self, w, p1c, r1c, open_finding):
        ev = up(r1c, open_finding, "fix.png")
        assert ev.status_code == 201
        assert [x["original_name"] for x in p1c.get(furl(open_finding, "/evidence")).json()["results"]] == ["fix.png"]
        assert r1c.get(furl(open_finding, "/evidence")).status_code == 200

    def test_unassigned_remediation_user_sees_nothing(self, w, p1c, open_finding):
        r2 = make_user("r2@example.com", "remediation")
        EngagementMembership.objects.create(engagement=w.eng_a, user=r2, added_by=w.p1)
        c = signed_in(r2)
        assert c.get(furl(open_finding, "/evidence")).status_code == 404

    def test_delete_rules(self, w, p1c, r1c, open_finding, admin_client):
        mine = up(r1c, open_finding, "mine.png").json()
        theirs = up(p1c, open_finding, "theirs.png").json()
        assert r1c.delete(furl(open_finding, f"/evidence/{theirs['id']}")).status_code == 403
        assert AuditEvent.objects.filter(
            action="evidence.delete_denied", outcome="denied", engagement_id=w.eng_a.pk
        ).exists()
        assert p1c.delete(furl(open_finding, f"/evidence/{mine['id']}")).status_code == 403  # pentester: own only
        assert r1c.delete(furl(open_finding, f"/evidence/{mine['id']}")).status_code == 204
        assert admin_client.delete(furl(open_finding, f"/evidence/{theirs['id']}")).status_code == 204
        assert p1c.get(furl(open_finding, "/evidence")).json()["count"] == 0
        assert p1c.delete(furl(open_finding, "/evidence/not-a-uuid")).status_code == 404
        assert Attachment.objects.get(pk=mine["id"]).deleted_at is not None

    def test_cannot_delete_other_findings_evidence_through_this_finding(self, w, p1c):
        a, b = make(p1c, w.eng_a, title="a"), make(p1c, w.eng_a, title="b")
        ev = up(p1c, b).json()
        assert p1c.delete(furl(a, f"/evidence/{ev['id']}")).status_code == 404

    def test_attachments_endpoint_cannot_delete_evidence(self, w, admin_client, p1c):
        ev = up(p1c, make(p1c, w.eng_a)).json()
        assert admin_client.delete(f"{API}/attachments/{ev['id']}").status_code == 403

    def test_limit_per_finding(self, w, p1c, monkeypatch):
        monkeypatch.setattr(file_services, "MAX_EVIDENCE_PER_FINDING", 2)
        f = make(p1c, w.eng_a)
        assert up(p1c, f, "1.png").status_code == 201 and up(p1c, f, "2.png").status_code == 201
        assert up(p1c, f, "3.png").status_code == 409

    def test_archived_engagement_is_read_only(self, w, p1c, admin):
        f = make(p1c, w.eng_a)
        eng_services.change_status(None, admin, w.eng_a, "scheduled", 1)
        w.eng_a.refresh_from_db()
        eng_services.change_status(None, admin, w.eng_a, "cancelled", w.eng_a.version)
        w.eng_a.refresh_from_db()
        eng_services.archive_engagement(None, admin, w.eng_a, w.eng_a.version)
        assert up(p1c, f).status_code == 409

    def test_db_constraint_requires_finding_for_evidence(self, w, admin):
        with pytest.raises(IntegrityError), transaction.atomic():
            Attachment.objects.create(kind="evidence", engagement=w.eng_a, original_name="x", storage_key="k" * 40,
                                      mime="image/png", size=1, sha256="0" * 64, uploaded_by=admin)  # fmt: skip

    def test_history_shows_evidence_to_testing_team_not_in_engagement_timeline_for_remediation(
        self, w, p1c, r1c, open_finding
    ):
        up(p1c, open_finding, "secret-name.png")
        hist = [e["action"] for e in p1c.get(furl(open_finding, "/history")).json()["results"]]
        assert "attachment.uploaded" in hist
        rem_hist = r1c.get(furl(open_finding, "/history")).json()["results"]
        assert "attachment.uploaded" in [e["action"] for e in rem_hist]  # post-publish evidence is shared
        eng_timeline = r1c.get(f"{API}/engagements/{w.eng_a.pk}/history").json()["results"]
        assert not any(
            e["entity_type"] == "attachment" and e["metadata"].get("kind") == "evidence" for e in eng_timeline
        )

    def test_finding_soft_delete_hides_evidence(self, w, p1c, admin_client):
        f = make(p1c, w.eng_a)
        ev = up(p1c, f).json()
        admin_client.delete(furl(f))
        assert p1c.get(f"{API}/attachments/{ev['id']}").status_code == 404


@pytest.mark.django_db
class TestNotes:
    def test_technical_and_remediation_notes(self, w, p1c, r1c, open_finding):
        t = p1c.post(furl(open_finding, "/notes"), {"kind": "technical", "body": "internal pivot path"}, format="json")
        assert t.status_code == 201 and t.json()["visibility"] == "team" and t.json()["author"]["email"] == w.p1.email
        r = r1c.post(furl(open_finding, "/notes"), {"kind": "remediation", "body": "patch scheduled"}, format="json")
        assert r.status_code == 201 and r.json()["visibility"] == "all"
        pent = {n["kind"] for n in p1c.get(furl(open_finding, "/notes")).json()["results"]}
        rem = r1c.get(furl(open_finding, "/notes")).json()["results"]
        assert pent == {"technical", "remediation"}
        assert [n["kind"] for n in rem] == ["remediation"] and "pivot" not in str(rem)

    def test_remediation_cannot_write_technical_notes(self, w, r1c, open_finding):
        r = r1c.post(furl(open_finding, "/notes"), {"kind": "technical", "body": "x"}, format="json")
        assert r.status_code == 403
        assert AuditEvent.objects.filter(
            action="finding.note_denied", outcome="denied", engagement_id=w.eng_a.pk
        ).exists()
        assert FindingNote.objects.count() == 0

    def test_draft_rules(self, w, p1c):
        draft = make(p1c, w.eng_a)
        assert p1c.post(furl(draft, "/notes"), {"kind": "technical", "body": "wip"}, format="json").status_code == 201
        assert p1c.post(furl(draft, "/notes"), {"kind": "remediation", "body": "wip"}, format="json").status_code == 409

    def test_validation(self, w, p1c):
        f = make(p1c, w.eng_a)
        for payload in ({"kind": "technical", "body": "  "}, {"kind": "bogus", "body": "x"}, {"body": "x"},
                        {"kind": "technical", "body": "x", "visibility": "all"}, {"kind": "technical", "body": "x" * 20001}):  # fmt: skip
            assert p1c.post(furl(f, "/notes"), payload, format="json").status_code == 400

    def test_append_only_api_and_database(self, w, p1c):
        f = make(p1c, w.eng_a)
        n = p1c.post(furl(f, "/notes"), {"kind": "technical", "body": "orig"}, format="json").json()
        assert p1c.patch(furl(f, f"/notes/{n['id']}"), {"body": "edited"}, format="json").status_code in (404, 405)
        assert p1c.delete(furl(f, f"/notes/{n['id']}")).status_code in (404, 405)
        with pytest.raises(Exception, match="append-only"), transaction.atomic(), connection.cursor() as cur:
            cur.execute("UPDATE findings_findingnote SET body = 'x' WHERE id = %s", [n["id"]])
        with pytest.raises(Exception, match="append-only"), transaction.atomic(), connection.cursor() as cur:
            cur.execute("DELETE FROM findings_findingnote WHERE id = %s", [n["id"]])
        assert FindingNote.objects.get(pk=n["id"]).body == "orig"

    def test_isolation(self, w, p1c, admin_client):
        fb = make(admin_client, w.eng_b, title="b")
        assert p1c.get(furl(fb, "/notes")).status_code == 404
        assert p1c.post(furl(fb, "/notes"), {"kind": "technical", "body": "x"}, format="json").status_code == 404

    def test_history_hides_technical_note_events_from_remediation(self, w, p1c, r1c, open_finding):
        p1c.post(furl(open_finding, "/notes"), {"kind": "technical", "body": "secret"}, format="json")
        r1c.post(furl(open_finding, "/notes"), {"kind": "remediation", "body": "fix"}, format="json")
        pent = [e["action"] for e in p1c.get(furl(open_finding, "/history")).json()["results"]]
        rem = [e["action"] for e in r1c.get(furl(open_finding, "/history")).json()["results"]]
        assert "finding.technical_note_added" in pent and "finding.remediation_note_added" in pent
        assert "finding.technical_note_added" not in rem and "finding.remediation_note_added" in rem
        ev = AuditEvent.objects.get(action="finding.technical_note_added")
        assert "secret" not in str(ev.metadata)

    def test_archived_engagement(self, w, p1c, admin):
        f = make(p1c, w.eng_a)
        eng_services.change_status(None, admin, w.eng_a, "scheduled", 1)
        w.eng_a.refresh_from_db()
        eng_services.change_status(None, admin, w.eng_a, "cancelled", w.eng_a.version)
        w.eng_a.refresh_from_db()
        eng_services.archive_engagement(None, admin, w.eng_a, w.eng_a.version)
        assert p1c.post(furl(f, "/notes"), {"kind": "technical", "body": "x"}, format="json").status_code == 409


TEMPLATE = {"name": "Reflected XSS", "title": "Reflected cross-site scripting", "description": "Input is reflected.",
            "recommendation": "Encode output.", "severity": "medium", "cwe_id": 79,
            "references": [{"label": "OWASP", "url": "https://owasp.org/xss"}]}  # fmt: skip


@pytest.mark.django_db
class TestTemplates:
    def test_permissions(self, w, admin_client, p1c, r1c):
        assert admin_client.post(f"{API}/finding-templates", TEMPLATE, format="json").status_code == 201
        assert p1c.get(f"{API}/finding-templates").status_code == 200
        assert p1c.post(f"{API}/finding-templates", {**TEMPLATE, "name": "x"}, format="json").status_code == 403
        assert r1c.get(f"{API}/finding-templates").status_code == 403
        t = FindingTemplate.objects.get()
        assert (
            p1c.patch(f"{API}/finding-templates/{t.pk}", {"version": 1, "title": "x"}, format="json").status_code == 403
        )
        assert p1c.delete(f"{API}/finding-templates/{t.pk}").status_code == 403

    def test_crud_validation_and_locking(self, admin_client):
        r = admin_client.post(f"{API}/finding-templates", TEMPLATE, format="json")
        t = r.json()
        assert t["cwe"]["id"] == 79 and t["version"] == 1
        assert (
            admin_client.post(f"{API}/finding-templates", TEMPLATE, format="json").status_code == 400
        )  # duplicate name
        bad = [{"cwe_id": 999999}, {"cvss_vector": "nope"}, {"severity": "low", "cvss_vector": V31}, {"ref": "x"}]
        for extra in bad:
            body_ = {**TEMPLATE, "name": "n2", **extra}
            assert admin_client.post(f"{API}/finding-templates", body_, format="json").status_code == 400
        no_sev = {k: v for k, v in TEMPLATE.items() if k != "severity"}
        assert admin_client.post(f"{API}/finding-templates", {**no_sev, "name": "n3"}, format="json").status_code == 400
        u = admin_client.patch(f"{API}/finding-templates/{t['id']}", {"version": 1, "title": "New"}, format="json")
        assert u.status_code == 200 and u.json()["version"] == 2
        assert (
            admin_client.patch(
                f"{API}/finding-templates/{t['id']}", {"version": 1, "title": "Old"}, format="json"
            ).status_code
            == 409
        )
        assert admin_client.get(f"{API}/finding-templates?search=new").json()["count"] == 1
        assert admin_client.delete(f"{API}/finding-templates/{t['id']}").status_code == 204
        assert AuditEvent.objects.filter(action="template.deleted").exists()

    def test_vector_template_derives_severity(self, admin_client):
        t = admin_client.post(
            f"{API}/finding-templates", {**TEMPLATE, "severity": "", "cvss_vector": V31}, format="json"
        ).json()
        assert t["severity"] == "critical"

    def test_create_finding_from_template(self, w, admin_client, p1c):
        t = admin_client.post(f"{API}/finding-templates", TEMPLATE, format="json").json()
        r = p1c.post(f"{API}/findings", {"engagement": str(w.eng_a.pk), "template": t["id"]}, format="json")
        assert r.status_code == 201, r.content
        d = r.json()
        assert (d["title"], d["severity"], d["cwe"]["id"], d["description"]) == (
            "Reflected cross-site scripting",
            "medium",
            79,
            "Input is reflected.",
        )
        assert d["references"][0]["label"] == "OWASP" and Finding.objects.get(pk=d["id"]).source == "template"
        over = p1c.post(f"{API}/findings", {"engagement": str(w.eng_a.pk), "template": t["id"], "title": "Mine",
                                            "severity": "low", "description": "custom"}, format="json").json()  # fmt: skip
        assert (over["title"], over["severity"], over["description"], over["recommendation"]) == (
            "Mine",
            "low",
            "custom",
            "Encode output.",
        )

    def test_template_vector_and_caller_vector(self, w, admin_client, p1c):
        t = admin_client.post(
            f"{API}/finding-templates", {**TEMPLATE, "severity": "", "cvss_vector": V31}, format="json"
        ).json()
        d = p1c.post(f"{API}/findings", {"engagement": str(w.eng_a.pk), "template": t["id"]}, format="json").json()
        assert (d["severity"], d["cvss_score"]) == ("critical", "9.8")
        d2 = p1c.post(
            f"{API}/findings", {"engagement": str(w.eng_a.pk), "template": t["id"], "severity": "low"}, format="json"
        ).json()
        assert d2["severity"] == "low" and d2["cvss_vector"] == ""

    def test_template_needs_view_permission_and_valid_id(self, w, admin_client, admin):
        t = admin_client.post(f"{API}/finding-templates", TEMPLATE, format="json").json()
        role = make_role("NoTemplates", ["engagements.view", "findings.view", "findings.create", "findings.view_draft"])
        u = make_user("nt@example.com", role)
        EngagementMembership.objects.create(engagement=w.eng_a, user=u, added_by=admin)
        c = signed_in(u)
        r = c.post(f"{API}/findings", {"engagement": str(w.eng_a.pk), "template": t["id"]}, format="json")
        assert r.status_code == 403
        r = admin_client.post(
            f"{API}/findings",
            {"engagement": str(w.eng_a.pk), "template": "00000000-0000-0000-0000-000000000009"},
            format="json",
        )
        assert r.status_code == 400
        assert (
            admin_client.post(
                f"{API}/findings", {"engagement": str(w.eng_a.pk), "severity": "low"}, format="json"
            ).status_code
            == 400
        )

    def test_deleting_template_keeps_findings(self, w, admin_client, p1c):
        t = admin_client.post(f"{API}/finding-templates", TEMPLATE, format="json").json()
        d = p1c.post(f"{API}/findings", {"engagement": str(w.eng_a.pk), "template": t["id"]}, format="json").json()
        admin_client.delete(f"{API}/finding-templates/{t['id']}")
        assert p1c.get(furl(d)).json()["title"] == "Reflected cross-site scripting"
        assert verify_chain().ok


class TestMarkdown:
    @pytest.mark.parametrize("attack", [
        "<script>alert(1)</script>", "<img src=x onerror=alert(1)>", "[x](javascript:alert(1))",
        "<a href=\"javascript:alert(1)\">x</a>", "<iframe src=//evil></iframe>", "<svg onload=alert(1)>",
        "<style>body{display:none}</style>", "![x](http://evil/p.png)", "<div onclick=\"x()\">hi</div>",
        "<a href=\"data:text/html,<script>1</script>\">x</a>", "<!-- c --><b onmouseover=1>x</b>",
    ])  # fmt: skip
    def test_dangerous_content_removed(self, attack):
        out = render_markdown(attack).lower()
        for bad in ("<script", "onerror", "onclick", "onload", "onmouseover", "javascript:", "<iframe", "<svg",
                    "<style", "<img", "data:text", "<!--"):  # fmt: skip
            assert bad not in out, (attack, out)

    def test_safe_markdown_kept(self):
        out = render_markdown(
            "# Title\n\n**bold** and `code`\n\n- a\n- b\n\n[link](https://example.com)\n\n```\nx < y\n```"
        )
        for good in ("<h1>", "<strong>bold</strong>", "<code>code</code>", "<li>a</li>", 'href="https://example.com"',
                     "x &lt; y"):  # fmt: skip
            assert good in out
        assert 'rel="noopener noreferrer nofollow"' in out

    def test_empty(self):
        assert render_markdown("") == "" and render_markdown(None) == ""
