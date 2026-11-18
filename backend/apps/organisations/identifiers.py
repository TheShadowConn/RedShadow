"""Asset identifiers: kinds, normalisation, kind detection and match keys.

An asset can be known by many identifiers (an IP, a hostname, a URL ...). Every identifier is
normalised to one canonical form and gets a ``match_key``. The database holds one identifier per
``match_key`` per organisation, so two assets of the same organisation can never share an identifier
and the same asset can never be created twice under different spellings of one identifier.
"""

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

KINDS = [
    ("ip", "IP address"),
    ("cidr", "Network range"),
    ("hostname", "Hostname"),
    ("domain", "Domain"),
    ("url", "URL"),
    ("mac", "MAC address"),
    ("cloud_id", "Cloud resource ID"),
    ("repo", "Repository"),
    ("package", "App or package ID"),
    ("other", "Other"),
]
KIND_CODES = [code for code, _ in KINDS]
MAX_LENGTH = 500

# Hostnames and domains are both DNS names: one name cannot be both on two different assets.
_FAMILY = {"hostname": "dns", "domain": "dns"}

_LABEL = re.compile(r"^(?!-)[a-z0-9_-]{1,63}(?<!-)$")
_MAC = re.compile(r"^[0-9a-f]{12}$")
_DEFAULT_PORTS = {"http": 80, "https": 443}


class IdentifierError(ValueError):
    """The value is not valid for its kind. The message is shown to the user."""


@dataclass(frozen=True)
class Identifier:
    kind: str
    value: str  # as the user typed it (trimmed)
    normalized: str
    match_key: str

    def as_dict(self) -> dict:
        return {"kind": self.kind, "value": self.value, "normalized": self.normalized, "match_key": self.match_key}


def _dns(value: str, what: str) -> str:
    name = value.strip().rstrip(".").lower()
    if not name:
        raise IdentifierError(f"The {what} is empty.")
    try:
        name = name.encode("idna").decode("ascii") if not name.isascii() else name
    except UnicodeError:
        raise IdentifierError(f"{value!r} is not a valid {what}.") from None
    if len(name) > 253 or not all(_LABEL.match(label) for label in name.split(".")):
        raise IdentifierError(f"{value!r} is not a valid {what}.")
    return name


def _ip(value: str) -> str:
    text = value.strip().strip("[]")
    try:
        return str(ipaddress.ip_address(text))
    except ValueError:
        raise IdentifierError(f"{value!r} is not a valid IP address.") from None


def _cidr(value: str) -> str:
    try:
        return str(ipaddress.ip_network(value.strip(), strict=False))
    except ValueError:
        raise IdentifierError(f"{value!r} is not a valid network range such as 10.0.0.0/24.") from None


def _mac(value: str) -> str:
    digits = re.sub(r"[^0-9a-fA-F]", "", value).lower()
    if not _MAC.match(digits) or re.search(r"[^0-9a-fA-F:.\-\s]", value):
        raise IdentifierError(f"{value!r} is not a valid MAC address.")
    return ":".join(digits[i : i + 2] for i in range(0, 12, 2))


def _url(value: str) -> str:
    text = value.strip()
    if "://" not in text:
        raise IdentifierError(f"{value!r} must be a full URL starting with http:// or https://.")
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError:
        raise IdentifierError(f"{value!r} is not a valid URL.") from None
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https", "ftp", "ws", "wss"):
        raise IdentifierError("Only http, https, ftp, ws and wss URLs are supported.")
    if parts.username is not None or parts.password is not None:
        raise IdentifierError("A URL must not contain a user name or password.")
    host = parts.hostname or ""
    if not host:
        raise IdentifierError(f"{value!r} has no host name.")
    try:
        host = _ip(host)
        host = f"[{host}]" if ":" in host else host
    except IdentifierError:
        host = _dns(host, "host name")
    if port and port != _DEFAULT_PORTS.get(scheme):
        host = f"{host}:{port}"
    path = parts.path.rstrip("/")  # example.com/app/ and example.com/app are one thing
    return urlunsplit((scheme, host, path, parts.query, ""))  # the fragment never identifies a page


def _repo(value: str) -> str:
    text = value.strip().rstrip("/")
    if not text:
        raise IdentifierError("The repository is empty.")
    text = text.removesuffix(".git")
    if "://" in text:
        parts = urlsplit(text)
        if parts.username is not None or parts.password is not None:
            raise IdentifierError("A repository URL must not contain a user name or password.")
        text = f"{parts.scheme.lower()}://{(parts.hostname or '').lower()}{parts.path}"
    return text.lower()


def normalize(kind: str, value: str) -> Identifier:
    """Return the canonical identifier. Raises :class:`IdentifierError` with a readable message."""
    if kind not in KIND_CODES:
        raise IdentifierError(f"{kind!r} is not an identifier type.")
    raw = (value or "").strip()
    if not raw:
        raise IdentifierError("The identifier is empty.")
    if len(raw) > MAX_LENGTH:
        raise IdentifierError(f"The identifier is longer than {MAX_LENGTH} characters.")
    if any(ord(c) < 32 for c in raw):
        raise IdentifierError("The identifier contains control characters.")
    if kind == "ip":
        norm = _ip(raw)
    elif kind == "cidr":
        norm = _cidr(raw)
    elif kind in ("hostname", "domain"):
        norm = _dns(raw, "host name" if kind == "hostname" else "domain")
    elif kind == "url":
        norm = _url(raw)
    elif kind == "mac":
        norm = _mac(raw)
    elif kind == "repo":
        norm = _repo(raw)
    elif kind == "package":
        norm = re.sub(r"\s+", "", raw).lower()
    elif kind == "cloud_id":
        norm = raw  # ARNs and account IDs are case-sensitive
    else:
        norm = re.sub(r"\s+", " ", raw).casefold()
    return Identifier(kind=kind, value=raw, normalized=norm, match_key=f"{_FAMILY.get(kind, kind)}:{norm}")


def detect_kind(value: str) -> str:
    """Best guess of the kind of a free-text value. Used when a file has one column of mixed identifiers."""
    raw = (value or "").strip()
    if not raw:
        return "other"
    probes = (
        ("ip", _ip),
        ("cidr", _cidr) if "/" in raw and "://" not in raw else None,
        ("mac", _mac) if re.fullmatch(r"[0-9a-fA-F]{2}([:\-.]?[0-9a-fA-F]{2}){5}", raw) else None,
        ("url", _url) if "://" in raw and not raw.lower().startswith(("git@", "ssh://")) else None,
    )
    for probe in probes:
        if probe is None:
            continue
        try:
            probe[1](raw)
        except IdentifierError:
            continue
        return probe[0]
    if raw.lower().startswith("arn:"):
        return "cloud_id"
    if "." in raw or "/" not in raw:
        try:
            _dns(raw, "host name")
            return "hostname"
        except IdentifierError:
            pass
    return "other"


def parse(value: str, kind: str | None = None) -> Identifier:
    """Normalise ``value`` as ``kind``, or as the detected kind when none is given."""
    return normalize(kind or detect_kind(value), value)


_SPLIT_ALL = re.compile(r"[;\n\r|,]+")
_SPLIT_NO_COMMA = re.compile(r"[;\n\r|]+")


def split_cell(text: str, kind: str | None = None) -> list[str]:
    """Split a spreadsheet cell into values. Commas split too, except inside URLs where they are legal."""
    pattern = _SPLIT_NO_COMMA if kind == "url" or "://" in text else _SPLIT_ALL
    return [part.strip() for part in pattern.split(text or "") if part.strip()]
