"""Retest rounds: a batch of findings in pending verification, assigned to one assessor.

Recording a result runs the finding state machine (passed closes, failed reopens), so the round
never disagrees with the findings. Only the assigned assessor can record results.
"""

from django.db import transaction
from django.http import Http404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import User
from apps.audit import service as audit
from apps.core.errors import Conflict
from apps.engagements.models import Engagement
from apps.rbac.authz import engagement_permissions, has_engagement_perm

from . import services
from .models import Finding, RetestItem, RetestRound
from .selectors import scope_findings

MAX_ITEMS = 100


def _deny(request, action: str, rnd, reason: str):
    audit.record(action, request=request, entity=rnd, engagement=rnd.engagement, outcome="denied",
                 metadata={"reason": reason})  # fmt: skip
    raise PermissionDenied(reason)


def _check_assessor(eng, user) -> None:
    if not user.is_active:
        raise ValidationError({"assessor": ["This user is deactivated."]})
    held = engagement_permissions(user, eng.pk)
    if not {"retests.record", "findings.verify"} <= held:
        raise ValidationError({"assessor": ["This user cannot record retest results on the engagement."]})


def _can_manage(actor, rnd) -> bool:
    return actor.pk == rnd.requested_by_id or has_engagement_perm(actor, rnd.engagement_id, "retests.manage")


def _lock_round(rnd: RetestRound) -> RetestRound:
    return RetestRound.objects.select_for_update(of=("self",)).select_related("engagement", "assessor").get(pk=rnd.pk)


# create


def create_round(request, actor, eng: Engagement, assessor, finding_ids: list, note: str = "") -> RetestRound:
    if not has_engagement_perm(actor, eng.pk, "retests.create"):
        audit.record("retest_round.create_denied", request=request, entity=eng, engagement=eng, outcome="denied",
                     metadata={"reason": "missing retests.create"})  # fmt: skip
        raise PermissionDenied("You do not have permission to request retests.")
    _check_assessor(eng, assessor)
    ids = list(dict.fromkeys(finding_ids))
    if not ids or len(ids) > MAX_ITEMS:
        raise ValidationError({"findings": [f"Choose between 1 and {MAX_ITEMS} findings."]})
    with transaction.atomic():
        engagement = Engagement.objects.select_for_update().get(pk=eng.pk)  # serialises round numbers
        if engagement.is_archived:
            raise Conflict("This engagement is archived. Unarchive it to make changes.")
        visible = set(scope_findings(actor).filter(engagement=engagement, pk__in=ids).values_list("pk", flat=True))
        if visible != set(ids):
            raise ValidationError({"findings": ["One or more findings were not found in this engagement."]})
        findings = list(Finding.objects.select_for_update().filter(pk__in=ids).order_by("pk"))
        wrong = [f.ref for f in findings if f.status != "pending_verification"]
        if wrong:
            raise ValidationError(
                {"findings": [f"Only findings pending verification can be retested: {', '.join(wrong)}."]}
            )
        busy = RetestItem.objects.filter(finding__in=findings, result="pending", round__status__in=RetestRound.ACTIVE)
        if busy.exists():
            refs = sorted({i.finding.ref for i in busy.select_related("finding")})
            raise Conflict(f"Already in an open retest round: {', '.join(refs)}.")
        last = RetestRound.objects.filter(engagement=engagement).order_by("-number").values_list("number", flat=True)
        rnd = RetestRound.objects.create(
            engagement=engagement, number=(last.first() or 0) + 1, requested_by=actor, assessor=assessor,
            note=note.strip(),
        )  # fmt: skip
        RetestItem.objects.bulk_create([RetestItem(round=rnd, finding=f) for f in findings])
        for f in findings:
            text = f"Retest {rnd.ref} assigned to {assessor.display_name}."
            services._record_activity(f, actor, "retest_requested", text, f.status, f.status)
        audit.record("retest_round.created", request=request, entity=rnd, engagement=engagement,
                     metadata={"assessor": assessor.email, "findings": [f.ref for f in findings]})  # fmt: skip
    return rnd


# assign and cancel


def assign_round(request, actor, rnd: RetestRound, assessor: User, version) -> RetestRound:
    if not _can_manage(actor, rnd):
        _deny(request, "retest_round.assign_denied", rnd, "Only the requester or an administrator can reassign.")
    with transaction.atomic():
        r = _lock_round(rnd)
        _check_version(r, version)
        if r.status not in RetestRound.ACTIVE:
            raise Conflict("Only an open retest round can be reassigned.")
        _check_assessor(r.engagement, assessor)
        old, r.assessor = r.assessor, assessor
        r.version += 1
        r.save()
        audit.record("retest_round.assigned", request=request, entity=r, engagement=r.engagement,
                     changes={"assessor": [old.email, assessor.email]})  # fmt: skip
    return r


def cancel_round(request, actor, rnd: RetestRound, version) -> RetestRound:
    if not _can_manage(actor, rnd):
        _deny(request, "retest_round.cancel_denied", rnd, "Only the requester or an administrator can cancel.")
    with transaction.atomic():
        r = _lock_round(rnd)
        _check_version(r, version)
        if r.status not in RetestRound.ACTIVE:
            raise Conflict("Only an open retest round can be cancelled.")
        now = timezone.now()
        r.items.filter(result="pending").update(result="not_tested", note="Round cancelled.", updated_at=now)
        r.status, r.completed_at = "cancelled", now
        r.version += 1
        r.save()
        audit.record("retest_round.cancelled", request=request, entity=r, engagement=r.engagement)
    return r


def _check_version(r: RetestRound, version) -> None:
    if version is not None and r.version != version:
        raise Conflict("This retest round was changed by someone else. Reload and try again.")


# results


def record_result(request, actor, rnd: RetestRound, item: RetestItem, result: str, note: str, evidence_ids, version):
    """Passed closes the finding, failed reopens it. Only the assigned assessor may call this."""
    if actor.pk != rnd.assessor_id or not has_engagement_perm(actor, rnd.engagement_id, "retests.record"):
        _deny(request, "retest_round.result_denied", rnd, "Only the assigned assessor can record results.")
    if item.round_id != rnd.pk:
        raise Http404
    finding = scope_findings(actor).filter(pk=item.finding_id).first()
    if finding is None:
        raise Http404
    if rnd.status not in RetestRound.ACTIVE or item.result != "pending":
        raise Conflict("This retest item is no longer open.")
    return services.transition(
        request, actor, finding, "closed" if result == "passed" else "reopened", version, note=note,
        retest_item=item, evidence_ids=list(evidence_ids),
    )  # fmt: skip


def settle(request, f: Finding, actor, rule, note: str, evidence_ids, recorded: RetestItem | None, now) -> dict:
    """Called by the state machine when ``f`` leaves pending_verification, inside its transaction.

    The recorded item gets its result; any other pending item of the finding becomes not_tested
    (the finding was moved by hand). Rounds with nothing pending complete. Returns audit metadata."""
    items = list(
        RetestItem.objects.select_for_update(of=("self",))
        .select_related("round__engagement")
        .filter(finding=f, result="pending", round__status__in=RetestRound.ACTIVE)
        .order_by("pk")
    )
    if recorded is not None and recorded.pk not in {i.pk for i in items}:
        raise Conflict("This retest item is no longer open.")
    meta, rounds = {}, {}
    for item in items:
        if recorded is not None and item.pk == recorded.pk:
            item.result = "passed" if rule.name == "verified" else "failed"
            item.note, item.evidence_ids = note.strip(), [str(i) for i in evidence_ids]
            item.tested_by, item.tested_at = actor, now
            meta["retest_round"] = item.round.ref
        else:
            item.result = "not_tested"
            item.note = f"Finding moved to {rule.target.replace('_', ' ')} outside the retest."
        item.save()
        rounds[item.round_id] = item.round
    for rnd in rounds.values():
        rnd = RetestRound.objects.select_for_update(of=("self",)).select_related("engagement").get(pk=rnd.pk)
        if not rnd.items.filter(result="pending").exists():
            rnd.status, rnd.completed_at = "completed", now
            counts = {k: rnd.items.filter(result=k).count() for k in ("passed", "failed", "not_tested")}
            audit.record("retest_round.completed", request=request, entity=rnd, engagement=rnd.engagement,
                         metadata=counts)  # fmt: skip
        elif rnd.status == "queued":
            rnd.status = "in_progress"
        else:
            continue
        rnd.version += 1
        rnd.save()
    return meta
