import io
import re
import zipfile
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.utils import timezone
from PIL import Image

from apps.audit.models import AuditEvent
from apps.audit.service import verify_chain
from apps.core.storage import KEY_RE, InvalidKey, LocalStorage, get_storage
from apps.engagements import services as eng_services
from apps.files import services as file_services
from apps.files.models import Attachment
from tests.conftest import Api, signed_in
from tests.world import build_world

API = "/api/v1"


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


@pytest.fixture
def w(admin):
    return build_world(admin)


def png(size=(8, 8)):
    out = io.BytesIO()
    Image.new("RGB", size, "red").save(out, "PNG")
    return out.getvalue()


def zip_bytes(entries: dict[str, bytes]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return out.getvalue()


def docs(eng):
    return f"{API}/engagements/{eng.pk}/documents"


def upload(client, eng, name, content, ctype="application/octet-stream"):
    return client.post(docs(eng), {"file": SimpleUploadedFile(name, content, content_type=ctype)}, format="multipart")


@pytest.mark.django_db
class TestUploadValidation:
    @pytest.mark.parametrize(
        "name,content",
        [
            ("shot.png", png()),
            ("notes.txt", b"plain notes\n"),
            ("scan.log", b"GET /?q=<script>alert(1)</script> HTTP/1.1\n\x1b[31mred\x1b[0m\n"),
            ("hosts.csv", b"ip,port\n10.0.0.1,443\n"),
            ("data.json", b'{"a": 1}'),
            ("report.pdf", b"%PDF-1.7\n%fake but has the right magic\n"),
            ("cap.pcap", b"\xd4\xc3\xb2\xa1" + b"\x00" * 60),
            ("bundle.zip", zip_bytes({"a.txt": b"hi"})),
            ("memo.docx", zip_bytes({"[Content_Types].xml": b"<x/>", "word/document.xml": b"<x/>"})),
            ("sheet.xlsx", zip_bytes({"[Content_Types].xml": b"<x/>", "xl/workbook.xml": b"<x/>"})),
        ],
    )
    def test_allowed_types(self, admin_client, w, name, content):
        r = upload(admin_client, w.eng_a, name, content)
        assert r.status_code == 201, r.content
        assert r.json()["original_name"] == name

    @pytest.mark.parametrize(
        "name,content",
        [
            ("page.txt", b"<html><body>hi</body></html>"),
            ("logo.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>"),
            ("logo.png", b"<svg xmlns='http://www.w3.org/2000/svg'/>"),
            ("tool.txt", b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 100),
            ("tool.exe", b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 100),
            ("script.sh", b"#!/bin/sh\necho hi\n"),
            ("image.png", b"\xff\xd8\xff\xe0" + b"\x00" * 40),  # jpeg content, png name
            ("fake.docx", zip_bytes({"a.txt": b"not office"})),
            ("doc.zip", zip_bytes({"[Content_Types].xml": b"<x/>", "word/document.xml": b"<x/>"})),
            ("broken.png", b"\x89PNG\r\n\x1a\nnot really a png"),
            ("bad.json", b"{nope"),
            ("noext", b"plain"),
            ("empty.txt", b""),
        ],
    )
    def test_rejected_types(self, admin_client, w, name, content):
        r = upload(admin_client, w.eng_a, name, content)
        assert r.status_code == 400, (name, r.content)
        assert "file" in r.json()["error"]["fields"]

    def test_client_content_type_is_ignored(self, admin_client, w):
        assert upload(admin_client, w.eng_a, "a.png", png(), ctype="text/html").json()["mime"] == "image/png"
        assert upload(admin_client, w.eng_a, "b.txt", b"x", ctype="image/png").json()["mime"].startswith("text/plain")

    def test_zip_bomb_and_zip_slip_and_entry_flood(self, admin_client, w):
        bomb = zip_bytes({"zeros.bin": b"\x00" * (6 * 1024 * 1024)})
        assert len(bomb) < 100_000
        assert upload(admin_client, w.eng_a, "bomb.zip", bomb).status_code == 400
        assert upload(admin_client, w.eng_a, "slip.zip", zip_bytes({"../evil.txt": b"x"})).status_code == 400
        flood = zip_bytes({f"f{i}.txt": b"x" for i in range(2001)})
        assert upload(admin_client, w.eng_a, "flood.zip", flood).status_code == 400

    def test_oversize_is_413(self, admin_client, w, settings):
        settings.ATTACHMENT_MAX_BYTES = 1000
        r = upload(admin_client, w.eng_a, "big.txt", b"x" * 2000)
        assert r.status_code == 413 and r.json()["error"]["code"] == "payload_too_large"
        assert upload(admin_client, w.eng_a, "ok.txt", b"x" * 900).status_code == 201

    def test_extra_form_fields_rejected(self, admin_client, w):
        r = admin_client.post(
            docs(w.eng_a), {"file": SimpleUploadedFile("a.txt", b"x"), "kind": "logo"}, format="multipart"
        )
        assert r.status_code == 400
        assert admin_client.post(docs(w.eng_a), {}, format="multipart").status_code == 400


@pytest.mark.django_db
class TestStorageSafety:
    def test_names_never_reach_the_filesystem(self, admin_client, w, media_root):
        r = upload(admin_client, w.eng_a, "../../etc/passwd.txt", b"root")
        assert r.status_code == 201 and r.json()["original_name"] == "passwd.txt"
        att = Attachment.objects.get(pk=r.json()["id"])
        assert KEY_RE.match(att.storage_key) and "passwd" not in att.storage_key
        assert (media_root / att.storage_key).is_file()
        names = [p.name for p in media_root.rglob("*") if p.is_file()]
        assert all(re.fullmatch(r"[0-9a-f-]{36}", n) for n in names)
        r = upload(admin_client, w.eng_a, "evil\nname\x07.txt", b"x")
        assert "\n" not in r.json()["original_name"] and "\x07" not in r.json()["original_name"]
        assert (
            "php"
            not in Attachment.objects.get(
                pk=upload(admin_client, w.eng_a, "shell.php.png", png()).json()["id"]
            ).storage_key
        )

    def test_images_are_reencoded_exif_stripped_and_trailing_payload_dropped(self, admin_client, w):
        exif = Image.Exif()
        exif[0x010F] = "SecretCamera"
        out = io.BytesIO()
        Image.new("RGB", (8, 8), "blue").save(out, "JPEG", exif=exif)
        assert b"SecretCamera" in out.getvalue()
        att = Attachment.objects.get(pk=upload(admin_client, w.eng_a, "photo.jpg", out.getvalue()).json()["id"])
        stored = get_storage().read(att.storage_key)
        assert b"SecretCamera" not in stored and not Image.open(io.BytesIO(stored)).getexif()
        polyglot = png() + b"<script>alert(1)</script>"
        att = Attachment.objects.get(pk=upload(admin_client, w.eng_a, "poly.png", polyglot).json()["id"])
        assert b"<script" not in get_storage().read(att.storage_key)
        assert att.size == len(get_storage().read(att.storage_key))

    def test_sha256_matches_stored_bytes(self, admin_client, w):
        import hashlib

        att = Attachment.objects.get(pk=upload(admin_client, w.eng_a, "n.txt", b"hello").json()["id"])
        assert att.sha256 == hashlib.sha256(get_storage().read(att.storage_key)).hexdigest()

    def test_storage_rejects_bad_keys_and_sets_permissions(self, media_root):
        store = LocalStorage(media_root)
        for bad in ("../../etc/passwd", "2026/01/not-a-uuid", "/abs/path", "2026/01/" + "0" * 36 + "/../x"):
            with pytest.raises(InvalidKey):
                store.read(bad)
        key = store.save(b"data")
        assert (media_root / key).stat().st_mode & 0o777 == 0o644 and store.read(key) == b"data"
        store.delete(key)
        assert not store.exists(key)

    def test_blob_removed_when_database_write_fails(self, admin_client, w, media_root, monkeypatch):
        monkeypatch.setattr(
            file_services.Attachment.objects, "create", lambda **kw: (_ for _ in ()).throw(RuntimeError("db down"))
        )
        with pytest.raises(RuntimeError):
            file_services.upload_document(None, w.eng_a.created_by, w.eng_a, SimpleUploadedFile("a.txt", b"x"))
        assert [p for p in media_root.rglob("*") if p.is_file()] == []

    def test_owner_check_constraint(self, admin, w):
        with pytest.raises(IntegrityError), transaction.atomic():
            Attachment.objects.create(
                kind="logo",
                engagement=w.eng_a,
                original_name="x",
                storage_key="k",
                mime="m",
                size=1,
                sha256="s",
                uploaded_by=admin,
            )


@pytest.mark.django_db
class TestDocumentAccess:
    def test_upload_permissions(self, w):
        assert upload(signed_in(w.p1), w.eng_a, "a.txt", b"x").status_code == 201
        assert upload(signed_in(w.r1), w.eng_a, "a.txt", b"x").status_code == 403  # remediation lacks documents.upload
        assert upload(signed_in(w.p3), w.eng_a, "a.txt", b"x").status_code == 404
        assert upload(signed_in(w.p2), w.eng_a, "a.txt", b"x").status_code == 404
        assert upload(Api(), w.eng_a, "a.txt", b"x").status_code in (401, 403)

    def test_listing_and_download_are_scoped(self, w):
        att_id = upload(signed_in(w.p1), w.eng_a, "secret.txt", b"classified").json()["id"]
        for user, expected in ((w.p1, 200), (w.r1, 200), (w.p2, 404), (w.p3, 404)):
            c = signed_in(user)
            assert c.get(docs(w.eng_a)).status_code == expected
            assert c.get(f"{API}/attachments/{att_id}/download").status_code == expected
            assert c.get(f"{API}/attachments/{att_id}").status_code == expected
        assert signed_in(w.p2).get(f"{API}/attachments").json()["count"] == 0
        assert signed_in(w.p1).get(f"{API}/attachments?engagement={w.eng_a.pk}").json()["count"] == 1
        assert signed_in(w.p1).get(f"{API}/attachments?engagement=junk").json()["count"] == 0
        assert Api().get(f"{API}/attachments/{att_id}/download").status_code in (401, 403)

    def test_download_hands_off_to_nginx_with_safe_headers(self, w):
        att = Attachment.objects.get(pk=upload(signed_in(w.p1), w.eng_a, 'we"ird name é.txt', b"hello").json()["id"])
        r = signed_in(w.p1).get(f"{API}/attachments/{att.pk}/download")
        assert r.status_code == 200 and r.content == b""
        assert r["X-Accel-Redirect"] == f"/protected/{att.storage_key}"
        assert r["Content-Disposition"].startswith("attachment;") and "\n" not in r["Content-Disposition"]
        assert r["X-Content-Type-Options"] == "nosniff" and "sandbox" in r["Content-Security-Policy"]
        assert r["Cache-Control"] == "private, no-store" and r["Content-Type"].startswith("text/plain")

    def test_delete_and_purge(self, admin_client, w):
        att_id = upload(signed_in(w.p1), w.eng_a, "gone.txt", b"bye").json()["id"]
        assert signed_in(w.p1).delete(f"{API}/attachments/{att_id}").status_code == 403  # no documents.delete
        assert signed_in(w.r1).delete(f"{API}/attachments/{att_id}").status_code == 403
        assert (
            signed_in(w.p2).delete(f"{API}/attachments/{att_id}").status_code == 403
        )  # code gate: same answer for all
        assert admin_client.delete(f"{API}/attachments/{att_id}").status_code == 204
        assert admin_client.get(f"{API}/attachments/{att_id}/download").status_code == 404
        assert admin_client.get(docs(w.eng_a)).json()["count"] == 0
        att = Attachment.objects.get(pk=att_id)
        assert get_storage().exists(att.storage_key)
        assert file_services.purge_deleted() == 0  # inside retention
        Attachment.objects.filter(pk=att_id).update(deleted_at=timezone.now() - timedelta(days=31))
        assert file_services.purge_deleted() == 1
        att.refresh_from_db()
        assert att.purged_at is not None and not get_storage().exists(att.storage_key)
        assert file_services.purge_deleted() == 0

    def test_archived_engagement_is_read_only(self, admin, admin_client, w):
        w.eng_a.status = "completed"
        w.eng_a.save()
        eng_services.archive_engagement(None, admin, w.eng_a, 1)
        assert upload(admin_client, w.eng_a, "a.txt", b"x").status_code == 409

    def test_audit_trail(self, admin_client, w):
        att_id = upload(admin_client, w.eng_a, "a.txt", b"x").json()["id"]
        admin_client.get(f"{API}/attachments/{att_id}/download")
        admin_client.delete(f"{API}/attachments/{att_id}")
        actions = set(AuditEvent.objects.filter(engagement_id=w.eng_a.pk).values_list("action", flat=True))
        assert {"attachment.uploaded", "attachment.downloaded", "attachment.deleted"} <= actions
        assert verify_chain().ok

    def test_denied_upload_is_audited(self, admin_client, w):
        from apps.rbac.models import Role

        rem = Role.objects.get(system_key="remediation")  # p3 is a pentester, but read-only on this engagement
        admin_client.post(
            f"{API}/engagements/{w.eng_b.pk}/members",
            {"user": str(w.p3.pk), "role_override": str(rem.pk)},
            format="json",
        )
        assert upload(signed_in(w.p3), w.eng_b, "a.txt", b"x").status_code == 403
        assert AuditEvent.objects.filter(action="attachment.upload_denied", outcome="denied").exists()


@pytest.mark.django_db
class TestLogo:
    def test_set_replace_remove(self, admin_client, w):
        url = f"{API}/organisations/{w.org_a.pk}/logo"
        r = admin_client.post(
            url, {"file": SimpleUploadedFile("l.png", png(), content_type="image/png")}, format="multipart"
        )
        assert r.status_code == 200 and r.json()["logo_url"]
        first = r.json()["logo_url"]
        assert signed_in(w.p1).get(first).status_code == 200  # member of an engagement of this organisation
        assert signed_in(w.p2).get(first).status_code == 404
        assert signed_in(w.p3).get(first).status_code == 404
        r = admin_client.post(
            url, {"file": SimpleUploadedFile("l2.png", png((4, 4)), content_type="image/png")}, format="multipart"
        )
        assert r.json()["logo_url"] != first
        assert admin_client.get(first).status_code == 404  # old logo is soft-deleted
        assert admin_client.delete(url).status_code == 204
        assert admin_client.get(f"{API}/organisations/{w.org_a.pk}").json()["logo_url"] is None

    def test_only_images_and_only_with_permission(self, admin_client, w):
        url = f"{API}/organisations/{w.org_a.pk}/logo"
        r = admin_client.post(
            url,
            {"file": SimpleUploadedFile("l.pdf", b"%PDF-1.7\n", content_type="application/pdf")},
            format="multipart",
        )
        assert r.status_code == 400
        r = signed_in(w.p1).post(url, {"file": SimpleUploadedFile("l.png", png())}, format="multipart")
        assert r.status_code == 403
        assert signed_in(w.p1).delete(url).status_code == 403

    def test_logo_cannot_be_deleted_as_document(self, admin_client, w):
        url = f"{API}/organisations/{w.org_a.pk}/logo"
        r = admin_client.post(url, {"file": SimpleUploadedFile("l.png", png())}, format="multipart")
        att_id = r.json()["logo_url"].split("/")[-2]
        assert admin_client.delete(f"{API}/attachments/{att_id}").status_code == 409

    def test_organisation_delete_is_405(self, admin_client, w):
        assert admin_client.delete(f"{API}/organisations/{w.org_a.pk}").status_code == 405
        assert signed_in(w.p1).delete(f"{API}/organisations/{w.org_a.pk}").status_code == 403
