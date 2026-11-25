"""Engagement scenarios: what is tested in an engagement and when. No owner, no findings link (see ADR-0023)."""

import datetime

from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit import service as audit
from apps.core.changes import apply_changes
from apps.core.errors import Conflict
from apps.notifications import services as inbox

from .models import Engagement, EngagementScenario
from .services import _assert_writable, _lock, _require_engagement_perm, refusals_audited

DETAIL_FIELDS = ("name", "description")
DATE_FIELDS = ("planned_start", "planned_end")
MANAGE = "engagement_scenarios.manage"
MAX_SCENARIOS = 200

# From -> allowed targets. Leaving "tested" clears the completion date.
TRANSITIONS = {
    "planned": {"in_progress", "tested", "deferred", "cancelled"},
    "in_progress": {"planned", "tested", "deferred", "cancelled"},
    "deferred": {"planned", "in_progress", "cancelled"},
    "tested": {"in_progress"},
    "cancelled": {"planned"},
}
NEEDS_REASON = {"deferred", "cancelled"}


def _check_dates(start, end) -> None:
    if start and end and end < start:
        raise ValidationError({"planned_end": ["End date must be on or after the start date."]})


def _clean_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise ValidationError({"name": ["The name cannot be empty."]})
    return name


def _check_name_free(eng: Engagement, name: str, exclude=None) -> None:
    qs = EngagementScenario.objects.filter(engagement=eng, name__iexact=name)
    if exclude is not None:
        qs = qs.exclude(pk=exclude.pk)
    if qs.exists():
        raise ValidationError({"name": ["This engagement already has a scenario with that name."]})


def _fetch(eng: Engagement, scenario: EngagementScenario) -> EngagementScenario:
    return EngagementScenario.objects.select_for_update(of=("self",)).get(pk=scenario.pk, engagement=eng)


@refusals_audited
def add_scenario(request, actor, eng: Engagement, data: dict) -> EngagementScenario:
    name = _clean_name(data["name"])
    start, end = data.get("planned_start"), data.get("planned_end")
    _check_dates(start, end)
    with transaction.atomic():
        eng = _lock(eng)
        _require_engagement_perm(request, actor, eng, MANAGE, "engagement.scenario_denied")
        _assert_writable(eng)
        if EngagementScenario.objects.filter(engagement=eng).count() >= MAX_SCENARIOS:
            raise Conflict(f"An engagement can hold at most {MAX_SCENARIOS} scenarios.")
        _check_name_free(eng, name)
        last = EngagementScenario.objects.filter(engagement=eng).aggregate(m=Max("position"))["m"]
        try:
            sc = EngagementScenario.objects.create(
                engagement=eng, name=name, description=data.get("description", ""), planned_start=start,
                planned_end=end, position=0 if last is None else last + 1, created_by=actor,
            )  # fmt: skip
        except IntegrityError:
            raise ValidationError({"name": ["This engagement already has a scenario with that name."]}) from None
        audit.record("engagement.scenario_added", request=request, entity=eng, engagement=eng,
                     metadata={"scenario_id": str(sc.pk), "name": sc.name})  # fmt: skip
    return sc


@refusals_audited
def update_scenario(request, actor, eng: Engagement, scenario: EngagementScenario, data: dict) -> EngagementScenario:
    if "name" in data:
        data = {**data, "name": _clean_name(data["name"])}
    with transaction.atomic():
        eng = _lock(eng)
        _require_engagement_perm(request, actor, eng, MANAGE, "engagement.scenario_denied")
        _assert_writable(eng)
        sc = _fetch(eng, scenario)
        if "name" in data:
            _check_name_free(eng, data["name"], exclude=sc)
        changes = apply_changes(sc, data, DETAIL_FIELDS)
        if changes:
            sc.save()
            audit.record("engagement.scenario_updated", request=request, entity=eng, engagement=eng,
                         changes=changes, metadata={"scenario_id": str(sc.pk), "name": sc.name})  # fmt: skip
    return sc


@refusals_audited
def reschedule_scenario(
    request, actor, eng: Engagement, scenario: EngagementScenario, data: dict
) -> EngagementScenario:
    """New planned dates. A deferred scenario that gets dates is planned again."""
    _check_dates(data["planned_start"], data["planned_end"])
    with transaction.atomic():
        eng = _lock(eng)
        _require_engagement_perm(request, actor, eng, MANAGE, "engagement.scenario_denied")
        _assert_writable(eng)
        sc = _fetch(eng, scenario)
        if sc.status in ("tested", "cancelled"):
            raise Conflict(f"A {sc.status} scenario cannot be rescheduled. Reopen it first.")
        changes = apply_changes(sc, data, DATE_FIELDS)
        reason = data.get("reason", "")
        if sc.status == "deferred" and (data["planned_start"] or data["planned_end"]):
            changes["status"] = [sc.status, "planned"]
            sc.status = "planned"
        if changes:
            sc.status_reason = reason if reason else ("" if "status" in changes else sc.status_reason)
            sc.save()
            audit.record("engagement.scenario_rescheduled", request=request, entity=eng, engagement=eng,
                         changes=changes, metadata={"scenario_id": str(sc.pk), "name": sc.name,
                                                    "reason": reason})  # fmt: skip
    return sc


@refusals_audited
def change_scenario_status(
    request, actor, eng: Engagement, scenario: EngagementScenario, data: dict
) -> EngagementScenario:
    to, reason = data["status"], data.get("reason", "").strip()
    if to in NEEDS_REASON and not reason:
        raise ValidationError({"reason": ["A reason is required."]})
    with transaction.atomic():
        eng = _lock(eng)
        _require_engagement_perm(request, actor, eng, MANAGE, "engagement.scenario_denied")
        _assert_writable(eng)
        sc = _fetch(eng, scenario)
        if to not in TRANSITIONS.get(sc.status, ()):
            raise Conflict(f"A {sc.get_status_display().lower()} scenario cannot become {to.replace('_', ' ')}.")
        before = sc.status
        sc.status = to
        sc.status_reason = reason if to in NEEDS_REASON else ""
        if to == "tested":
            sc.completed_on = data.get("completed_on") or timezone.localdate()
        else:
            sc.completed_on = None
        if "planned_start" in data or "planned_end" in data:
            start = data.get("planned_start", sc.planned_start)
            end = data.get("planned_end", sc.planned_end)
            _check_dates(start, end)
            sc.planned_start, sc.planned_end = start, end
        sc.save()
        audit.record("engagement.scenario_status_changed", request=request, entity=eng, engagement=eng,
                     changes={"status": [before, to]},
                     metadata={"scenario_id": str(sc.pk), "name": sc.name, "reason": reason})  # fmt: skip
    return sc


@refusals_audited
def reorder_scenarios(request, actor, eng: Engagement, ids: list) -> list[EngagementScenario]:
    with transaction.atomic():
        eng = _lock(eng)
        _require_engagement_perm(request, actor, eng, MANAGE, "engagement.scenario_denied")
        _assert_writable(eng)
        rows = {s.pk: s for s in EngagementScenario.objects.select_for_update(of=("self",)).filter(engagement=eng)}
        if len(set(ids)) != len(ids) or set(ids) != set(rows):
            raise ValidationError({"ids": ["List every scenario of this engagement exactly once."]})
        moved = []
        for position, pk in enumerate(ids):
            if rows[pk].position != position:
                rows[pk].position = position
                rows[pk].save(update_fields=["position", "updated_at"])
                moved.append(str(pk))
        if moved:
            audit.record("engagement.scenarios_reordered", request=request, entity=eng, engagement=eng,
                         metadata={"order": [str(i) for i in ids]})  # fmt: skip
    return [rows[pk] for pk in ids]


OPEN_SCENARIO = ("planned", "in_progress", "deferred")
BULK_MAX = 50
REMINDER_DAYS = 3


def summarise(rows, today: datetime.date | None = None) -> dict:
    """Counts for the progress bar. ``total`` leaves out cancelled scenarios (3 of 5 = 3 tested of 5 that count)."""
    today = today or timezone.localdate()
    counts = {k: 0 for k, _ in EngagementScenario.STATUSES}
    overdue, upcoming = 0, []
    for sc in rows:
        counts[sc.status] += 1
        if sc.status in ("planned", "in_progress") and sc.planned_end and sc.planned_end < today:
            overdue += 1
        if sc.status in OPEN_SCENARIO and sc.planned_start and sc.planned_start >= today:
            upcoming.append(sc.planned_start)
    return {
        "total": sum(counts.values()) - counts["cancelled"],
        **counts,
        "overdue": overdue,
        "next_date": min(upcoming) if upcoming else None,
    }


def open_count(eng: Engagement) -> int:
    return EngagementScenario.objects.filter(engagement=eng, status__in=OPEN_SCENARIO).count()


@refusals_audited
def add_scenarios_bulk(request, actor, eng: Engagement, names: list[str]) -> list[EngagementScenario]:
    """One scenario per name, all or nothing. A name that already exists, or repeats in the list, rejects the batch."""
    cleaned = [_clean_name(n) for n in names]
    if not cleaned or len(cleaned) > BULK_MAX:
        raise ValidationError({"names": [f"Send between 1 and {BULK_MAX} names."]})
    lowered = [n.lower() for n in cleaned]
    repeated = sorted({n for n in cleaned if lowered.count(n.lower()) > 1})
    if repeated:
        raise ValidationError({"names": [f"Repeated in the list: {', '.join(repeated)}."]})
    with transaction.atomic():
        eng = _lock(eng)
        _require_engagement_perm(request, actor, eng, MANAGE, "engagement.scenario_denied")
        _assert_writable(eng)
        existing = EngagementScenario.objects.filter(engagement=eng)
        if existing.count() + len(cleaned) > MAX_SCENARIOS:
            raise Conflict(f"An engagement can hold at most {MAX_SCENARIOS} scenarios.")
        taken = sorted(n for n in cleaned if existing.filter(name__iexact=n).exists())
        if taken:
            raise ValidationError({"names": [f"Already in this engagement: {', '.join(taken)}."]})
        last = existing.aggregate(m=Max("position"))["m"]
        start = 0 if last is None else last + 1
        made = EngagementScenario.objects.bulk_create(
            [EngagementScenario(engagement=eng, name=n, position=start + i, created_by=actor)
             for i, n in enumerate(cleaned)]
        )  # fmt: skip
        audit.record("engagement.scenarios_added", request=request, entity=eng, engagement=eng,
                     metadata={"count": len(made), "names": cleaned})  # fmt: skip
    return made


def copy_scenarios(request, actor, src: Engagement, dst: Engagement) -> int:
    """Clone helper: names and descriptions only, all planned, no dates, no pictures. Cancelled ones are skipped."""
    rows = EngagementScenario.objects.filter(engagement=src).exclude(status="cancelled")
    EngagementScenario.objects.bulk_create(
        [EngagementScenario(engagement=dst, name=r.name, description=r.description, position=i, created_by=actor)
         for i, r in enumerate(rows)]
    )  # fmt: skip
    return rows.count()


def _people(eng: Engagement):
    return inbox.engagement_people(eng)


def remind(today: datetime.date | None = None) -> int:
    """Hourly sweep. Tell the engagement team a scenario starts within 3 days or is past its planned end.
    Once per scenario and date, so repeats and re-runs are harmless."""
    today = today or timezone.localdate()
    sent = 0
    soon = EngagementScenario.objects.filter(
        status__in=("planned", "deferred"), planned_start__gte=today,
        planned_start__lte=today + datetime.timedelta(days=REMINDER_DAYS),
        engagement__archived_at__isnull=True, engagement__deleted_at__isnull=True,
    ).select_related("engagement__lead")  # fmt: skip
    for sc in soon:
        sent += bool(inbox.notify(
            _people(sc.engagement), "scenario.due_soon",
            f"{sc.engagement.ref}: {sc.name} starts {sc.planned_start.isoformat()}", body=sc.engagement.name,
            link=inbox.eng_link(sc.engagement), engagement=sc.engagement,
            dedupe_key=f"{sc.pk}:start:{sc.planned_start.isoformat()}",
        ))  # fmt: skip
    late = EngagementScenario.objects.filter(
        status__in=("planned", "in_progress"), planned_end__lt=today,
        engagement__archived_at__isnull=True, engagement__deleted_at__isnull=True,
    ).select_related("engagement__lead")  # fmt: skip
    for sc in late:
        sent += bool(inbox.notify(
            _people(sc.engagement), "scenario.overdue", f"{sc.engagement.ref}: {sc.name} is past its planned end",
            body=sc.engagement.name, link=inbox.eng_link(sc.engagement), engagement=sc.engagement,
            dedupe_key=f"{sc.pk}:overdue:{sc.planned_end.isoformat()}",
        ))  # fmt: skip
    return sent
