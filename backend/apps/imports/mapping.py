"""Which finding fields a CSV column can fill, how columns are suggested, and what a mapping may contain."""

import re

from rest_framework.exceptions import ValidationError

from apps.findings.models import SEVERITIES

# key, label, hint
FIELDS = [
    ("title", "Title", "Required"),
    ("severity", "Severity", "Needed unless a CVSS vector is mapped"),
    ("cvss_vector", "CVSS vector", "Sets the score and the severity"),
    ("description", "Description", ""),
    ("recommendation", "Recommendation", ""),
    ("technical_details", "Technical details", ""),
    ("poc", "Proof of concept", ""),
    ("endpoint", "Endpoint", ""),
    ("asset", "Asset", "Asset name, IP address or URL, matched against the engagement's in-scope assets"),
    ("cwe", "CWE", "A number or CWE-79 style"),
    ("discovered_at", "Discovered date", "Use YYYY-MM-DD"),
    ("references", "References", "Links, optionally Label|URL, separated by semicolons or new lines"),
]
FIELD_KEYS = [k for k, _, _ in FIELDS]

ALIASES = {
    "title": ["title", "name", "finding", "finding title", "issue", "vulnerability", "summary"],
    "severity": ["severity", "risk", "risk level", "priority", "rating"],
    "cvss_vector": ["cvss vector", "cvss", "vector", "cvss v3 vector", "cvss v4 vector"],
    "description": ["description", "details", "detail", "synopsis"],
    "recommendation": ["recommendation", "solution", "remediation", "fix", "mitigation"],
    "technical_details": ["technical details", "technical", "technical description"],
    "poc": ["poc", "proof of concept", "proof", "steps to reproduce", "reproduction"],
    "endpoint": ["endpoint", "url", "path", "location", "affected url"],
    "asset": [
        "asset", "asset name", "host", "target", "hostname", "ip", "ip address", "asset ip",
        "affected asset", "affected host",
    ],  # fmt: skip
    "cwe": ["cwe", "cwe id", "cwe-id"],
    "discovered_at": ["discovered", "discovered at", "date", "found", "date found", "discovered date"],
    "references": ["references", "reference", "links", "urls"],
}

SEVERITY_ALIASES = {
    "informational": "info",
    "information": "info",
    "none": "info",
    "crit": "critical",
    "severe": "critical",
    "important": "high",
    "moderate": "medium",
    "med": "medium",
}
SEVERITY_KEYS = {k for k, _ in SEVERITIES}


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def suggest(headers: list[str]) -> dict[str, str]:
    """Best guess per field: the first header whose normalised name is a known alias. A header is used once."""
    by_norm = {}
    for h in headers:
        by_norm.setdefault(norm(h), h)
    out, used = {}, set()
    for field, names in ALIASES.items():
        for name in names:
            header = by_norm.get(norm(name))
            if header and header not in used:
                out[field], _ = header, used.add(header)
                break
    return out


def clean_mapping(headers: list[str], column_map: dict, value_map: dict) -> tuple[dict, dict]:
    """Check a mapping against the file's headers. Raises 400 with a message per problem."""
    problems = {}
    if not isinstance(column_map, dict) or not isinstance(value_map, dict):
        raise ValidationError({"mapping": ["Send column_map and value_map as objects."]})
    cleaned, seen = {}, {}
    for field, header in column_map.items():
        if field not in FIELD_KEYS:
            problems[field] = ["Unknown field."]
        elif header in ("", None):
            continue
        elif header not in headers:
            problems[field] = [f"The file has no column named {header!r}."]
        elif header in seen:
            problems[field] = [f"Column {header!r} is already used for {seen[header]}."]
        else:
            cleaned[field], seen[header] = header, field
    if "title" not in cleaned:
        problems.setdefault("title", ["Choose the column that holds the title."])
    if "severity" not in cleaned and "cvss_vector" not in cleaned:
        problems.setdefault("severity", ["Map a severity column or a CVSS vector column."])
    sev = {}
    for raw, key in (value_map.get("severity") or {}).items():
        if key not in SEVERITY_KEYS:
            problems["value_map"] = [f"{key!r} is not a severity."]
        else:
            sev[norm(raw)] = key
    if problems:
        raise ValidationError(problems)
    return cleaned, ({"severity": sev} if sev else {})
