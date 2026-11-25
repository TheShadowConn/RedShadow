"""Calendar feed, double-booking hints and rescheduling.

Reads start at ``scope_engagements(user, "calendar.view")`` and counts at ``scope_findings``, so the
calendar never shows more than the engagement and finding lists. Rescheduling reuses the engagement
locking, version and audit helpers. A double-booking hint is a warning only: it never blocks a move.
"""

import datetime

from django.db import transaction
from django.db.models import Count, Q
from rest_framework.exceptions import ValidationError

from apps.audit import service as audit
from apps.core.errors import Conflict
from apps.findings.selectors import scope_findings
from apps.rbac.authz import has_platform_perm

from . import services
from .models import OPEN_STATUSES, Engagement
from .selectors import scope_engagements, with_overdue

MAX_WINDOW_DAYS = 400
MAX_EVENTS = 1000
NOT_MOVABLE = ("completed", "cancelled")
ACTIVE_FINDING_STATUSES = ("open", "in_progress", "reopened", "pending_verification")


def parse_window(start: str, end: str) -> tuple[datetime.date, datetime.date]:
    try:
        s, e = datetime.date.fromisoformat(start or ""), datetime.date.fromisoformat(end or "")
    except ValueError:
        raise ValidationError({"start": ["Send start and end as dates (2026-11-01)."]}) from None
    if e < s:
        raise ValidationError({"end": ["End must be on or after start."]})
    if (e - s).days > MAX_WINDOW_DAYS:
        raise ValidationError({"end": [f"Ask for at most {MAX_WINDOW_DAYS} days at a time."]})
    return s, e


def _team_ids(eng: Engagement) -> set:
    ids = {m.user_id for m in eng.memberships.all()}
    if eng.lead_id:
        ids.add(eng.lead_id)
    return ids


def feed(user, start: datetime.date, end: datetime.date, filters: dict) -> list[dict]:
    qs = scope_engagements(user, "calendar.view").filter(
        archived_at__isnull=True, start_date__lte=end, end_date__gte=start
    )
    statuses = filters.get("status") or [s for s, _ in Engagement.STATUSES if s not in ("cancelled", "archived")]
    qs = qs.filter(status__in=statuses)
    if filters.get("engagement"):
        qs = qs.filter(pk__in=filters["engagement"])
    if filters.get("client"):
        qs = qs.filter(organisation_id=filters["client"])
    if filters.get("pentester"):
        qs = qs.filter(Q(memberships__user_id=filters["pentester"]) | Q(lead_id=filters["pentester"]))
    if filters.get("mine"):
        qs = qs.filter(Q(memberships__user_id=user.pk) | Q(lead_id=user.pk))
    qs = with_overdue(qs.distinct()).select_related("organisation", "lead").prefetch_related("memberships__user")
    engagements = list(qs.order_by("start_date", "ref")[: MAX_EVENTS + 1])
    if len(engagements) > MAX_EVENTS:
        raise ValidationError({"end": ["Too many engagements in this window. Narrow the dates or the filters."]})

    counts = {
        row["engagement_id"]: row
        for row in scope_findings(user)
        .filter(engagement_id__in=[e.pk for e in engagements])
        .values("engagement_id")
        .annotate(total=Count("pk"), active=Count("pk", filter=Q(status__in=ACTIVE_FINDING_STATUSES)))
    }
    events = []
    for e in engagements:
        team = {m.user_id: m.user for m in e.memberships.all()}
        if e.lead:
            team.setdefault(e.lead_id, e.lead)
        c = counts.get(e.pk, {})
        events.append({
            "id": e.pk, "ref": e.ref, "name": e.name, "type": e.type, "status": e.status, "overdue": e.overdue,
            "start_date": e.start_date, "end_date": e.end_date, "version": e.version,
            "client": {"id": e.organisation_id, "name": e.organisation.name},
            "lead": _user(e.lead) if e.lead else None,
            "team": [_user(u) for u in team.values()],
            "findings": {"total": c.get("total", 0), "active": c.get("active", 0)},
            "conflicts": [],
        })  # fmt: skip
    _mark_overlaps(events)
    return events


def _user(u) -> dict:
    return {"id": u.pk, "display_name": u.display_name}


def _overlap(a_start, a_end, b_start, b_end) -> bool:
    return a_start <= b_end and b_start <= a_end


def _mark_overlaps(events: list[dict]) -> None:
    """Fill ``conflicts`` on each open event: team members who also sit on another visible open event that overlaps."""
    by_user: dict = {}
    for ev in events:
        if ev["status"] in OPEN_STATUSES:
            for u in ev["team"]:
                by_user.setdefault(u["id"], (u, []))[1].append(ev)
    for person, items in by_user.values():
        for ev in items:
            for other in items:
                if other is ev:
                    continue
                if _overlap(ev["start_date"], ev["end_date"], other["start_date"], other["end_date"]):
                    brief = {"id": other["id"], "ref": other["ref"], "name": other["name"]}
                    ev["conflicts"].append({"user": person, "with": brief})


def find_conflicts(viewer, eng: Engagement, start: datetime.date, end: datetime.date) -> list[dict]:
    """Team members of ``eng`` double-booked on the new dates, limited to engagements the viewer can see."""
    team = {m.user_id: m.user for m in eng.memberships.select_related("user")}
    if eng.lead_id:
        team.setdefault(eng.lead_id, eng.lead)
    if not team:
        return []
    others = (
        scope_engagements(viewer, "calendar.view")
        .filter(archived_at__isnull=True, status__in=OPEN_STATUSES, start_date__lte=end, end_date__gte=start)
        .exclude(pk=eng.pk)
        .filter(Q(memberships__user_id__in=team) | Q(lead_id__in=team))
        .distinct()
        .prefetch_related("memberships")
    )
    out = []
    for o in others:
        shared = ({m.user_id for m in o.memberships.all()} | ({o.lead_id} if o.lead_id else set())) & set(team)
        brief = {"id": o.pk, "ref": o.ref, "name": o.name, "start_date": o.start_date, "end_date": o.end_date}
        out += [{"user": _user(team[uid]), "with": brief} for uid in shared]
    return out


@services.refusals_audited
def reschedule(request, actor, eng: Engagement, start, end, version: int, dry_run: bool = False):
    """Move an engagement's dates. Returns (engagement, conflicts). ``dry_run`` checks everything and saves nothing."""
    with transaction.atomic():
        eng = services._lock(eng)
        if not has_platform_perm(actor, "engagements.schedule"):
            services._refuse("engagement.reschedule_denied", "You do not have permission to reschedule.", eng)
        services._assert_writable(eng)
        services._check_version(eng, version)
        if eng.status in NOT_MOVABLE:
            raise Conflict("Completed and cancelled engagements cannot be rescheduled.")
        services._check_dates(start, end)
        conflicts = find_conflicts(actor, eng, start, end)
        if dry_run or (eng.start_date, eng.end_date) == (start, end):
            return eng, conflicts
        old = {"start_date": eng.start_date, "end_date": eng.end_date}
        eng.start_date, eng.end_date = start, end
        eng.version += 1
        eng.save()
        booked = [f"{c['user']['display_name']} with {c['with']['ref']}" for c in conflicts[:20]]
        audit.record(
            "engagement.rescheduled", request=request, entity=eng, engagement=eng,
            changes={"start_date": [old["start_date"], start], "end_date": [old["end_date"], end]},
            metadata={"double_booked": booked},
        )  # fmt: skip
    return eng, conflicts


def scenario_feed(user, start: datetime.date, end: datetime.date) -> list[dict]:
    """Scenarios with planned dates that touch the window, for engagements the user sees in the calendar and may
    read scenarios of. Cancelled scenarios are left out."""
    from .models import EngagementScenario

    visible = scope_engagements(user, "calendar.view").filter(archived_at__isnull=True)
    allowed = scope_engagements(user, "engagement_scenarios.view").values("pk")
    today = datetime.date.today()
    rows = (
        EngagementScenario.objects.filter(engagement__in=visible, engagement_id__in=allowed)
        .exclude(status="cancelled")
        .filter(planned_start__isnull=False)
        .filter(
            Q(planned_start__lte=end),
            Q(planned_end__gte=start) | Q(planned_end__isnull=True, planned_start__gte=start),
        )
        .select_related("engagement")
        .order_by("planned_start", "position")[: MAX_EVENTS + 1]
    )
    rows = list(rows)
    if len(rows) > MAX_EVENTS:
        raise ValidationError({"end": ["Too many scenarios in this window. Narrow the dates."]})
    return [
        {
            "id": r.pk, "name": r.name, "status": r.status, "planned_start": r.planned_start,
            "planned_end": r.planned_end or r.planned_start,
            "overdue": r.status in ("planned", "in_progress") and (r.planned_end or r.planned_start) < today,
            "engagement": {"id": r.engagement_id, "ref": r.engagement.ref, "name": r.engagement.name},
        }
        for r in rows
    ]  # fmt: skip
