"""Findings per tag (department). Both inputs are already scoped to the caller, so nothing outside it is counted.

An asset with two tags counts in both rows. The total row counts every asset and finding once.
"""

from collections import Counter
from datetime import timedelta

from django.utils import timezone

from apps.findings import lifecycle
from apps.findings.models import SEVERITIES

from . import tags

DUE_SOON_DAYS = 7


def _blank(tag: str | None) -> dict:
    return {
        "tag": tag,
        "assets": 0,
        "open": 0,
        "open_by_severity": {k: 0 for k, _ in SEVERITIES},
        "overdue": 0,
        "due_soon": 0,
        "risk_accepted": 0,
    }


def overview(assets, findings) -> dict:
    """``assets``: the caller's assets (one organisation or all). ``findings``: the caller's findings on them."""
    today = timezone.localdate()
    soon = today + timedelta(days=DUE_SOON_DAYS)
    names = tags.spellings(assets)
    rows: dict[str | None, dict] = {key: _blank(name) for key, name in sorted(names.items())}
    rows[None] = _blank(None)  # untagged, including findings with no asset
    total = _blank(None)

    keys_of: dict = {}
    for pk, asset_tags, archived_at in assets.values_list("pk", "tags", "archived_at"):
        keys_of[pk] = {t.casefold() for t in asset_tags} or {None}
        if archived_at is None:
            total["assets"] += 1
            for key in keys_of[pk]:
                rows[key]["assets"] += 1

    seen: Counter = Counter()
    for asset_id, severity, status, due in findings.values_list("asset_id", "severity", "status", "due_date"):
        working = status in lifecycle.OVERDUE_STATUSES
        facts = []
        if status in lifecycle.ACTIVE_STATUSES:
            facts.append("open")
        if working and due and due < today:
            facts.append("overdue")
        if working and due and today <= due <= soon:
            facts.append("due_soon")
        if status == "risk_accepted":
            facts.append("risk_accepted")
        if not facts:
            continue
        for row in [total, *(rows[key] for key in keys_of.get(asset_id, {None}))]:
            for fact in facts:
                row[fact] += 1
            if "open" in facts:
                row["open_by_severity"][severity] += 1
        seen.update(facts)

    return {
        "rows": [r for key, r in rows.items() if key is not None or any((r["assets"], r["open"], r["risk_accepted"]))],
        "total": total,
        "open_statuses": list(lifecycle.ACTIVE_STATUSES),
    }
