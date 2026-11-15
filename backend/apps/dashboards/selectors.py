"""Dashboard numbers. Everything starts at ``scope_findings`` / ``scope_engagements`` / ``scope_audit``, so a
dashboard can never show more than the matching list screens. Counting is done in the database."""

from collections import Counter
from datetime import timedelta

from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import TruncWeek
from django.utils import timezone

from apps.audit.models import IntegrityCheck
from apps.audit.selectors import scope_audit
from apps.engagements.models import Engagement, EngagementCost
from apps.engagements.selectors import cost_totals, scope_engagements, with_overdue
from apps.findings import lifecycle
from apps.findings.models import SEVERITIES, STATUSES, Finding, RetestItem, RetestRound
from apps.findings.selectors import scope_findings, with_severity_rank
from apps.rbac.authz import has_platform_perm

SEVERITY_KEYS = [k for k, _ in SEVERITIES]
STATUS_KEYS = [k for k, _ in STATUSES]
ACTIVE = lifecycle.ACTIVE_STATUSES
WORKING = lifecycle.OVERDUE_STATUSES  # open, in progress, reopened: the clock runs
TREND_WEEKS = 12
UPCOMING_DAYS = 30
DUE_SOON_DAYS = 7
SLA_WINDOW_DAYS = 90
ACTIVITY_LIMIT = 8
COST_TOP = 8


def _zeroed(keys, counts) -> dict[str, int]:
    return {k: counts.get(k, 0) for k in keys}


def findings_block(user, today) -> dict:
    """Counts over every finding the user can see. Each number equals the same filter on the findings list."""
    qs = scope_findings(user).order_by()
    by_severity: Counter = Counter()
    by_status: Counter = Counter()
    open_by_severity: Counter = Counter()
    for row in qs.values("severity", "status").annotate(n=Count("pk")):
        by_severity[row["severity"]] += row["n"]
        by_status[row["status"]] += row["n"]
        if row["status"] in ACTIVE:
            open_by_severity[row["severity"]] += row["n"]
    working = qs.filter(status__in=WORKING)
    return {
        "total": sum(by_status.values()),
        "by_severity": _zeroed(SEVERITY_KEYS, by_severity),
        "by_status": _zeroed(STATUS_KEYS, by_status),
        "open_by_severity": _zeroed(SEVERITY_KEYS, open_by_severity),
        "open": sum(open_by_severity.values()),
        "overdue": working.filter(due_date__lt=today).count(),
        "due_soon": working.filter(due_date__gte=today, due_date__lte=today + timedelta(days=DUE_SOON_DAYS)).count(),
        "pending_verification": by_status.get("pending_verification", 0),
        "drafts": by_status.get("draft", 0),
        "risk_acceptance_expiring": qs.filter(
            status="risk_accepted", risk_accepted_until__lte=today + timedelta(days=UPCOMING_DAYS)
        ).count(),
    }


def engagements_block(user, today) -> dict:
    """Active (non-archived) engagements by status, and the ones starting soon."""
    qs = with_overdue(scope_engagements(user)).filter(archived_at__isnull=True).order_by()
    counts = Counter()
    for row in qs.values("status").annotate(n=Count("pk")):
        counts[row["status"]] += row["n"]
    keys = [k for k, _ in Engagement.STATUSES if k != "archived"]
    upcoming = (
        qs.filter(
            status__in=("planned", "scheduled"),
            start_date__gte=today,
            start_date__lte=today + timedelta(days=UPCOMING_DAYS),
        )
        .select_related("organisation")
        .order_by("start_date", "ref")[:8]
    )
    running = qs.filter(status="in_progress").select_related("organisation").order_by("end_date", "ref")[:6]
    row = lambda e: {  # noqa: E731
        "id": str(e.pk), "ref": e.ref, "name": e.name, "organisation": e.organisation.name, "status": e.status,
        "start_date": e.start_date, "end_date": e.end_date, "overdue": e.overdue,
    }  # fmt: skip
    return {
        "total": sum(counts.values()),
        "by_status": _zeroed(keys, counts),
        "overdue": qs.filter(overdue=True).count(),
        "upcoming": [row(e) for e in upcoming],
        "in_progress": [row(e) for e in running],
    }


def trend(user, today) -> list[dict]:
    """Findings opened (created, drafts excluded) and closed per week, oldest first."""
    start = today - timedelta(weeks=TREND_WEEKS - 1)
    start -= timedelta(days=start.weekday())
    qs = scope_findings(user).order_by()
    opened = Counter()
    closed = Counter()
    for row in (
        qs.exclude(status="draft")
        .filter(created_at__date__gte=start)
        .annotate(w=TruncWeek("created_at"))
        .values("w")
        .annotate(n=Count("pk"))
    ):
        opened[row["w"].date()] += row["n"]
    for row in (
        qs.filter(closed_at__date__gte=start).annotate(w=TruncWeek("closed_at")).values("w").annotate(n=Count("pk"))
    ):
        closed[row["w"].date()] += row["n"]
    return [
        {"week_start": (d := start + timedelta(weeks=i)), "opened": opened.get(d, 0), "closed": closed.get(d, 0)}
        for i in range(TREND_WEEKS)
    ]


def sla_block(user, today) -> dict:
    """Of the findings closed in the last 90 days that had a due date, how many closed on time; and time to fix."""
    since = timezone.now() - timedelta(days=SLA_WINDOW_DAYS)
    closed = scope_findings(user).order_by().filter(status="closed", closed_at__gte=since)
    dated = closed.filter(due_date__isnull=False)
    total = dated.count()
    on_time = dated.filter(closed_at__date__lte=F("due_date")).count()
    mean = closed.aggregate(avg=Avg(ExpressionWrapper(F("closed_at") - F("created_at"), output_field=DurationField())))[
        "avg"
    ]
    return {
        "window_days": SLA_WINDOW_DAYS,
        "closed": closed.count(),
        "dated": total,
        "on_time": on_time,
        "compliance_pct": round(100 * on_time / total, 1) if total else None,
        "mean_days_to_close": round(mean.total_seconds() / 86400, 1) if mean is not None else None,
    }


def activity(user) -> list[dict]:
    """Latest audit events the user may read (same scope and redaction as the audit explorer)."""
    rows = scope_audit(user).order_by("-id")[:ACTIVITY_LIMIT]
    return [
        {
            "id": e.pk, "at": e.occurred_at, "action": e.action, "entity_type": e.entity_type,
            "entity_label": e.entity_label, "actor": e.actor_label, "engagement_ref": e.engagement_ref,
            "outcome": e.outcome,
        }
        for e in rows
    ]  # fmt: skip


def _finding_row(f: Finding) -> dict:
    return {
        "id": str(f.pk), "ref": f.ref, "title": f.title, "severity": f.severity, "status": f.status,
        "due_date": f.due_date, "engagement": {"id": str(f.engagement_id), "ref": f.engagement.ref},
    }  # fmt: skip


def next_due(user, today, limit=8) -> list[dict]:
    qs = scope_findings(user).filter(status__in=WORKING).select_related("engagement")
    qs = with_severity_rank(qs).order_by(F("due_date").asc(nulls_last=True), "-severity_rank", "ref")[:limit]
    return [_finding_row(f) for f in qs]


def top_organisations(user, limit=5) -> list[dict]:
    rows = (
        scope_findings(user)
        .order_by()
        .filter(status__in=ACTIVE, severity__in=("critical", "high"))
        .values("engagement__organisation_id", "engagement__organisation__name")
        .annotate(
            critical=Count("pk", filter=Q(severity="critical")),
            high=Count("pk", filter=Q(severity="high")),
        )
        .order_by("-critical", "-high", "engagement__organisation__name")[:limit]
    )
    return [
        {
            "id": str(r["engagement__organisation_id"]),
            "name": r["engagement__organisation__name"],
            "critical": r["critical"],
            "high": r["high"],
        }
        for r in rows
    ]


def retests_for(user, limit=5) -> dict:
    """Retest rounds assigned to the user that still have findings to test."""
    rounds = (
        RetestRound.objects.filter(
            engagement__in=scope_engagements(user, "retests.view"), assessor=user, status__in=RetestRound.ACTIVE
        )
        .select_related("engagement")
        .order_by("created_at")
    )
    pending = dict(
        RetestItem.objects.filter(round__in=rounds, result="pending").values_list("round_id").annotate(n=Count("pk"))
    )
    rows = [
        {
            "id": str(r.pk),
            "ref": r.ref,
            "engagement": {"id": str(r.engagement_id), "ref": r.engagement.ref},
            "status": r.status,
            "pending": pending.get(r.pk, 0),
        }
        for r in rounds[:limit]
    ]
    return {"active_rounds": rounds.count(), "items_pending": sum(pending.values()), "rounds": rows}


def integrity() -> dict | None:
    check = IntegrityCheck.objects.exclude(status="running").first()
    if check is None:
        return None
    return {"status": check.status, "finished_at": check.finished_at, "checked": check.checked, "reason": check.reason}


# one entry per dashboard


def costs_block(user) -> dict | None:
    """Total cost per currency and the biggest engagements. None unless the user holds engagement_costs.view."""
    if not has_platform_perm(user, "engagement_costs.view"):
        return None
    scope = scope_engagements(user)
    rows = (
        EngagementCost.objects.filter(engagement__in=scope)
        .order_by()
        .values("engagement_id", "engagement__ref", "engagement__name", "currency")
        .annotate(total=Sum("amount"))
        .order_by("-total")[:COST_TOP]
    )
    return {
        "totals": cost_totals(engagements_qs=scope),
        "top": [
            {"engagement": {"id": str(r["engagement_id"]), "ref": r["engagement__ref"], "name": r["engagement__name"]},
             "currency": r["currency"], "total": r["total"]}
            for r in rows
        ],
    }  # fmt: skip


def admin(user, today) -> dict:
    return {
        "costs": costs_block(user),
        "top_organisations": top_organisations(user),
        "next_due": next_due(user, today),
        "integrity": integrity(),
    }


def pentester(user, today) -> dict:
    mine = scope_findings(user).filter(Q(assigned_pentester=user) | Q(remediation_owner=user)).order_by()
    return {
        "mine": {
            "open": mine.filter(status__in=ACTIVE).count(),
            "overdue": mine.filter(status__in=WORKING, due_date__lt=today).count(),
            "drafts": mine.filter(status="draft").count(),
        },
        "retests": retests_for(user),
        "next_due": next_due(user, today),
    }


def remediation(user, today) -> dict:
    since = timezone.now() - timedelta(days=30)
    return {
        "recently_closed": scope_findings(user).filter(status="closed", closed_at__gte=since).count(),
        "next_due": next_due(user, today),
    }


def vendor(user, today) -> dict:
    """External vendor: scope_findings already limits to their own findings, so "mine" is everything visible."""
    mine = scope_findings(user).order_by()
    return {
        "mine": {
            "open": mine.filter(status__in=ACTIVE).count(),
            "overdue": mine.filter(status__in=WORKING, due_date__lt=today).count(),
            "drafts": mine.filter(status="draft").count(),
        },
        "retests": retests_for(user),
        "next_due": next_due(user, today),
    }


EXTRAS = {"admin": admin, "pentester": pentester, "remediation": remediation, "vendor": vendor}


def build(kind: str, user) -> dict:
    today = timezone.localdate()
    return {
        "kind": kind,
        "generated_at": timezone.now(),
        "findings": findings_block(user, today),
        "engagements": engagements_block(user, today),
        "trend": trend(user, today),
        "sla": sla_block(user, today),
        "activity": activity(user),
        **EXTRAS[kind](user, today),
    }
