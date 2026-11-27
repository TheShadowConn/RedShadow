"""Asset CSV import: row validation, identifier matching and the commit.

A row describes one asset by one or more identifiers. Rows are matched to existing assets by identifier,
never by name, so the same asset can never be created twice under different identifiers:

* no identifier is known            -> create an asset that is *not onboarded* yet
* every known identifier is one asset -> add the identifiers it lacks to that asset (or skip as a duplicate)
* identifiers of two different assets  -> error: the file contradicts the data, nothing is guessed

Rows of one file also match each other: a row that shares an identifier with an earlier row is folded into
the same asset. The check (preview) and the commit use the same `Matcher`.
"""

from dataclasses import dataclass, field

from apps.organisations import assets as asset_ops
from apps.organisations import identifiers as ident
from apps.organisations.models import Asset

from .mapping import ASSET_IDENTIFIER_FIELDS, norm

NAME_LIMIT = 160
MAX_TAGS = 20
TYPE_BY_KIND = {
    "url": "web_app",
    "domain": "web_app",
    "cidr": "network_range",
    "ip": "host",
    "hostname": "host",
    "mac": "host",
    "repo": "source_repo",
    "cloud_id": "cloud_account",
    "package": "mobile_app",
}
ENV_ALIASES = {
    "prod": "prod", "production": "prod", "live": "prod",
    "staging": "staging", "stage": "staging", "uat": "staging", "preprod": "staging", "pre prod": "staging",
    "dev": "dev", "development": "dev", "test": "dev", "testing": "dev", "qa": "dev",
}  # fmt: skip
CRITICALITY_WORDS = {"low": 2, "medium": 3, "moderate": 3, "high": 4, "critical": 5, "very high": 5, "very low": 1}


def _err(errors: list, field_name: str, code: str, message: str) -> None:
    errors.append({"field": field_name, "code": code, "message": message})


class AssetRowValidator:
    """Turns one CSV row into the asset it describes. Does not touch the database."""

    def __init__(self, headers: list[str], column_map: dict):
        self.index = {f: headers.index(h) for f, h in column_map.items()}
        self.width = len(headers)
        self.types = {norm(k): k for k, _ in Asset.TYPES} | {norm(v): k for k, v in Asset.TYPES}

    def cell(self, raw: list[str], name: str) -> str:
        i = self.index.get(name)
        return raw[i].strip() if i is not None and i < len(raw) else ""

    def validate(self, raw: list[str]) -> tuple[dict, list[dict]]:
        errors: list[dict] = []
        if len(raw) > self.width and any(c.strip() for c in raw[self.width :]):
            _err(
                errors,
                "row",
                "too_many_values",
                f"The row has {len(raw)} values but the file has {self.width} columns.",
            )
        items: list[dict] = []
        for column in ASSET_IDENTIFIER_FIELDS:
            kind = None if column == "identifiers" else column
            for value in ident.split_cell(self.cell(raw, column), kind):
                items.append({"kind": kind, "value": value})
        parsed: list[ident.Identifier] = []
        seen = set()
        for item in items:
            try:
                p = ident.parse(item["value"], item["kind"])
            except ident.IdentifierError as exc:
                _err(errors, item["kind"] or "identifiers", "invalid_identifier", str(exc))
                continue
            if p.match_key not in seen:
                seen.add(p.match_key)
                parsed.append(p)
        if not items and not errors:
            _err(errors, "identifiers", "required", "The row has no identifier (IP, hostname, domain, URL ...).")
        elif not parsed and not errors:
            _err(errors, "identifiers", "required", "The row has no usable identifier.")

        name = self.cell(raw, "name") or (parsed[0].value if parsed else "")
        if len(name) > NAME_LIMIT:
            _err(errors, "name", "too_long", f"The name is longer than {NAME_LIMIT} characters.")
        out: dict = {"name": name, "identifiers": [p.as_dict() for p in parsed]}

        type_text = self.cell(raw, "type")
        if type_text:
            out["type"] = self.types.get(norm(type_text))
            if out["type"] is None:
                _err(errors, "type", "invalid_type", f"{type_text!r} is not an asset type.")
        else:
            out["type"] = TYPE_BY_KIND.get(parsed[0].kind, "other") if parsed else "other"

        env = self.cell(raw, "environment")
        out["environment"] = "prod"
        if env:
            out["environment"] = ENV_ALIASES.get(norm(env))
            if out["environment"] is None:
                _err(
                    errors,
                    "environment",
                    "invalid_environment",
                    f"{env!r} is not an environment. Use prod, staging or dev.",
                )

        crit = self.cell(raw, "criticality")
        out["criticality"] = 3
        if crit:
            if crit.isdigit() and 1 <= int(crit) <= 5:
                out["criticality"] = int(crit)
            elif norm(crit) in CRITICALITY_WORDS:
                out["criticality"] = CRITICALITY_WORDS[norm(crit)]
            else:
                _err(
                    errors,
                    "criticality",
                    "invalid_criticality",
                    f"{crit!r} is not 1 to 5, low, medium, high or critical.",
                )

        tags = [t for t in ident.split_cell(self.cell(raw, "tags")) if t]
        if len(tags) > MAX_TAGS or any(len(t) > 40 for t in tags):
            _err(errors, "tags", "invalid_tags", f"Use at most {MAX_TAGS} tags of 40 characters.")
            tags = []
        out["tags"] = list({t.casefold(): t for t in reversed(tags)}.values())[::-1]
        return out, errors


@dataclass
class Outcome:
    action: str  # create | merge | merge_in_file | known | known_in_file | conflict | archived
    asset_id: str | None = None
    asset_name: str = ""
    new_keys: list[str] = field(default_factory=list)
    target_line: int | None = None
    message: str = ""


class Matcher:
    """Matches rows to assets. ``db`` is match_key -> (asset_id, name, archived); ``overlay`` holds the
    identifiers of assets that earlier rows of the same file will create (match_key -> first line)."""

    def __init__(self, organisation_id):
        self.org_id = organisation_id
        self.db: dict[str, tuple[str, str, bool]] = {}
        self.overlay: dict[str, int] = {}

    def preload(self, keys) -> None:
        missing = [k for k in set(keys) if k not in self.db]
        for key, row in asset_ops.owners(self.org_id, missing).items():
            self.db[key] = (str(row.asset_id), row.asset.name, row.asset.archived_at is not None)

    def resolve(self, identifiers: list[dict], line: int) -> Outcome:
        keys = [i["match_key"] for i in identifiers]
        db_hits = {self.db[k][0]: self.db[k] for k in keys if k in self.db}
        rows_hit = {self.overlay[k] for k in keys if k in self.overlay}
        groups = len(db_hits) + len(rows_hit)
        if groups > 1:
            names = [f"{v[1]!r}" for v in db_hits.values()] + [f"the asset of line {n}" for n in sorted(rows_hit)]
            return Outcome(
                "conflict",
                message="These identifiers belong to different assets: "
                + ", ".join(names)
                + ". Merge them first, or split the row.",
            )
        if db_hits:
            asset_id, name, archived = next(iter(db_hits.values()))
            if archived:
                return Outcome(
                    "archived",
                    asset_id,
                    name,
                    message=f"These identifiers belong to the archived asset {name!r}. Unarchive it first.",
                )
            new = [k for k in keys if k not in self.db]
            for k in new:
                self.db[k] = (asset_id, name, False)
            return Outcome("merge" if new else "known", asset_id, name, new)
        if rows_hit:
            first = next(iter(rows_hit))
            new = [k for k in keys if k not in self.overlay]
            for k in new:
                self.overlay[k] = first
            return Outcome("merge_in_file" if new else "known_in_file", new_keys=new, target_line=first)
        for k in keys:
            self.overlay[k] = line
        return Outcome("create", new_keys=list(keys))


def describe(outcome: Outcome, mapped: dict) -> tuple[str, dict]:
    """The row status and the details stored on the row for an outcome."""
    mapped = {**mapped, "action": outcome.action}
    if outcome.asset_id:
        mapped.update(asset_id=outcome.asset_id, asset_name=outcome.asset_name)
    if outcome.target_line:
        mapped["target_line"] = outcome.target_line
    mapped["new_identifiers"] = len(outcome.new_keys)
    if outcome.action in ("known", "known_in_file"):
        return "duplicate", mapped
    return "valid", mapped
