"""Turn scanner XML (Nessus, Burp, Nmap) into the same table a CSV upload gives, so that mapping, checking,
preview, duplicate detection and the import itself are shared with CSV.

The XML is untrusted: it is read with defusedxml, which refuses entity expansion and external references.
"""

import base64
import binascii
import io
import ipaddress
import re
from dataclasses import dataclass
from html import unescape
from urllib.parse import urlsplit

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import ParseError as XmlError
from defusedxml.ElementTree import iterparse

from apps.findings import cvss

from .parsing import MAX_ROWS, Parsed, ParseError

MAX_BYTES = 50 * 1024 * 1024
EXTENSIONS = {"nessus", "xml"}
TEXT_LIMIT = 40_000
TAG_RE = re.compile(r"<[^>]+>")
CWE_RE = re.compile(r"CWE-(\d{1,6})")

FINDING_HEADERS = [
    "Title", "Severity", "CVSS vector", "Description", "Recommendation", "Technical details", "Proof of concept",
    "Endpoint", "Asset", "CWE", "References",
]  # fmt: skip
ASSET_HEADERS = ["Name", "Asset type", "IP address", "Hostname", "URL", "Open ports"]

NESSUS_SEVERITY = {"0": "info", "1": "low", "2": "medium", "3": "high", "4": "critical"}
BURP_SEVERITY = {"information": "info", "info": "info", "low": "low", "medium": "medium", "high": "high"}


@dataclass
class Host:
    ip: str = ""
    name: str = ""
    url: str = ""
    ports: str = ""


def is_scan(data: bytes) -> bool:
    return data[:512].lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"<")


def parse(data: bytes, kind: str, *, include_info: bool = False, known_cwes: set[int] | None = None) -> Parsed:
    """``kind`` is "findings" or "assets". For assets, only the hosts of the scan are read."""
    if len(data) > MAX_BYTES:
        raise ParseError(f"The file is larger than {MAX_BYTES // (1024 * 1024)} MB.")
    try:
        root = _root_tag(data)
        if root == "NessusClientData_v2":
            findings, reader = _nessus, "nessus"
        elif root == "issues":
            findings, reader = _burp, "burp"
        elif root == "nmaprun":
            findings, reader = _nmap, "nmap"
        else:
            raise ParseError("This is not a Nessus (.nessus), Burp (XML issues) or Nmap (-oX) file.")
        if reader == "nmap" and kind != "assets":
            raise ParseError("Nmap results list hosts and ports, not vulnerabilities. Import this file as assets.")

        hosts: dict[tuple, Host] = {}
        rows: list[list[str]] = []
        for host, issue in findings(data):
            if host.ip or host.name or host.url:
                kept = hosts.setdefault((host.ip, host.name, host.url), host)
                kept.ports = kept.ports or host.ports
            if kind == "assets" or issue is None:
                continue
            if issue["severity"] == "info" and not include_info:
                continue
            rows.append(_finding_row(issue, known_cwes or set()))
            if len(rows) > MAX_ROWS:
                raise ParseError(f"The scan has more than {MAX_ROWS:,} results. Split it and import the parts.")
    except DefusedXmlException:
        raise ParseError("The file uses XML features that are not allowed (entities or external references).") from None
    except XmlError:
        raise ParseError("The file is not well-formed XML. Export it again from the scanner.") from None

    if kind == "assets":
        rows = [_asset_row(h) for h in hosts.values()]
        headers = ASSET_HEADERS
        if len(rows) > MAX_ROWS:
            raise ParseError(f"The scan has more than {MAX_ROWS:,} hosts. Split it and import the parts.")
        if not rows:
            raise ParseError("The scan names no hosts.")
    else:
        headers = FINDING_HEADERS
        if not rows:
            raise ParseError("The scan has no results to import. Informational results are left out unless you ask.")
    return Parsed(encoding="xml", delimiter="", headers=list(headers), rows=iter(enumerate(rows, 1)))


def _root_tag(data: bytes) -> str:
    for _, element in iterparse(io.BytesIO(data), events=("start",)):
        return element.tag
    raise ParseError("The file is empty.")


def _elements(data: bytes, tag: str):
    """Each finished element with that tag, freed after use so a large scan does not fill memory."""
    for _, element in iterparse(io.BytesIO(data), events=("end",)):
        if element.tag == tag:
            yield element
            element.clear()


def _is_ip(text: str) -> bool:
    try:
        ipaddress.ip_address(text)
    except ValueError:
        return False
    return True


def _text(element, name: str) -> str:
    return (element.findtext(name) or "").strip()


def _plain(html: str) -> str:
    """Burp writes HTML fragments. Keep the words and the line breaks."""
    text = re.sub(r"<\s*(br|/p|/li|/h\d|/div)\s*/?>", "\n", html, flags=re.I)
    text = unescape(TAG_RE.sub("", text))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _fenced(text: str) -> str:
    """Scanner output shown as it is, not read as Markdown."""
    text = text.replace("\x00", "").strip()  # a captured request body can hold bytes the database refuses
    if not text:
        return ""
    return "~~~~\n" + text[:TEXT_LIMIT].replace("~~~~", "~ ~ ~ ~") + "\n~~~~"


def _links(text: str) -> list[str]:
    found = []
    for part in re.findall(r"https?://[^\s\"'<>]+", text):
        url = part.rstrip(".,)")[:500]
        if urlsplit(url).netloc and url not in found:
            found.append(url)
    return found[:20]


def _nessus(data: bytes):
    for report_host in _elements(data, "ReportHost"):
        props = {t.get("name"): (t.text or "").strip() for t in report_host.iterfind("HostProperties/tag")}
        name = (report_host.get("name") or "").strip()
        ip = props.get("host-ip", "")
        if _is_ip(name):  # an address is never a hostname, or one machine could become two assets
            ip, name = ip or name, ""
        host = Host(ip=ip, name=props.get("host-fqdn", "") or name)
        yield host, None
        for item in report_host.iterfind("ReportItem"):
            port, protocol = item.get("port", "0"), item.get("protocol", "")
            address = host.name or host.ip
            vector = _text(item, "cvss3_vector")
            yield (
                host,
                {
                    "title": item.get("pluginName", "") or f"Nessus plugin {item.get('pluginID', '')}",
                    "severity": NESSUS_SEVERITY.get(item.get("severity", "0"), "info"),
                    "vector": vector.replace("CVSS:3.0/", "CVSS:3.1/", 1),
                    "description": _text(item, "description") or _text(item, "synopsis"),
                    "recommendation": _text(item, "solution"),
                    "technical": f"Nessus plugin {item.get('pluginID', '')}, port {port}/{protocol}.",
                    "poc": _fenced(_text(item, "plugin_output")),
                    "endpoint": f"{address}:{port}/{protocol}" if port != "0" else address,
                    "asset": [host.ip, host.name],
                    "cwe": _text(item, "cwe"),
                    "references": _links(_text(item, "see_also")),
                },
            )


def _burp(data: bytes):
    for item in _elements(data, "issue"):
        host_el = item.find("host")
        url = (host_el.text or "").strip() if host_el is not None else ""
        ip = (host_el.get("ip", "") if host_el is not None else "").strip()
        host = Host(ip=ip, name=urlsplit(url).hostname or "", url=url)
        if _is_ip(host.name):
            host.ip, host.name = host.ip or host.name, ""
        request = ""
        sent = item.find("requestresponse/request")
        if sent is not None and sent.text:
            request = sent.text
            if sent.get("base64") == "true":
                try:
                    request = base64.b64decode(request, validate=False).decode("utf-8", "replace")
                except (binascii.Error, ValueError):
                    request = ""
        path = _text(item, "path")
        cwe = CWE_RE.search(_text(item, "vulnerabilityClassifications"))
        yield (
            host,
            {
                "title": _text(item, "name"),
                "severity": BURP_SEVERITY.get(_text(item, "severity").lower(), "info"),
                "vector": "",
                "description": _plain(f"{_text(item, 'issueBackground')}\n\n{_text(item, 'issueDetail')}"),
                "recommendation": _plain(
                    f"{_text(item, 'remediationBackground')}\n\n{_text(item, 'remediationDetail')}"
                ),
                "technical": f"Burp confidence: {_text(item, 'confidence') or 'not stated'}.",
                "poc": _fenced(request),
                "endpoint": url.rstrip("/") + path,
                "asset": [url, ip],
                "cwe": cwe.group(1) if cwe else "",
                "references": _links(_text(item, "references")),
            },
        )


def _nmap(data: bytes):
    for item in _elements(data, "host"):
        status = item.find("status")
        if status is not None and status.get("state") != "up":
            continue
        ip = next((a.get("addr", "") for a in item.iterfind("address") if a.get("addrtype") in ("ipv4", "ipv6")), "")
        name = next((h.get("name", "") for h in item.iterfind("hostnames/hostname")), "")
        ports = [
            f"{p.get('portid')}/{p.get('protocol')}"
            for p in item.iterfind("ports/port")
            if (state := p.find("state")) is not None and state.get("state") == "open"
        ]
        yield Host(ip=ip, name=name, ports=", ".join(ports)[:2000]), None


def _finding_row(issue: dict, known_cwes: set[int]) -> list[str]:
    vector = issue["vector"][:200]
    if vector:
        try:
            cvss.score_vector(vector)
        except cvss.InvalidVector:
            vector = ""
    cwe = issue["cwe"] if issue["cwe"].isdigit() and int(issue["cwe"]) in known_cwes else ""
    return [
        issue["title"][:200],
        "" if vector else issue["severity"],  # the vector decides the severity, so the two cannot disagree
        vector,
        issue["description"][:TEXT_LIMIT],
        issue["recommendation"][:TEXT_LIMIT],
        issue["technical"],
        issue["poc"],
        issue["endpoint"][:500],
        "; ".join(a for a in dict.fromkeys(issue["asset"]) if a),
        f"CWE-{cwe}" if cwe else "",
        "\n".join(issue["references"]),
    ]


def _asset_row(host: Host) -> list[str]:
    name = (host.name or host.ip or host.url)[:160]
    kind = "web_app" if host.url else "host"
    return [name, kind, host.ip, host.name, host.url, host.ports]
