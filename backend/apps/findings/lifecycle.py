"""Finding state machine: the single table of allowed status changes.

Pure data and lookups, no database access. ``services.transition`` is the only executor.
Each rule names the permissions that may perform it (any one is enough), the activity and audit
action it records, and what the caller must supply.
"""

from dataclasses import dataclass

STATUS_ORDER = (
    "draft", "open", "in_progress", "pending_verification", "reopened", "closed",
    "risk_accepted", "false_positive", "duplicate",
)  # fmt: skip

# Findings that can still be edited. The text is part of the report until it is closed.
EDITABLE_STATUSES = ("draft", "open", "in_progress", "reopened")
# Findings whose SLA clock is running (remediation has not been submitted yet).
OVERDUE_STATUSES = ("open", "in_progress", "reopened")
# Findings a team still has to act on (used by queues).
ACTIVE_STATUSES = ("open", "in_progress", "reopened", "pending_verification")


@dataclass(frozen=True)
class Rule:
    name: str  # audit action suffix: finding.<name>
    sources: tuple[str, ...]
    target: str
    perms: tuple[str, ...]  # any one is enough
    activity: str  # RemediationActivity.action
    note: str = ""  # "" none, "required" a written reason is required
    note_kind: str = ""  # also store the note as a FindingNote of this kind
    needs: tuple[str, ...] = ()  # extra inputs: expiry, duplicate_of


_WORKING = ("open", "in_progress", "reopened")
_REOPENABLE = ("closed", "risk_accepted", "false_positive", "duplicate")
_DUPLICABLE = ("draft", "open", "in_progress", "pending_verification", "reopened", "risk_accepted")

RULES: tuple[Rule, ...] = (
    Rule("published", ("draft",), "open", ("findings.publish",), "published"),
    Rule("started", ("open", "reopened"), "in_progress", ("remediation.update_status",), "started"),
    Rule("paused", ("in_progress",), "open", ("remediation.update_status",), "paused"),
    Rule("submitted_for_verification", _WORKING, "pending_verification", ("remediation.submit_verification",),
         "submitted_for_verification", note="required", note_kind="remediation"),
    Rule("verified", ("pending_verification",), "closed", ("findings.verify", "findings.close"),
         "verification_passed", note="required", note_kind="verification"),
    Rule("verification_failed", ("pending_verification",), "reopened", ("findings.verify",),
         "verification_failed", note="required", note_kind="verification"),
    Rule("closed", _WORKING, "closed", ("findings.close",), "closed", note="required", note_kind="verification"),
    Rule("risk_accepted", _WORKING, "risk_accepted", ("findings.risk_accept",), "risk_accepted",
         note="required", needs=("expiry",)),
    Rule("reopened", _REOPENABLE, "reopened", ("findings.reopen",), "reopened",
         note="required", note_kind="verification"),
    Rule("false_positive", ("draft", "open"), "false_positive", ("findings.update",), "false_positive",
         note="required"),
    Rule("duplicate", _DUPLICABLE, "duplicate", ("findings.duplicate",), "duplicate", needs=("duplicate_of",)),
)  # fmt: skip

_BY_MOVE = {(src, rule.target): rule for rule in RULES for src in rule.sources}
assert len(_BY_MOVE) == sum(len(r.sources) for r in RULES), "ambiguous transition table"

MIN_NOTE_LENGTH = 5


def find_rule(source: str, target: str) -> Rule | None:
    return _BY_MOVE.get((source, target))


def allowed(source: str, held) -> list[Rule]:
    """Rules out of ``source`` that a holder of the permission codes ``held`` may run."""
    return [r for r in RULES if source in r.sources and held.intersection(r.perms)]
