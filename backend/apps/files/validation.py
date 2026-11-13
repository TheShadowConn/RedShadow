"""Upload inspection: trust nothing the client says.

Type comes from the bytes (magic numbers), not the name or the Content-Type header. The claimed
extension must agree with the detected type. Images are re-encoded (metadata and any trailing
polyglot payload are dropped). Archives are checked without being extracted.
"""

import io
import json
import re
import unicodedata
import zipfile
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

Image.MAX_IMAGE_PIXELS = 50_000_000  # Pillow raises DecompressionBombError above 2x this

ALLOWED_EXTENSIONS = {
    "png": {"png"},
    "jpeg": {"jpg", "jpeg"},
    "gif": {"gif"},
    "webp": {"webp"},
    "pdf": {"pdf"},
    "pcap": {"pcap", "cap"},
    "pcapng": {"pcapng", "pcap"},
    "zip": {"zip"},
    "docx": {"docx"},
    "xlsx": {"xlsx"},
    "text": {"txt", "log", "csv", "json", "xml"},
}
CANONICAL_EXT = {"png": "png", "jpeg": "jpg", "gif": "gif", "webp": "webp", "pdf": "pdf", "pcap": "pcap",
                 "pcapng": "pcapng", "zip": "zip", "docx": "docx", "xlsx": "xlsx"}  # fmt: skip
# Served Content-Type. Text is always text/plain so a log containing markup can never render.
MIME = {
    "png": "image/png", "jpeg": "image/jpeg", "gif": "image/gif", "webp": "image/webp",
    "pdf": "application/pdf", "pcap": "application/vnd.tcpdump.pcap", "pcapng": "application/octet-stream",
    "zip": "application/zip", "text": "text/plain; charset=utf-8",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}  # fmt: skip
IMAGE_KINDS = {"png", "jpeg", "gif", "webp"}

ZIP_MAX_ENTRIES = 2000
ZIP_MAX_UNCOMPRESSED = 500 * 1024 * 1024
ZIP_MAX_RATIO = 200  # per entry, applied above 1 MB
PCAP_MAGICS = (b"\xa1\xb2\xc3\xd4", b"\xd4\xc3\xb2\xa1", b"\xa1\xb2\x3c\x4d", b"\x4d\x3c\xb2\xa1")
ALLOWED_CONTROL = {9, 10, 12, 13, 27}  # tab, LF, FF, CR, ESC (ANSI colours in logs)
_UNSAFE_NAME = re.compile(r"[^\w .()+@\-]", re.UNICODE)


class UploadRejected(ValueError):
    """Message is safe to show to the user."""


@dataclass
class Inspected:
    kind: str  # key of ALLOWED_EXTENSIONS
    mime: str
    ext: str
    data: bytes  # possibly re-encoded: store this, not the upload


def clean_name(raw: str) -> str:
    """Display name only. Never used as a path."""
    name = unicodedata.normalize("NFKC", raw or "").replace("\\", "/").split("/")[-1]
    name = "".join(ch for ch in name if ch.isprintable())
    name = _UNSAFE_NAME.sub("_", name).strip(" .")
    if len(name) > 100:
        stem, dot, ext = name.rpartition(".")
        name = (stem[: 100 - len(ext) - 1] + dot + ext) if dot and len(ext) < 10 else name[:100]
    return name or "file"


def _extension(name: str) -> str:
    return name.rpartition(".")[2].lower() if "." in name else ""


def _detect_binary(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data[:4] in PCAP_MAGICS:
        return "pcap"
    if data.startswith(b"\x0a\x0d\x0d\x0a"):
        return "pcapng"
    if data.startswith(b"PK\x03\x04"):
        return "zip"
    return None


def _inspect_zip(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            infos = zf.infolist()
            if len(infos) > ZIP_MAX_ENTRIES:
                raise UploadRejected("The archive contains too many files.")
            total = 0
            for info in infos:
                if info.filename.startswith("/") or ".." in info.filename.replace("\\", "/").split("/"):
                    raise UploadRejected("The archive contains unsafe file paths.")
                total += info.file_size
                if info.file_size > 1024 * 1024 and info.file_size / max(info.compress_size, 1) > ZIP_MAX_RATIO:
                    raise UploadRejected("The archive expands suspiciously and was refused.")
            if total > ZIP_MAX_UNCOMPRESSED:
                raise UploadRejected("The archive expands to too much data.")
            names = {i.filename for i in infos}
    except zipfile.BadZipFile:
        raise UploadRejected("The archive is corrupt.") from None
    if "[Content_Types].xml" in names:
        if any(n.startswith("word/") for n in names):
            return "docx"
        if any(n.startswith("xl/") for n in names):
            return "xlsx"
    return "zip"


def _inspect_text(data: bytes, ext: str) -> str:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise UploadRejected("This file type is not allowed.") from None
    if any(ord(ch) < 32 and ord(ch) not in ALLOWED_CONTROL for ch in text):
        raise UploadRejected("This file type is not allowed.")
    head = text[:2048].lstrip().lower()
    if head.startswith(("<!doctype html", "<html", "<svg")) or "<svg" in head[:300]:
        raise UploadRejected("HTML and SVG files are not allowed.")
    if ext == "json":
        try:
            json.loads(text)
        except ValueError:
            raise UploadRejected("The file is not valid JSON.") from None
    return "text"


def _reencode(kind: str, data: bytes) -> bytes:
    try:
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()
        with Image.open(io.BytesIO(data)) as im:
            animated = getattr(im, "is_animated", False) and kind in {"gif", "webp"}
            out = io.BytesIO()
            if kind == "jpeg":
                im = ImageOps.exif_transpose(im)
                im.convert("RGB").save(out, "JPEG", quality=90, optimize=True)
            elif kind == "png":
                im.save(out, "PNG", optimize=True)
            elif kind == "gif":
                im.save(out, "GIF", save_all=animated)
            else:
                im.save(out, "WEBP", quality=90, save_all=animated)
            return out.getvalue()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError, ValueError):
        raise UploadRejected("The image is corrupt or too large.") from None


def inspect_upload(name: str, data: bytes, allowed_kinds: set[str] | None = None) -> Inspected:
    if not data:
        raise UploadRejected("The file is empty.")
    ext = _extension(name)
    kind = _detect_binary(data)
    if kind == "zip":
        kind = _inspect_zip(data)
    elif kind is None:
        kind = _inspect_text(data, ext)
    if allowed_kinds is not None and kind not in allowed_kinds:
        raise UploadRejected("This file type is not allowed here.")
    if ext not in ALLOWED_EXTENSIONS[kind]:
        raise UploadRejected("The file content does not match its extension, or the type is not allowed.")
    if kind in IMAGE_KINDS:
        data = _reencode(kind, data)
    return Inspected(kind=kind, mime=MIME[kind], ext=CANONICAL_EXT.get(kind, ext), data=data)
