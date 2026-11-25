"""Create notifications. Call inside the transaction of the change being announced."""

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from .models import Notification, NotificationPreference

# Notification kinds grouped for muting. Anything not listed falls under "other" and cannot be muted.
GROUPS = {"engagement": "Engagement changes", "assignments": "Assignments", "findings": "Finding updates",
          "deadlines": "Due dates and overdue", "retests": "Retests"}  # fmt: skip
EMAIL_GROUPS = {"assignments", "deadlines", "retests"}
_BY_KIND = {"finding.assigned": "assignments", "finding.due_soon": "deadlines", "finding.overdue": "deadlines",
            "scenario.due_soon": "deadlines", "scenario.overdue": "deadlines",
            "scenario.deferred_due": "deadlines"}


def group_of(kind: str) -> str:
    if kind in _BY_KIND:
        return _BY_KIND[kind]
    head = kind.split(".")[0]
    return {"engagement": "engagement", "finding": "findings", "retest": "retests"}.get(head, "other")


def _email(rows, group: str) -> None:
    """Send after the surrounding transaction commits. Failures are swallowed: email is a courtesy."""
    if not settings.EMAIL_ENABLED or group not in EMAIL_GROUPS:
        return
    wanted = set(
        NotificationPreference.objects.filter(
            user_id__in=[r.recipient_id for r in rows], email_enabled=True
        ).values_list("user_id", flat=True)
    )
    for r in rows:
        if r.recipient_id in wanted and r.recipient.email:
            link = f"{settings.APP_BASE_URL}{r.link}" if settings.APP_BASE_URL and r.link else ""
            transaction.on_commit(
                lambda r=r, link=link: send_mail(
                    f"RedShadow: {r.title}",
                    "\n".join(x for x in (r.title, r.body, link) if x),
                    None,
                    [r.recipient.email],
                    fail_silently=True,
                )
            )


def notify(
    users, kind: str, title: str, *, body: str = "", link: str = "", actor=None, engagement=None, dedupe_key: str = ""
) -> int:
    """One notification per distinct active user. The actor never notifies themself. With ``dedupe_key`` a user
    who already has a notification of this kind and key is skipped. Returns the count."""
    seen: dict = {}
    for user in users:
        if user is None or not user.is_active or (actor is not None and user.pk == actor.pk):
            continue
        seen[user.pk] = user
    group = group_of(kind)
    if seen and group != "other":
        muted = NotificationPreference.objects.filter(user_id__in=seen, muted__contains=[group])
        for uid in muted.values_list("user_id", flat=True):
            seen.pop(uid, None)
    if dedupe_key and seen:
        have = Notification.objects.filter(kind=kind, dedupe_key=dedupe_key, recipient_id__in=seen)
        for rid in have.values_list("recipient_id", flat=True):
            seen.pop(rid, None)
    rows = [
        Notification(
            recipient=user,
            actor=actor,
            kind=kind,
            title=title[:200],
            body=body[:400],
            link=link[:200],
            engagement_id=engagement.pk if engagement is not None else None,
            dedupe_key=dedupe_key,
        )
        for user in seen.values()
    ]
    Notification.objects.bulk_create(rows)
    _email(rows, group)
    return len(rows)


def engagement_people(eng):
    """Team members and the lead."""
    from apps.engagements.models import EngagementMembership

    people = [m.user for m in EngagementMembership.objects.filter(engagement=eng).select_related("user")]
    return people + ([eng.lead] if eng.lead_id else [])


def finding_people(f):
    return [f.reported_by, f.assigned_pentester, f.remediation_owner]


def eng_link(eng) -> str:
    return f"/engagements/{eng.pk}"


def finding_link(f) -> str:
    return f"/findings/{f.pk}"


def mark_read(user, ids=None) -> int:
    qs = Notification.objects.filter(recipient=user, read_at__isnull=True)
    if ids is not None:
        qs = qs.filter(pk__in=ids)
    return qs.update(read_at=timezone.now())
