"""Row validation. Mirrors the manual create path (`findings.services.create_finding`) so an imported
finding obeys the same rules as one typed in by hand."""

import datetime
import re
from urllib.parse import urlsplit

from apps.engagements.models import EngagementAsset
from apps.findings import cvss
from apps.findings.models import CWE
from apps.findings.services import dedupe_hash

from .mapping import SEVERITY_ALIASES, SEVERITY_KEYS, norm

TEXT_LIMIT = 50_000
TEXT_FIELDS = ("description", "recommendation", "technical_details", "poc")
MAX_REFERENCES = 20
CWE_RE = re.compile(r"^(?:cwe[\s-]*)?(\d{1,6})$", re.I)
DATE_RE = re.compile(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$")


# Problems that can be fixed later in the finding editor. A row whose only problems are these can still be imported as a
# draft marked for review ("everything" mode). Anything else (too long, too many values) cannot be stored.
SOFT_CODES = frozenset({
    "required", "invalid_severity", "invalid_cvss", "severity_mismatch", "unknown_asset", "unknown_cwe",
    "invalid_date", "invalid_reference",
})  # fmt: skip


def is_recoverable(errors: list) -> bool:
    return bool(errors) and all(e.get("code") in SOFT_CODES for e in errors)


def _err(errors: list, field: str, code: str, message: str) -> None:
    errors.append({"field": field, "code": code, "message": message})


def asset_key(text: str) -> str:
    """Match key for an asset cell: case-insensitive, trimmed, and tolerant of a trailing slash on URLs."""
    return text.strip().lower().rstrip("/")


class RowValidator:
    def __init__(self, engagement, headers: list[str], column_map: dict, value_map: dict):
        self.engagement = engagement
        self.index = {field: headers.index(h) for field, h in column_map.items()}
        self.width = len(headers)
        self.severity_map = {norm(k): v for k, v in (value_map.get("severity") or {}).items()}
        self.assets = {}
        links = EngagementAsset.objects.filter(engagement=engagement, in_scope=True).select_related("asset")
        for link in links.prefetch_related("asset__identifiers"):
            if link.asset.archived_at is None:
                self.assets.setdefault(asset_key(link.asset.name), link.asset.pk)
                if link.asset.identifier.strip():
                    self.assets.setdefault(asset_key(link.asset.identifier), link.asset.pk)
                for i in link.asset.identifiers.all():  # every identifier finds the asset, as typed or normalised
                    self.assets.setdefault(asset_key(i.value), link.asset.pk)
                    self.assets.setdefault(asset_key(i.normalized), link.asset.pk)
        self.cwes = set(CWE.objects.values_list("pk", flat=True)) if "cwe" in self.index else set()

    def cell(self, raw: list[str], field: str) -> str:
        i = self.index.get(field)
        return raw[i].strip() if i is not None and i < len(raw) else ""

    def validate(self, raw: list[str]) -> tuple[dict, list[dict]]:
        errors: list[dict] = []
        out: dict = {}
        if len(raw) > self.width and any(c.strip() for c in raw[self.width :]):
            _err(
                errors,
                "row",
                "too_many_values",
                f"The row has {len(raw)} values but the file has {self.width} columns.",
            )

        title = self.cell(raw, "title")
        if not title:
            _err(errors, "title", "required", "The title is empty.")
        elif len(title) > 200:
            _err(errors, "title", "too_long", "The title is longer than 200 characters.")
        out["title"] = title

        vector = self.cell(raw, "cvss_vector")
        severity = self.cell(raw, "severity")
        sev_key = None
        if severity:
            n = norm(severity)
            sev_key = self.severity_map.get(n) or SEVERITY_ALIASES.get(n, n)
            if sev_key not in SEVERITY_KEYS:
                _err(
                    errors,
                    "severity",
                    "invalid_severity",
                    f"{severity!r} is not a severity. Use critical, high, medium, low or info, or map it.",
                )
                sev_key = None
        if vector:
            try:
                version, score, derived = cvss.score_vector(vector)
            except cvss.InvalidVector as exc:
                _err(errors, "cvss_vector", "invalid_cvss", str(exc))
            else:
                if sev_key and sev_key != derived:
                    _err(
                        errors,
                        "severity",
                        "severity_mismatch",
                        f"Severity must be {derived} for a CVSS score of {score}.",
                    )
                out.update(cvss_vector=vector, severity=derived)
        if not vector and sev_key:
            out["severity"] = sev_key
        if "severity" not in out and not severity and not vector:
            _err(errors, "severity", "required", "Give a severity or a CVSS vector.")

        for field in TEXT_FIELDS:
            value = self.cell(raw, field)
            if len(value) > TEXT_LIMIT:
                _err(errors, field, "too_long", f"This text is longer than {TEXT_LIMIT:,} characters.")
            else:
                out[field] = value
        endpoint = self.cell(raw, "endpoint")
        if len(endpoint) > 500:
            _err(errors, "endpoint", "too_long", "The endpoint is longer than 500 characters.")
        out["endpoint"] = endpoint

        asset_text = self.cell(raw, "asset")
        out["asset_id"] = None
        if asset_text:
            found = self.assets.get(asset_key(asset_text))
            if found is None:
                _err(
                    errors,
                    "asset",
                    "unknown_asset",
                    f"No in-scope asset of this engagement has the name, IP address or URL {asset_text!r}. "
                    "A hostname or other identifier of the asset matches too.",
                )
            else:
                out["asset_id"] = str(found)

        cwe_text = self.cell(raw, "cwe")
        out["cwe_id"] = None
        if cwe_text:
            m = CWE_RE.match(cwe_text)
            if not m or int(m.group(1)) not in self.cwes:
                _err(errors, "cwe", "unknown_cwe", f"{cwe_text!r} is not in the CWE list.")
            else:
                out["cwe_id"] = int(m.group(1))

        date_text = self.cell(raw, "discovered_at")
        out["discovered_at"] = None
        if date_text:
            m = DATE_RE.match(date_text)
            try:
                out["discovered_at"] = (
                    datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat() if m else None
                )
            except ValueError:
                out["discovered_at"] = None
            if out["discovered_at"] is None:
                _err(errors, "discovered_at", "invalid_date", f"{date_text!r} is not a date. Use YYYY-MM-DD.")

        out["references"] = self._references(self.cell(raw, "references"), errors)
        out["dedupe_hash"] = dedupe_hash(self.engagement.pk, title, out["asset_id"], endpoint, out["cwe_id"])
        return out, errors

    @staticmethod
    def _references(text: str, errors: list) -> list[dict]:
        refs = []
        for part in [p.strip() for p in re.split(r"[;\n]+", text) if p.strip()]:
            label, _, url = part.partition("|") if "|" in part else ("", "", part)
            url = url.strip()
            parts = urlsplit(url)
            if parts.scheme not in ("http", "https") or not parts.netloc:
                _err(errors, "references", "invalid_reference", f"{url[:80]!r} is not a full http or https link.")
                continue
            refs.append({"label": (label.strip() or url)[:120], "url": url[:500]})
        if len(refs) > MAX_REFERENCES:
            _err(errors, "references", "too_many", f"At most {MAX_REFERENCES} references.")
            refs = refs[:MAX_REFERENCES]
        return refs
