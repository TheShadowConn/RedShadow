import hashlib
import ipaddress
import json
from dataclasses import dataclass
from datetime import UTC
from typing import Any

from django.db import connection, transaction
from django.utils import timezone

from apps.core.logs import request_id_var
from apps.core.net import client_ip

from .models import GENESIS_HASH, AuditEvent
from .redact import redact

_LOCK_KEY = 0x52534155  # serialises chain appends: advisory lock held to end of transaction
_HASHED_FIELDS = (
    "occurred_at", "actor_id", "actor_label", "actor_ip", "user_agent", "request_id", "action",
    "entity_type", "entity_id", "entity_label", "engagement_id", "engagement_ref", "changes",
    "metadata", "outcome", "prev_hash",
)  # fmt: skip


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def compute_hash(fields: dict) -> str:
    body = json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(body.encode()).hexdigest()


def _hash_input(event: AuditEvent) -> dict:
    data = {name: getattr(event, name) for name in _HASHED_FIELDS}
    data["occurred_at"] = event.occurred_at.astimezone(UTC).isoformat()
    for key in ("actor_id",):
        data[key] = str(data[key]) if data[key] else None
    data["engagement_id"] = str(data["engagement_id"]) if data["engagement_id"] else None
    data["actor_ip"] = str(data["actor_ip"]) if data["actor_ip"] else None
    return data


def record(
    action: str,
    *,
    request=None,
    actor=None,
    actor_label: str = "",
    entity: Any = None,
    entity_type: str = "",
    entity_id: str = "",
    entity_label: str = "",
    engagement: Any = None,
    changes: dict | None = None,
    metadata: dict | None = None,
    outcome: str = "success",
) -> AuditEvent:
    """Append one event to the chain, in the caller's transaction (same commit or rollback)."""
    if actor is None and request is not None:
        candidate = getattr(request, "user", None)
        if candidate is not None and getattr(candidate, "is_authenticated", False):
            actor = candidate
    if entity is not None:
        entity_type = entity_type or entity.__class__.__name__.lower()
        entity_id = entity_id or str(entity.pk)
        label = getattr(entity, "audit_label", None)
        entity_label = entity_label or (label() if callable(label) else str(entity))

    django_request = getattr(request, "_request", request)
    ip = None
    if request is not None:
        try:
            ip = str(ipaddress.ip_address(client_ip(request) or ""))
        except ValueError:
            ip = None
    ua = django_request.META.get("HTTP_USER_AGENT", "")[:255] if django_request is not None else ""

    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", [_LOCK_KEY])
        last = AuditEvent.objects.order_by("-id").values_list("hash", flat=True).first()
        event = AuditEvent(
            occurred_at=timezone.now(),
            actor_id=actor.pk if actor is not None else None,
            actor_label=(actor.email if actor is not None else actor_label)[:254],
            actor_ip=ip,
            user_agent=ua,
            request_id=request_id_var.get() if request_id_var.get() != "-" else "",
            action=action,
            entity_type=entity_type[:60],
            entity_id=str(entity_id)[:64],
            entity_label=entity_label[:255],
            engagement_id=engagement.pk if engagement is not None else None,
            engagement_ref=(getattr(engagement, "ref", "") if engagement is not None else "")[:40],
            changes=_json_safe(redact(changes or {})),
            metadata=_json_safe(redact(metadata or {})),
            outcome=outcome,
            prev_hash=last or GENESIS_HASH,
        )
        event.hash = compute_hash(_hash_input(event))
        event.save(force_insert=True)
    return event


@dataclass
class VerifyResult:
    ok: bool
    checked: int
    first_bad_id: int | None = None
    reason: str = ""


def verify_chain() -> VerifyResult:
    """Recompute every hash in order. Detects edits, deletions and reordering."""
    prev = GENESIS_HASH
    checked = 0
    for event in AuditEvent.objects.order_by("id").iterator(chunk_size=2000):
        if event.prev_hash != prev:
            return VerifyResult(False, checked, event.id, "chain link broken (event removed or reordered)")
        if compute_hash(_hash_input(event)) != event.hash:
            return VerifyResult(False, checked, event.id, "event content does not match its hash")
        prev = event.hash
        checked += 1
    return VerifyResult(True, checked)
