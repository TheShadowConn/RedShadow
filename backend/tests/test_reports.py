"""Phase 9: report templates, report jobs, the PDF and CSV builders and their limits."""

import csv
import io
import time
from datetime import timedelta
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image
from pypdf import PdfReader

from apps.audit.models import AuditEvent
from apps.audit.service import verify_chain
from apps.engagements.models import EngagementMembership
from apps.findings.models import Finding
from apps.reports import builder, render, services
from apps.reports.models import ReportJob, ReportTemplate
from tests.conftest import make_role, make_user, signed_in
from tests.test_findings import API, furl, make, publish
from tests.world import build_world

REPORTS = f"{API}/reports"
TEMPLATES = f"{API}/report-templates"


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


@pytest.fixture
def w(admin):
    return build_world(admin)


@pytest.fixture
def p1c(w):
    return signed_in(w.p1)


@pytest.fixture
def r1c(w):
    return signed_in(w.r1)


def png_bytes(size=(64, 48), colour="red"):
    out = io.BytesIO()
    Image.new("RGB", size, colour).save(out, "PNG")
    return out.getvalue()


def seed(w, p1c, count=4):
    """A few published findings with text in every field the report prints. Returns the finding dicts."""
    out = []
    specs = [
        ("SQL injection in search", "critical", "TECH-SECRET sqlmap output", "POC-SECRET curl -d q=1"),
        ("Stored XSS in comments", "high", "TECH-SECRET payload", "POC-SECRET <script>"),
        ("Verbose server banner", "low", "", ""),
        ("Missing security headers", "medium", "", ""),
    ]
    for title, severity, tech, poc in specs[:count]:
        f = make(
            p1c, w.eng_a, title=title, severity=severity, technical_details=tech, poc=poc,
            description=f"## Summary\n\nThe **{title}** issue lets an attacker read data.\n\n```\nGET /search?q=1\n```",
            references=[{"label": "OWASP Top 10", "url": "https://owasp.org/www-project-top-ten/"}], asset=str(w.asset_a.pk), endpoint="/search",
        )  # fmt: skip
        out.append(publish(p1c, f))
    return out


def request_report(client, eng, capture, **kw):
    body = {"engagement": str(eng.pk), "format": "pdf", "audience": "client", **kw}
    with capture(execute=True):
        r = client.post(REPORTS, body, format="json")
    return r


def done(client, r):
    assert r.status_code == 201, r.content
    job = client.get(f"{REPORTS}/{r.json()['id']}").json()
    assert job["status"] == "done", job
    return job


def download(client, job):
    r = client.get(f"{REPORTS}/{job['id']}/download")
    assert r.status_code == 200, r.content
    return b"".join(r.streaming_content)


def pdf_text(data: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(data)).pages)


# ------------------------------------------------------------------ the PDF itself


@pytest.mark.django_db
class TestPdf:
    def test_client_report_has_every_section_and_no_internal_text(self, w, p1c, django_capture_on_commit_callbacks):
        seed(w, p1c)
        draft = make(p1c, w.eng_a, title="Unpublished draft finding")
        job = done(p1c, request_report(p1c, w.eng_a, django_capture_on_commit_callbacks))
        data = download(p1c, job)
        assert data.startswith(b"%PDF") and job["page_count"] >= 8 and job["size"] == len(data)
        text = pdf_text(data)
        for needle in ("Executive summary", "Document control", "Engagement overview", "Scope", "Findings at a glance",
                       "Severity and status distribution", "Detailed findings", "Remediation roadmap", "Appendix",
                       "Methodology and rating scale", w.eng_a.ref, "Acme Corp", "SQL injection in search",
                       "Stored XSS in comments", "Missing security headers", "/search"):  # fmt: skip
            assert needle in text, needle
        assert draft["title"] not in text
        assert "TECH-SECRET" not in text and "POC-SECRET" not in text
        assert job["audience"] == "client" and job["finding_count"] == 4

    def test_internal_report_adds_technical_detail(self, w, p1c, django_capture_on_commit_callbacks):
        seed(w, p1c)
        job = done(p1c, request_report(p1c, w.eng_a, django_capture_on_commit_callbacks, audience="internal"))
        text = pdf_text(download(p1c, job))
        assert "TECH-SECRET sqlmap output" in text and "POC-SECRET curl" in text and "Internal" in text

    def test_evidence_image_is_embedded(self, w, p1c, django_capture_on_commit_callbacks):
        f = seed(w, p1c, count=1)[0]
        file = SimpleUploadedFile("proof.png", png_bytes((900, 500)), content_type="image/png")
        assert p1c.post(furl(f, "/evidence"), {"file": file}, format="multipart").status_code == 201
        job = done(p1c, request_report(p1c, w.eng_a, django_capture_on_commit_callbacks))
        reader = PdfReader(io.BytesIO(download(p1c, job)))
        assert sum(len(p.images) for p in reader.pages) >= 1
        assert "proof.png" in pdf_text(download(p1c, job))

    def test_filters_limit_the_findings(self, w, p1c, django_capture_on_commit_callbacks):
        seed(w, p1c)
        job = done(
            p1c, request_report(p1c, w.eng_a, django_capture_on_commit_callbacks, filters={"severities": ["critical"]})
        )
        text = pdf_text(download(p1c, job))
        assert job["finding_count"] == 1 and "SQL injection in search" in text and "Stored XSS in comments" not in text

    def test_closed_findings_and_remediation_roadmap(self, w, p1c, django_capture_on_commit_callbacks):
        seeded = seed(w, p1c)
        Finding.objects.filter(pk=seeded[0]["id"]).update(status="closed", closed_at=timezone.now())
        Finding.objects.filter(pk=seeded[1]["id"]).update(due_date=timezone.localdate() - timedelta(days=3))
        job = done(p1c, request_report(p1c, w.eng_a, django_capture_on_commit_callbacks))
        text = pdf_text(download(p1c, job))
        assert "Overdue" in text and "Closed" in text

    def test_custom_template_changes_sections_footer_and_logo(
        self, w, admin_client, p1c, django_capture_on_commit_callbacks
    ):
        seed(w, p1c, count=1)
        r = admin_client.post(
            TEMPLATES,
            {"name": "Slim", "sections": ["executive_summary", "findings"], "accent": "#1d4ed8", "font": "serif",
             "footer_text": "Acme confidential 2026"},
            format="json",
        )  # fmt: skip
        assert r.status_code == 201, r.content
        tid = r.json()["id"]
        logo = SimpleUploadedFile("logo.png", png_bytes((300, 100), "blue"), content_type="image/png")
        assert admin_client.post(f"{TEMPLATES}/{tid}/logo", {"logo": logo}, format="multipart").status_code == 200
        job = done(p1c, request_report(p1c, w.eng_a, django_capture_on_commit_callbacks, template=tid))
        text = pdf_text(download(p1c, job))
        assert "Executive summary" in text and "Detailed findings" in text and "Acme confidential 2026" in text
        assert "Remediation roadmap" not in text and "Appendix" not in text
        assert job["template"]["name"] == "Slim"

    def test_render_time_stays_inside_the_budget(self, w, p1c, django_capture_on_commit_callbacks):
        seed(w, p1c, count=2)
        for i in range(30):
            publish(p1c, make(p1c, w.eng_a, title=f"Bulk finding {i}", severity="medium", description="Text. " * 40))
        started = time.monotonic()
        job = done(p1c, request_report(p1c, w.eng_a, django_capture_on_commit_callbacks))
        assert job["finding_count"] == 32 and job["page_count"] > 35
        assert time.monotonic() - started < 60


# ------------------------------------------------------------------ safety


class TestFetcher:
    def test_only_data_uris_and_bundled_fonts_pass(self):
        font = (render.FONT_DIR / "geist-latin-400-normal.woff").as_uri()
        assert render.safe_fetcher(font) is not None
        assert render.safe_fetcher("data:text/plain;base64,aGk=") is not None
        for url in (
            "http://127.0.0.1:8000/api/v1/health/ready", "https://example.com/x.png", "file:///etc/passwd",
            (render.FONT_DIR / ".." / "report.css").as_uri(), (render.FONT_DIR.parent / "wordmark-dark.svg").as_uri(),
            "ftp://example.com/x", "file:///app/config/settings/base.py",
        ):  # fmt: skip
            with pytest.raises(ValueError):
                render.safe_fetcher(url)

    @pytest.mark.django_db
    def test_hostile_markdown_cannot_pull_resources(self, w, p1c, django_capture_on_commit_callbacks, monkeypatch):
        seen = []
        real = render.safe_fetcher

        def spy(url, *a, **k):
            seen.append(url)
            return real(url, *a, **k)

        monkeypatch.setattr(render, "safe_fetcher", spy)
        make(
            p1c, w.eng_a, title="Hostile text",
            description=(
                "![x](http://127.0.0.1:9/ssrf.png) ![y](file:///etc/passwd)\n\n"
                '<img src="http://127.0.0.1:9/raw.png"><link rel="stylesheet" href="http://127.0.0.1:9/a.css">\n\n'
                "<style>@import url(http://127.0.0.1:9/i.css); body{background:url(file:///etc/passwd)}</style>"
                "[link](javascript:alert(1)) [ok](https://example.com)"
            ),
        )  # fmt: skip
        f = Finding.objects.get(title="Hostile text")
        publish(p1c, {"id": str(f.pk), "version": f.version})
        job = done(p1c, request_report(p1c, w.eng_a, django_capture_on_commit_callbacks))
        assert all(u.startswith(("data:", "file://")) for u in seen), seen
        assert not any("127.0.0.1" in u or "passwd" in u for u in seen)
        assert "Hostile text" in pdf_text(download(p1c, job))


# ------------------------------------------------------------------ csv


@pytest.mark.django_db
class TestCsv:
    def rows(self, client, job):
        return list(csv.reader(io.StringIO(download(client, job).decode())))

    def test_client_csv_has_no_technical_columns(self, w, p1c, django_capture_on_commit_callbacks):
        seed(w, p1c)
        job = done(p1c, request_report(p1c, w.eng_a, django_capture_on_commit_callbacks, format="csv"))
        t = self.rows(p1c, job)
        assert t[0] == render.CSV_COLUMNS and len(t) == 5
        assert "technical_details" not in t[0] and "TECH-SECRET" not in "".join("".join(r) for r in t)
        assert job["file_name"].endswith(".csv") and job["page_count"] is None

    def test_internal_csv_has_them(self, w, p1c, django_capture_on_commit_callbacks):
        seed(w, p1c, count=2)
        job = done(
            p1c, request_report(p1c, w.eng_a, django_capture_on_commit_callbacks, format="csv", audience="internal")
        )
        t = self.rows(p1c, job)
        assert t[0] == render.CSV_COLUMNS + render.CSV_INTERNAL_COLUMNS and "TECH-SECRET sqlmap output" in t[1] + t[2]

    def test_formula_cells_are_neutralised(self, w, p1c, django_capture_on_commit_callbacks):
        publish(p1c, make(p1c, w.eng_a, title='=HYPERLINK("http://evil")', severity="low"))
        job = done(p1c, request_report(p1c, w.eng_a, django_capture_on_commit_callbacks, format="csv"))
        assert self.rows(p1c, job)[1][1].startswith("'=")


# ------------------------------------------------------------------ access control


@pytest.mark.django_db
class TestAccess:
    def test_remediation_user_cannot_create_or_list(self, w, r1c, django_capture_on_commit_callbacks):
        assert r1c.get(REPORTS).status_code == 403
        r = r1c.post(REPORTS, {"engagement": str(w.eng_a.pk), "format": "pdf", "audience": "client"}, format="json")
        assert r.status_code == 403

    def test_other_engagement_is_out_of_reach(self, w, p1c, admin_client, django_capture_on_commit_callbacks):
        r = p1c.post(REPORTS, {"engagement": str(w.eng_b.pk), "format": "pdf", "audience": "client"}, format="json")
        assert r.status_code == 400
        job = done(admin_client, request_report(admin_client, w.eng_b, django_capture_on_commit_callbacks))
        assert p1c.get(f"{REPORTS}/{job['id']}").status_code == 404
        assert p1c.get(f"{REPORTS}/{job['id']}/download").status_code == 404
        assert job["id"] not in {j["id"] for j in p1c.get(REPORTS).json()["results"]}

    def test_the_report_only_holds_what_the_requester_can_see(self, w, p1c, django_capture_on_commit_callbacks):
        seeded = seed(w, p1c)
        EngagementMembership.objects.create(engagement=w.eng_a, user=w.p3, finding_scope="assigned")
        Finding.objects.filter(pk=seeded[2]["id"]).update(assigned_pentester=w.p3)
        c3 = signed_in(w.p3)
        job = done(c3, request_report(c3, w.eng_a, django_capture_on_commit_callbacks))
        text = pdf_text(download(c3, job))
        assert job["finding_count"] == 1 and "Verbose server banner" in text and "SQL injection in search" not in text

    def test_internal_needs_technical_access(self, w, django_capture_on_commit_callbacks):
        role = make_role(
            "Report writer",
            ["engagements.view", "findings.view", "reports.view", "reports.generate_pdf", "exports.csv"],
            all_engagements=False, finding_scope="all",
        )  # fmt: skip
        user = make_user("writer@example.com", role)
        EngagementMembership.objects.create(engagement=w.eng_a, user=user)
        c = signed_in(user)
        r = c.post(REPORTS, {"engagement": str(w.eng_a.pk), "format": "pdf", "audience": "internal"}, format="json")
        assert r.status_code == 403
        assert AuditEvent.objects.filter(action="report.request_denied", outcome="denied").exists()
        ok = request_report(c, w.eng_a, django_capture_on_commit_callbacks)
        assert ok.status_code == 201

    def test_worker_rechecks_rights(self, w, p1c, monkeypatch):
        seed(w, p1c, count=1)
        monkeypatch.setattr(services, "_enqueue", lambda job_id: None)
        r = p1c.post(REPORTS, {"engagement": str(w.eng_a.pk), "format": "pdf", "audience": "client"}, format="json")
        job_id = r.json()["id"]
        EngagementMembership.objects.filter(engagement=w.eng_a, user=w.p1).delete()
        w.p1.role = make_role("Nothing", ["engagements.view"], all_engagements=False)
        w.p1.save()
        services.build_job(job_id)
        job = ReportJob.objects.get(pk=job_id)
        assert job.status == "failed" and "no longer has permission" in job.error and not job.storage_key
        assert AuditEvent.objects.filter(action="report.failed", outcome="failure").exists()

    def test_one_build_at_a_time_per_engagement(self, w, p1c, monkeypatch):
        monkeypatch.setattr(services, "_enqueue", lambda job_id: None)
        body = {"engagement": str(w.eng_a.pk), "format": "pdf", "audience": "client"}
        assert p1c.post(REPORTS, body, format="json").status_code == 201
        assert p1c.post(REPORTS, body, format="json").status_code == 409

    def test_too_many_findings_is_refused_with_a_clear_message(
        self, w, p1c, monkeypatch, django_capture_on_commit_callbacks
    ):
        seed(w, p1c, count=3)
        monkeypatch.setattr(builder, "MAX_FINDINGS", 2)
        r = request_report(p1c, w.eng_a, django_capture_on_commit_callbacks)
        job = p1c.get(f"{REPORTS}/{r.json()['id']}").json()
        assert job["status"] == "failed" and "Narrow the filters" in job["error"]

    def test_body_is_strict(self, w, p1c):
        r = p1c.post(REPORTS, {"engagement": str(w.eng_a.pk), "format": "pdf", "status": "done"}, format="json")
        assert r.status_code == 400
        r = p1c.post(REPORTS, {"engagement": str(w.eng_a.pk), "format": "docx"}, format="json")
        assert r.status_code == 400

    def test_anonymous_gets_401(self, w):
        from tests.conftest import Api

        assert Api().get(REPORTS).status_code == 401


# ------------------------------------------------------------------ audit and retention


@pytest.mark.django_db
class TestAuditAndRetention:
    def test_generation_and_download_are_chained_in_the_audit_log(self, w, p1c, django_capture_on_commit_callbacks):
        seed(w, p1c, count=2)
        job = done(p1c, request_report(p1c, w.eng_a, django_capture_on_commit_callbacks))
        data = download(p1c, job)
        gen = AuditEvent.objects.get(action="report.generated")
        import hashlib

        assert gen.metadata["sha256"] == hashlib.sha256(data).hexdigest() == job["sha256"]
        assert gen.metadata["filters"]["statuses"] and gen.metadata["findings"] == 2
        assert AuditEvent.objects.filter(action__in=["report.requested", "report.downloaded"]).count() == 2
        assert verify_chain().ok

    def test_download_headers(self, w, p1c, django_capture_on_commit_callbacks):
        seed(w, p1c, count=1)
        job = done(p1c, request_report(p1c, w.eng_a, django_capture_on_commit_callbacks))
        r = p1c.get(f"{REPORTS}/{job['id']}/download")
        assert r["Content-Type"] == "application/pdf" and "attachment" in r["Content-Disposition"]
        assert r["Cache-Control"] == "no-store" and r["X-Content-Type-Options"] == "nosniff"

    def test_expired_files_are_purged_and_answer_410(self, w, p1c, django_capture_on_commit_callbacks, media_root):
        seed(w, p1c, count=1)
        job = done(p1c, request_report(p1c, w.eng_a, django_capture_on_commit_callbacks))
        ReportJob.objects.filter(pk=job["id"]).update(expires_at=timezone.now() - timedelta(days=1))
        assert services.cleanup()["purged"] == 1
        assert p1c.get(f"{REPORTS}/{job['id']}/download").status_code == 410
        assert not any(p.is_file() for p in Path(media_root).rglob("*"))
        assert p1c.get(f"{REPORTS}/{job['id']}").json()["file_available"] is False

    def test_stuck_jobs_are_failed(self, w, p1c, monkeypatch):
        monkeypatch.setattr(services, "_enqueue", lambda job_id: None)
        r = p1c.post(REPORTS, {"engagement": str(w.eng_a.pk), "format": "pdf", "audience": "client"}, format="json")
        ReportJob.objects.filter(pk=r.json()["id"]).update(updated_at=timezone.now() - timedelta(hours=1))
        assert services.cleanup()["failed"] == 1
        assert ReportJob.objects.get(pk=r.json()["id"]).status == "failed"


# ------------------------------------------------------------------ templates


@pytest.mark.django_db
class TestTemplates:
    def test_default_template_is_seeded(self):
        t = ReportTemplate.objects.get(is_default=True)
        assert t.name == "RedShadow standard" and "findings" in t.sections

    def test_everyone_who_makes_reports_can_read_but_not_write(self, w, p1c, r1c):
        assert [t["name"] for t in p1c.get(TEMPLATES).json()["results"]] == ["RedShadow standard"]
        assert p1c.post(TEMPLATES, {"name": "x"}, format="json").status_code == 403
        assert r1c.get(TEMPLATES).status_code == 403

    def test_admin_crud_with_audit(self, admin_client):
        r = admin_client.post(TEMPLATES, {"name": "Board", "accent": "#112233", "font": "serif"}, format="json")
        assert r.status_code == 201
        t = r.json()
        r = admin_client.patch(
            f"{TEMPLATES}/{t['id']}", {"footer_text": "Board only", "version": t["version"]}, format="json"
        )
        assert r.status_code == 200 and r.json()["version"] == 2
        stale = admin_client.patch(f"{TEMPLATES}/{t['id']}", {"footer_text": "x", "version": 1}, format="json")
        assert stale.status_code == 409
        assert admin_client.delete(f"{TEMPLATES}/{t['id']}").status_code == 204
        actions = set(AuditEvent.objects.filter(action__startswith="report_template.").values_list("action", flat=True))
        assert {"report_template.created", "report_template.updated", "report_template.deleted"} <= actions

    @pytest.mark.parametrize(
        "body",
        [
            {"name": "bad", "sections": ["executive_summary"]},
            {"name": "bad", "sections": ["findings", "findings"]},
            {"name": "bad", "sections": ["findings", "exfiltrate"]},
            {"name": "bad", "accent": "red"},
            {"name": "bad", "accent": "#12345"},
            {"name": "bad", "font": "Comic Sans"},
            {"name": "bad", "is_admin": True},
            {"accent": "#112233"},
        ],
    )
    def test_invalid_templates_are_refused(self, admin_client, body):
        assert admin_client.post(TEMPLATES, body, format="json").status_code == 400

    def test_default_cannot_be_deleted_and_moves_cleanly(self, admin_client):
        default = ReportTemplate.objects.get(is_default=True)
        assert admin_client.delete(f"{TEMPLATES}/{default.pk}").status_code == 409
        other = admin_client.post(TEMPLATES, {"name": "New default", "is_default": True}, format="json").json()
        assert other["is_default"] is True
        assert list(ReportTemplate.objects.filter(is_default=True).values_list("name", flat=True)) == ["New default"]

    def test_logo_rules(self, admin_client, media_root):
        t = admin_client.post(TEMPLATES, {"name": "Logo"}, format="json").json()
        url = f"{TEMPLATES}/{t['id']}/logo"

        def up(name, data, ctype):
            return admin_client.post(
                url, {"logo": SimpleUploadedFile(name, data, content_type=ctype)}, format="multipart"
            )

        assert (
            up(
                "a.svg", b"<svg xmlns='http://www.w3.org/2000/svg'><script>1</script></svg>", "image/svg+xml"
            ).status_code
            == 400
        )
        assert up("a.png", b"not an image", "image/png").status_code == 400
        assert up("a.png", png_bytes((2100, 10)), "image/png").status_code == 400
        assert up("a.png", png_bytes((100, 40)), "image/png").status_code == 200
        shown = admin_client.get(url)
        assert shown.status_code == 200 and shown["Content-Type"] == "image/png"
        first = ReportTemplate.objects.get(pk=t["id"]).logo_key
        assert up("b.png", png_bytes((100, 40), "green"), "image/png").status_code == 200
        assert not (Path(media_root) / first).exists()
        assert admin_client.delete(url).json()["has_logo"] is False
        assert admin_client.get(url).status_code == 404
