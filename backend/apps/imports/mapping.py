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
        "asset",
        "asset name",
        "host",
        "target",
        "hostname",
        "ip",
        "ip address",
        "asset ip",
        "affected asset",
        "affected host",
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


def suggest(headers: list[str], aliases: dict | None = None) -> dict[str, str]:
    """Best guess per field: the first header whose normalised name is a known alias. A header is used once."""
    by_norm = {}
    for h in headers:
        by_norm.setdefault(norm(h), h)
    out, used = {}, set()
    for field, names in (aliases or ALIASES).items():
        for name in names:
            header = by_norm.get(norm(name))
            if header and header not in used:
                out[field], _ = header, used.add(header)
                break
    return out


# Asset imports: which asset fields a column can fill. The identifier columns can each hold several
# values in one cell (separated by ; or | or a new line).
ASSET_FIELDS = [
    ("name", "Name", "Optional: the first identifier is used when empty"),
    ("type", "Asset type", "Optional: guessed from the identifiers when empty"),
    ("environment", "Environment", "prod, staging or dev. Empty means production"),
    ("criticality", "Criticality", "1 to 5, or low, medium, high, critical. Empty means 3"),
    ("tags", "Tags", "Separated by semicolons"),
    ("ip", "IP address", "One or more per cell"),
    ("hostname", "Hostname", "One or more per cell"),
    ("domain", "Domain", "One or more per cell"),
    ("url", "URL", "Full URLs, one or more per cell"),
    ("mac", "MAC address", ""),
    ("cloud_id", "Cloud resource ID", "ARN, account or subscription ID"),
    ("repo", "Repository", ""),
    ("identifiers", "Other identifiers", "Mixed values: the type of each is detected"),
]
ASSET_FIELD_KEYS = [k for k, _, _ in ASSET_FIELDS]
ASSET_IDENTIFIER_FIELDS = ("ip", "hostname", "domain", "url", "mac", "cloud_id", "repo", "identifiers")
ASSET_ALIASES = {
    "name": ["name", "asset", "asset name", "title", "system", "system name"],
    "type": ["type", "asset type", "category", "kind"],
    "environment": ["environment", "env", "stage"],
    "criticality": ["criticality", "priority", "importance", "business criticality", "tier"],
    "tags": ["tags", "labels", "tag"],
    "ip": ["ip", "ip address", "ipv4", "ipv6", "address", "ips", "ip addresses"],
    "hostname": ["hostname", "host", "host name", "fqdn", "dns name", "server", "hostnames"],
    "domain": ["domain", "domain name", "domains"],
    "url": ["url", "uri", "link", "website", "web address", "urls"],
    "mac": ["mac", "mac address"],
    "cloud_id": ["cloud id", "arn", "resource id", "account id", "cloud resource", "subscription id"],
    "repo": ["repo", "repository", "git", "repo url"],
    "identifiers": ["identifiers", "identifier", "ids", "other identifiers", "aliases"],
}


def suggest_assets(headers: list[str]) -> dict[str, str]:
    return suggest(headers, ASSET_ALIASES)


def clean_asset_mapping(headers: list[str], column_map: dict, value_map: dict) -> tuple[dict, dict]:
    problems = {}
    if not isinstance(column_map, dict) or not isinstance(value_map, dict):
        raise ValidationError({"mapping": ["Send column_map and value_map as objects."]})
    cleaned, seen = {}, {}
    for field, header in column_map.items():
        if field not in ASSET_FIELD_KEYS:
            problems[field] = ["Unknown field."]
        elif header in ("", None):
            continue
        elif header not in headers:
            problems[field] = [f"The file has no column named {header!r}."]
        elif header in seen:
            problems[field] = [f"Column {header!r} is already used for {seen[header]}."]
        else:
            cleaned[field], seen[header] = header, field
    if not any(f in cleaned for f in ASSET_IDENTIFIER_FIELDS):
        problems.setdefault(
            "identifiers", ["Map at least one column that identifies the asset: IP, hostname, domain, URL ..."]
        )
    if problems:
        raise ValidationError(problems)
    return cleaned, {}


def clean_mapping(headers: list[str], column_map: dict, value_map: dict, kind: str = "findings") -> tuple[dict, dict]:
    """Check a mapping against the file's headers. Raises 400 with a message per problem."""
    if kind == "assets":
        return clean_asset_mapping(headers, column_map, value_map)
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
