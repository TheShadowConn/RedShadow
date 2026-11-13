"""CSV export of audit events. Cells that a spreadsheet could run as a formula are neutralised."""

import json

from apps.core.csvout import safe_cell, write_csv

MAX_ROWS = 50_000
COLUMNS = [
    "id", "occurred_at", "actor", "actor_ip", "action", "outcome", "entity_type", "entity_id", "entity_label",
    "engagement_ref", "request_id", "changes", "metadata",
]  # fmt: skip


def build_csv(events):
    """Write events to a temporary file. Returns (file object positioned at 0, sha256 hex, row count)."""
    rows = (
        (
            e.id, e.occurred_at.isoformat(), e.actor_label, e.actor_ip or "", e.action, e.outcome, e.entity_type,
            e.entity_id, e.entity_label, e.engagement_ref, e.request_id,
            json.dumps(e.changes, sort_keys=True, ensure_ascii=False),
            json.dumps(e.metadata, sort_keys=True, ensure_ascii=False),
        )
        for e in events.iterator(chunk_size=1000)
    )  # fmt: skip
    return write_csv(COLUMNS, rows)


__all__ = ["COLUMNS", "MAX_ROWS", "build_csv", "safe_cell"]
