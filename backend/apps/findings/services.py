"""All finding writes: refs, field permissions, CVSS, lifecycle transitions, soft delete, bulk."""

import datetime
import functools
import hashlib
import re

from django.conf import settings
from django.db import transaction
from django.http import Http404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.audit import service as audit
from apps.core.changes import apply_changes
from apps.core.errors import Conflict
from apps.engagements.models import EngagementAsset
from apps.files.models import Attachment
from apps.rbac.authz import engagement_permissions, has_engagement_perm, user_permissions

from . import cvss, lifecycle
from .models import CWE, Finding, FindingCounter, FindingNote, FindingTemplate, RemediationActivity
from .selectors import scope_findings

CONTENT_FIELDS = (
    "title", "description", "technical_details", "poc", "recommendation", "references",
    "endpoint", "discovered_at",
)  # fmt: skip
TEXT_FIELDS = {"description", "technical_details", "poc", "recommendation"}
ASSIGN_FIELDS = ("assigned_pentester", "remediation_owner")
EDITABLE_STATUSES = lifecycle.EDITABLE_STATUSES
PUBLISH_REQUIRED = ("title", "description", "recommendation")
AUDIT_TEXT_LIMIT = 500


# refusals: audited after the transaction rolls back, tagged with the engagement


class _Refusal(Exception):
    def __init__(self, action: str, reason: str, finding: Finding):
        self.action, self.reason, self.finding = action, reason, finding


def _refuse(action: str, reason: str, finding: Finding) -> None:
    raise _Refusal(action, reason, finding)


def refusals_audited(func):
    @functools.wraps(func)
    def wrapper(request, *args, **kwargs):
        try:
            return func(request, *args, **kwargs)
        except _Refusal as r:
            audit.record(
                r.action, request=request, entity=r.finding, engagement=r.finding.engagement, outcome="denied",
                metadata={"reason": r.reason},
            )  # fmt: skip
            raise PermissionDenied(r.reason) from None

    return wrapper


# helpers


def next_ref() -> str:
    FindingCounter.objects.bulk_create([FindingCounter(id=1, last=0)], ignore_conflicts=True)
    counter = FindingCounter.objects.select_for_update().get(pk=1)
    counter.last += 1
    counter.save(update_fields=["last"])
    return f"RS-F-{counter.last:06d}"


def reserve_refs(count: int) -> list[str]:
    """Allocate ``count`` consecutive refs with one lock on the counter row. Call inside a transaction."""
    FindingCounter.objects.bulk_create([FindingCounter(id=1, last=0)], ignore_conflicts=True)
    counter = FindingCounter.objects.select_for_update().get(pk=1)
    first = counter.last + 1
    counter.last += count
    counter.save(update_fields=["last"])
    return [f"RS-F-{n:06d}" for n in range(first, first + count)]


def _norm(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def dedupe_hash(engagement_id, title, asset_id, endpoint, cwe_id) -> str:
    parts = [str(engagement_id), _norm(title), str(asset_id or ""), _norm(endpoint), str(cwe_id or "")]
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def _lock(finding: Finding) -> Finding:
    return Finding.objects.select_for_update(of=("self",)).select_related("engagement", "asset").get(pk=finding.pk)


def _assert_writable(f: Finding) -> None:
    if f.engagement.is_archived:
        raise Conflict("This engagement is archived. Unarchive it to make changes.")


def _check_version(f: Finding, version) -> None:
    if version is not None and f.version != version:
        raise Conflict("This finding was changed by someone else. Reload and try again.")


def _short(value):
    return value[:AUDIT_TEXT_LIMIT] + "…" if isinstance(value, str) and len(value) > AUDIT_TEXT_LIMIT else value


def _audit_changes(changes: dict) -> dict:
    return {k: [_short(v) for v in pair] for k, pair in changes.items()}


def _require(f: Finding, actor, code: str, action: str, reason: str = "You do not have permission to do this.") -> None:
    if not has_engagement_perm(actor, f.engagement_id, code):
        _refuse(action, reason, f)


def _from_template(template: FindingTemplate, data: dict) -> dict:
    """Template text fills what the caller left out. A caller-supplied vector or severity replaces both."""
    base = {"title": template.title, "description": template.description,
            "recommendation": template.recommendation, "references": template.references}  # fmt: skip
    if template.cwe_id:
        base["cwe_id"] = template.cwe_id
    if "cvss_vector" not in data and "severity" not in data:
        if template.cvss_vector:
            base["cvss_vector"] = template.cvss_vector
        elif template.severity:
            base["severity"] = template.severity
    return {**base, **data}


def _check_cwe(cwe_id):
    if cwe_id is None:
        return None
    cwe = CWE.objects.filter(pk=cwe_id).first()
    if cwe is None:
        raise ValidationError({"cwe_id": ["Unknown CWE. Choose one from the list."]})
    return cwe


def _check_asset(eng, asset) -> None:
    if asset is None:
        return
    if not EngagementAsset.objects.filter(engagement=eng, asset=asset, in_scope=True).exists():
        raise ValidationError({"asset": ["This asset is not in scope for the engagement."]})


def _check_assignee(eng, user, field: str) -> None:
    if user is None:
        return
    if not user.is_active:
        raise ValidationError({field: ["This user is deactivated."]})
    if "findings.view" not in engagement_permissions(user, eng.pk):
        raise ValidationError({field: ["This user cannot see findings on the engagement. Add them to the team first."]})


def _apply_cvss(data: dict) -> dict:
    """Derive version, score and severity from the vector. Returns fields to set."""
    vector = data.get("cvss_vector")
    out = {}
    if "cvss_vector" in data:
        if vector:
            try:
                version, score, severity = cvss.score_vector(vector)
            except cvss.InvalidVector as e:
                raise ValidationError({"cvss_vector": [str(e)]}) from None
            if data.get("severity") and data["severity"] != severity:
                raise ValidationError({"severity": [f"Severity must be {severity} for a CVSS score of {score}."]})
            out.update(cvss_vector=vector.strip(), cvss_version=version, cvss_score=score, severity=severity)
        else:
            out.update(cvss_vector="", cvss_version="", cvss_score=None)
            if "severity" in data:
                out["severity"] = data["severity"]
    elif "severity" in data:
        out["severity"] = data["severity"]
    return out


def _check_field_perms(actor, data: dict, content_code: str, eng) -> None:
    held = engagement_permissions(actor, eng.pk)
    bad = []
    if content_code not in held:
        bad += [k for k in data if k not in ASSIGN_FIELDS and k != "engagement"]
    if "findings.assign" not in held:
        bad += [k for k in data if k in ASSIGN_FIELDS]
    if bad:
        raise ValidationError({k: ["You cannot change this field."] for k in sorted(set(bad))})


# create / update


def create_finding(request, actor, eng, data: dict) -> Finding:
    if not has_engagement_perm(actor, eng.pk, "findings.create"):
        audit.record("finding.create_denied", request=request, entity=eng, engagement=eng, outcome="denied",
                     metadata={"reason": "missing findings.create"})  # fmt: skip
        raise PermissionDenied("You do not have permission to create findings.")
    data = {k: v for k, v in data.items() if k != "engagement"}
    _check_field_perms(actor, data, "findings.create", eng)
    if eng.is_archived:
        raise Conflict("This engagement is archived. Unarchive it to make changes.")
    template = data.pop("template", None)
    if template is not None:
        if "templates.view" not in user_permissions(actor):
            raise PermissionDenied("You do not have permission to use templates.")
        data = _from_template(template, data)
    if not (data.get("title") or "").strip():
        raise ValidationError({"title": ["This field is required."]})
    cwe = _check_cwe(data.pop("cwe_id", None))
    asset = data.get("asset")
    _check_asset(eng, asset)
    for field in ASSIGN_FIELDS:
        _check_assignee(eng, data.get(field), field)
    fields = _apply_cvss(data)
    if not fields.get("severity"):
        raise ValidationError({"severity": ["Choose a severity or provide a CVSS vector."]})
    with transaction.atomic():
        f = Finding.objects.create(
            ref=next_ref(), engagement=eng, reported_by=actor, cwe=cwe,
            discovered_at=data.get("discovered_at") or timezone.localdate(),
            dedupe_hash=dedupe_hash(eng.pk, data.get("title"), asset.pk if asset else None, data.get("endpoint"),
                                    cwe.pk if cwe else None),
            asset=asset, source="template" if template is not None else "manual",
            assigned_pentester=data.get("assigned_pentester"), remediation_owner=data.get("remediation_owner"),
            **{k: data[k] for k in CONTENT_FIELDS if k in data and k != "discovered_at"},
            **fields,
        )  # fmt: skip
        audit.record("finding.created", request=request, entity=f, engagement=eng,
                     metadata={"severity": f.severity, "cvss_score": str(f.cvss_score) if f.cvss_score else None,
                               "asset": asset.name if asset else None})  # fmt: skip
    return f


def _precheck_update(request, actor, f: Finding, data: dict) -> None:
    """Permission and field checks. Runs outside any transaction so the denial audit event persists."""
    eng = f.engagement
    only_assign = set(data) <= set(ASSIGN_FIELDS) and has_engagement_perm(actor, eng.pk, "findings.assign")
    if not has_engagement_perm(actor, eng.pk, "findings.update") and not only_assign:
        audit.record("finding.update_denied", request=request, entity=f, engagement=eng, outcome="denied",
                     metadata={"reason": "missing findings.update"})  # fmt: skip
        raise PermissionDenied("You do not have permission to edit this finding.")
    try:
        _check_field_perms(actor, data, "findings.update", eng)
    except ValidationError as e:
        audit.record("finding.update_denied", request=request, entity=f, engagement=eng, outcome="denied",
                     metadata={"fields": sorted(e.detail)})  # fmt: skip
        raise


def update_finding(request, actor, finding: Finding, data: dict, version) -> Finding:
    _precheck_update(request, actor, finding, data)
    with transaction.atomic():
        f = _lock(finding)
        eng = f.engagement
        _assert_writable(f)
        _check_version(f, version)
        if f.status not in EDITABLE_STATUSES:
            raise Conflict(f"A {f.get_status_display().lower()} finding cannot be edited.")
        if f.cvss_vector and "severity" in data and "cvss_vector" not in data and data["severity"] != f.severity:
            raise ValidationError({"severity": ["Severity follows the CVSS vector. Clear it to set severity by hand."]})
        changes = apply_changes(f, data, CONTENT_FIELDS)
        if "asset" in data and data["asset"] != f.asset:
            _check_asset(eng, data["asset"])
            changes["asset"] = [f.asset.name if f.asset else None, data["asset"].name if data["asset"] else None]
            f.asset = data["asset"]
        if "cwe_id" in data:
            cwe = _check_cwe(data["cwe_id"])
            if cwe != f.cwe:
                changes["cwe"] = [f.cwe_id, cwe.pk if cwe else None]
                f.cwe = cwe
        for field in ASSIGN_FIELDS:
            if field in data and data[field] != getattr(f, field):
                _check_assignee(eng, data[field], field)
                old = getattr(f, field)
                changes[field] = [old.email if old else None, data[field].email if data[field] else None]
                setattr(f, field, data[field])
        for key, value in _apply_cvss(data).items():
            if getattr(f, key) != value:
                changes[key] = [getattr(f, key), value]
                setattr(f, key, value)
        if "severity" in changes and f.due_date is not None:
            due = sla_due_date(f.severity, _published_on(f))  # the SLA follows the new severity
            changes["due_date"] = [f.due_date, due]
            f.due_date = due
            if due is None or due >= timezone.localdate():
                f.sla_breached_at = None  # a new deadline can be breached again
        if changes:
            f.dedupe_hash = dedupe_hash(eng.pk, f.title, f.asset_id, f.endpoint, f.cwe_id)
            f.version += 1
            f.save()
            audit.record("finding.updated", request=request, entity=f, engagement=eng, changes=_audit_changes(changes))
    return f


# lifecycle (rules live in lifecycle.py)


def sla_due_date(severity: str, start: datetime.date) -> datetime.date | None:
    days = settings.SLA_DAYS.get(severity)
    return start + datetime.timedelta(days=days) if days else None


def _published_on(f: Finding) -> datetime.date:
    first = f.activities.filter(action="published").order_by("created_at").first()
    return timezone.localdate(first.created_at) if first else timezone.localdate()


def _check_target(f: Finding, rule: lifecycle.Rule, note: str, expiry, duplicate_of) -> None:
    if rule.note and len(note.strip()) < lifecycle.MIN_NOTE_LENGTH:
        raise ValidationError({"note": [f"Write at least {lifecycle.MIN_NOTE_LENGTH} characters."]})
    if "expiry" in rule.needs:
        today = timezone.localdate()
        limit = today + datetime.timedelta(days=settings.RISK_ACCEPT_MAX_DAYS)
        if expiry is None:
            raise ValidationError({"risk_accepted_until": ["Required."]})
        if expiry <= today:
            raise ValidationError({"risk_accepted_until": ["Choose a date in the future."]})
        if expiry > limit:
            raise ValidationError(
                {"risk_accepted_until": [f"Risk can be accepted for at most {settings.RISK_ACCEPT_MAX_DAYS} days."]}
            )
    if "duplicate_of" in rule.needs:
        if duplicate_of is None:
            raise ValidationError({"duplicate_of": ["Required."]})
        if duplicate_of.pk == f.pk:
            raise ValidationError({"duplicate_of": ["A finding cannot be a duplicate of itself."]})
        if duplicate_of.engagement_id != f.engagement_id:
            raise ValidationError({"duplicate_of": ["The original must be in the same engagement."]})
        if duplicate_of.status == "duplicate":
            raise ValidationError({"duplicate_of": ["Point to the original finding, not another duplicate."]})
    if rule.name == "published":
        missing = {k: ["Required before publishing."] for k in PUBLISH_REQUIRED if not getattr(f, k).strip()}
        if missing:
            raise ValidationError(missing)


def _apply_target(f: Finding, rule: lifecycle.Rule, actor, note: str, expiry, duplicate_of, now) -> dict:
    """Set the fields a move changes. Returns {field: [old, new]} for the audit event."""
    before = {k: getattr(f, k) for k in _LIFECYCLE_FIELDS}
    target = rule.target
    if target in ("open", "reopened") and f.due_date is None:
        f.due_date = sla_due_date(f.severity, timezone.localdate(now))
    if target == "pending_verification":
        f.resolved_at = now
    if target == "closed":
        f.closed_at = now
        if rule.name == "verified":
            f.verified_at, f.verified_by = now, actor
    if target == "reopened":
        f.resolved_at = f.closed_at = f.verified_at = f.verified_by = None
        f.risk_accepted_until, f.risk_acceptance_reason = None, ""
        f.duplicate_of = None
    if target == "risk_accepted":
        f.risk_accepted_until, f.risk_acceptance_reason = expiry, note.strip()
    if target == "duplicate":
        f.duplicate_of = duplicate_of
    return {k: [_audit_value(v), _audit_value(getattr(f, k))] for k, v in before.items() if getattr(f, k) != v}


def _audit_value(value):
    return value.email if hasattr(value, "email") else (value.ref if hasattr(value, "ref") else value)


_LIFECYCLE_FIELDS = (
    "due_date", "resolved_at", "closed_at", "verified_at", "verified_by", "risk_accepted_until",
    "risk_acceptance_reason", "duplicate_of",
)  # fmt: skip


_DENIED_NAME = {"published": "publish"}  # keeps the audit action name used before the state machine


def _require_any(f: Finding, actor, codes, action: str) -> None:
    if not any(has_engagement_perm(actor, f.engagement_id, c) for c in codes):
        _refuse(action, "You do not have permission to do this.", f)


def _record_activity(f, actor, action, note="", from_status="", to_status="", evidence_ids=None):
    return RemediationActivity.objects.create(
        finding=f, actor=actor, action=action, note=note.strip(), from_status=from_status, to_status=to_status,
        evidence_ids=[str(i) for i in evidence_ids or []],
    )  # fmt: skip


@refusals_audited
def transition(
    request, actor, finding: Finding, target: str, version, note: str = "", expiry=None, duplicate_of=None,
    retest_item=None, evidence_ids=(),
):  # fmt: skip
    """Move a finding to ``target`` through the state machine, or refuse. One transaction:
    status change, note, timeline entry and audit event commit together.

    ``retest_item`` (set by retests.record_result) is settled in the same transaction."""
    with transaction.atomic():
        f = _lock(finding)
        rule = lifecycle.find_rule(f.status, target)
        _assert_writable(f)
        if rule is not None:
            _require_any(f, actor, rule.perms, f"finding.{_DENIED_NAME.get(rule.name, rule.name)}_denied")
        _check_version(f, version)
        if rule is None:
            raise Conflict(f"A {f.get_status_display().lower()} finding cannot be moved to {target.replace('_', ' ')}.")
        _check_target(f, rule, note, expiry, duplicate_of)
        _check_evidence(f, evidence_ids)
        return _execute(request, actor, f, rule, note, expiry, duplicate_of, retest_item, evidence_ids)


def _check_evidence(f: Finding, evidence_ids) -> None:
    if not evidence_ids:
        return
    valid = set(
        Attachment.objects.filter(finding=f, kind="evidence", deleted_at__isnull=True, pk__in=evidence_ids)
        .values_list("pk", flat=True)
    )  # fmt: skip
    if valid != set(evidence_ids):
        raise ValidationError({"evidence_ids": ["Choose evidence that belongs to this finding."]})


def _execute(request, actor, f, rule, note, expiry, duplicate_of, retest_item=None, evidence_ids=(), meta=None):
    """Apply a checked move. Caller holds the row lock inside a transaction. ``actor`` None = the system."""
    from . import retests  # late import: retests builds on this module

    old, target = f.status, rule.target
    f.status = target
    now = timezone.now()
    changes = {"status": [old, target], **_apply_target(f, rule, actor, note, expiry, duplicate_of, now)}
    f.version += 1
    f.save()
    meta = dict(meta or {})
    if rule.note:
        meta["reason"] = _short(note.strip())
        if rule.note_kind and actor is not None:
            meta["note_id"] = str(
                FindingNote.objects.create(finding=f, author=actor, kind=rule.note_kind, body=note.strip()).pk
            )
    if duplicate_of is not None:
        meta["duplicate_of"] = duplicate_of.ref
    if old == "pending_verification":
        meta.update(retests.settle(request, f, actor, rule, note, evidence_ids, retest_item, now))
    _record_activity(f, actor, rule.activity, note, old, target, evidence_ids)
    audit.record(f"finding.{rule.name}", request=request, actor_label="" if actor else "system", entity=f,
                 engagement=f.engagement, changes=_audit_changes(changes), metadata=meta)  # fmt: skip
    return f


def system_reopen_expired_risk(finding: Finding) -> bool:
    """Beat task entry: reopen one risk-accepted finding whose acceptance has expired. Idempotent."""
    with transaction.atomic():
        f = _lock(finding)
        until = f.risk_accepted_until
        if f.status != "risk_accepted" or until is None or until >= timezone.localdate() or f.engagement.is_archived:
            return False
        rule = lifecycle.find_rule("risk_accepted", "reopened")
        note = f"Risk acceptance expired on {until.isoformat()}."
        _execute(None, None, f, rule, note, None, None, meta={"trigger": "risk_acceptance_expired"})
        return True


def system_flag_sla_breach(finding: Finding) -> bool:
    """Beat task entry: record the first SLA breach of one finding. Idempotent."""
    with transaction.atomic():
        f = _lock(finding)
        today = timezone.localdate()
        if (f.sla_breached_at or f.due_date is None or f.due_date >= today
                or f.status not in lifecycle.OVERDUE_STATUSES):  # fmt: skip
            return False
        f.sla_breached_at = timezone.now()
        f.save(update_fields=["sla_breached_at", "updated_at"])
        _record_activity(f, None, "sla_breached", f"Due {f.due_date.isoformat()}, still {f.status.replace('_', ' ')}.",
                         f.status, f.status)  # fmt: skip
        audit.record("finding.sla_breached", actor_label="system", entity=f, engagement=f.engagement,
                     metadata={"due_date": f.due_date.isoformat(), "severity": f.severity,
                               "status": f.status})  # fmt: skip
        return True


def publish_finding(request, actor, finding: Finding, version) -> Finding:
    return transition(request, actor, finding, "open", version)


def mark_false_positive(request, actor, finding: Finding, reason: str, version) -> Finding:
    return transition(request, actor, finding, "false_positive", version, note=reason)


def mark_duplicate(request, actor, finding: Finding, target: Finding, version) -> Finding:
    return transition(request, actor, finding, "duplicate", version, duplicate_of=target)


# timeline entries that do not change the status

ACTIVITY_PERMISSION = {
    "fix_deployed": "remediation.update_status",
    "mitigated": "remediation.update_status",
    "comment": "finding_notes.remediation",
}


@refusals_audited
def add_activity(request, actor, finding: Finding, action: str, note: str, evidence_ids) -> RemediationActivity:
    with transaction.atomic():
        f = _lock(finding)
        _require(f, actor, ACTIVITY_PERMISSION[action], "finding.activity_denied")
        _assert_writable(f)
        if f.status == "draft":
            raise Conflict("Timeline entries can be added once the finding is published.")
        if action != "comment" and f.status not in lifecycle.OVERDUE_STATUSES:
            raise Conflict("This update only applies while the finding is being remediated.")
        _check_evidence(f, evidence_ids)
        entry = _record_activity(f, actor, action, note, f.status, f.status, evidence_ids)
        audit.record("finding.activity_added", request=request, entity=f, engagement=f.engagement,
                     metadata={"action": action, "activity_id": str(entry.pk), "length": len(note)})  # fmt: skip
    return entry


@refusals_audited
def delete_finding(request, actor, finding: Finding) -> None:
    with transaction.atomic():
        f = _lock(finding)
        _require(f, actor, "findings.delete", "finding.delete_denied")
        _assert_writable(f)
        if f.duplicates.filter(deleted_at__isnull=True).exists():
            raise Conflict("Other findings are marked as duplicates of this one. Resolve them first.")
        f.soft_delete()
        audit.record("finding.deleted", request=request, entity=f, engagement=f.engagement)


# bulk

BULK_ACTIONS = ("publish", "assign", "delete")
BULK_LIMIT = 100


def bulk_apply(request, actor, ids: list, action: str, params: dict) -> list[dict]:
    """Run one action over many findings. Each item is authorised and committed on its own;
    failures are reported per item and never abort the others."""
    visible = {f.pk: f for f in scope_findings(actor).select_related("engagement").filter(pk__in=ids)}
    results = []
    for fid in ids:
        item = {"id": str(fid), "ok": False, "error": None}
        f = visible.get(fid)
        try:
            if f is None:
                raise Http404
            if not has_engagement_perm(actor, f.engagement_id, "findings.bulk_update"):
                audit.record("finding.bulk_denied", request=request, entity=f, engagement=f.engagement,
                             outcome="denied", metadata={"action": action})  # fmt: skip
                raise PermissionDenied("You do not have permission for bulk updates here.")
            if action == "publish":
                publish_finding(request, actor, f, None)
            elif action == "assign":
                update_finding(request, actor, f, params, None)
            else:
                delete_finding(request, actor, f)
            item["ok"] = True
        except Http404:
            item["error"] = {"code": "not_found", "message": "Not found."}
        except PermissionDenied as e:
            item["error"] = {"code": "forbidden", "message": str(e.detail)}
        except Conflict as e:
            item["error"] = {"code": "conflict", "message": str(e.detail)}
        except ValidationError as e:
            item["error"] = {"code": "invalid", "message": _flatten(e.detail)}
        results.append(item)
    return results


def _flatten(detail) -> str:
    if isinstance(detail, dict):
        return " ".join(f"{k}: {_flatten(v)}" for k, v in detail.items())
    if isinstance(detail, list):
        return " ".join(_flatten(v) for v in detail)
    return str(detail)


# notes (append-only)

NOTE_PERMISSION = {"technical": "finding_notes.technical", "remediation": "finding_notes.remediation"}


@refusals_audited
def add_note(request, actor, finding: Finding, kind: str, body: str) -> FindingNote:
    with transaction.atomic():
        f = _lock(finding)
        _require(f, actor, NOTE_PERMISSION[kind], "finding.note_denied", "You cannot add this kind of note.")
        _assert_writable(f)
        if kind == "remediation" and f.status == "draft":
            raise Conflict("Remediation notes can be added once the finding is published.")
        note = FindingNote.objects.create(finding=f, author=actor, kind=kind, body=body)
        audit.record(f"finding.{kind}_note_added", request=request, entity=f, engagement=f.engagement,
                     metadata={"note_id": str(note.pk), "length": len(body)})  # fmt: skip
    return note
