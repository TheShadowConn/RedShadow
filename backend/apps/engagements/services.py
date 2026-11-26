"""All engagement writes: refs, optimistic locking, lifecycle, membership, scope assets, notes."""

import functools

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import User
from apps.audit import service as audit
from apps.core.changes import apply_changes
from apps.core.errors import Conflict
from apps.notifications import services as inbox
from apps.organisations.models import Asset
from apps.rbac.authz import engagement_permissions, has_engagement_perm, role_permission_codes, user_permissions
from apps.rbac.guards import deny

from .models import (
    Engagement,
    EngagementAsset,
    EngagementCost,
    EngagementCounter,
    EngagementMembership,
    EngagementNote,
)

DETAIL_FIELDS = (
    "name", "type", "start_date", "end_date", "scope", "out_of_scope", "objectives",
    "methodology", "rules_of_engagement",
)  # fmt: skip

TRANSITIONS = {
    "planned": {"scheduled", "cancelled"},
    "scheduled": {"planned", "in_progress", "cancelled"},
    "in_progress": {"reporting", "cancelled"},
    "reporting": {"in_progress", "completed"},
    "completed": {"reporting"},
    "cancelled": {"planned"},
}


def next_ref(year: int) -> str:
    """Collision-safe: the per-year counter row is locked until the creating transaction ends."""
    EngagementCounter.objects.bulk_create([EngagementCounter(year=year, last=0)], ignore_conflicts=True)
    counter = EngagementCounter.objects.select_for_update().get(year=year)
    counter.last += 1
    counter.save(update_fields=["last"])
    return f"RS-E-{year}-{counter.last:04d}"


class _Refusal(Exception):
    """Raised inside a transaction; the audit record of the denial is written after rollback."""

    def __init__(self, action: str, reason: str, entity, metadata: dict | None = None):
        self.action, self.reason, self.entity, self.metadata = action, reason, entity, metadata


def _refuse(action: str, reason: str, entity) -> None:
    raise _Refusal(action, reason, entity)


def refusals_audited(func):
    """Turn a _Refusal into an audited 403 *outside* the rolled-back transaction."""

    @functools.wraps(func)
    def wrapper(request, *args, **kwargs):
        try:
            return func(request, *args, **kwargs)
        except _Refusal as refusal:
            deny(request, refusal.action, refusal.reason, refusal.entity, refusal.metadata)

    return wrapper


def _lock(engagement: Engagement) -> Engagement:
    return Engagement.objects.select_for_update(of=("self",)).select_related("organisation").get(pk=engagement.pk)


def _assert_writable(eng: Engagement) -> None:
    if eng.is_archived:
        raise Conflict("This engagement is archived. Unarchive it to make changes.")


def _check_version(eng: Engagement, version: int) -> None:
    if eng.version != version:
        raise Conflict("This engagement was changed by someone else. Reload and try again.")


def _check_dates(start, end) -> None:
    if end < start:
        raise ValidationError({"end_date": ["End date must be on or after the start date."]})


def _require_engagement_perm(request, actor, eng: Engagement, code: str, action: str) -> None:
    if not has_engagement_perm(actor, eng.pk, code):
        _refuse(action, "You do not have permission to perform this action.", eng)


def _bump_sessions(user_id, actor=None) -> None:
    """Sign a user out so new access applies. The person making the change stays signed in:
    access is checked on every request, so their session needs no reset."""
    if actor is not None and user_id == actor.pk:
        return
    User.objects.filter(pk=user_id).update(session_version=F("session_version") + 1)


def _ensure_member(request, actor, eng: Engagement, user: User) -> None:
    if user.role.all_engagements:
        return
    member, created = EngagementMembership.objects.get_or_create(
        engagement=eng, user=user, defaults={"added_by": actor}
    )
    if created:
        audit.record("engagement.member_added", request=request, entity=eng, engagement=eng,
                     metadata={"user": user.email, "via": "lead"})  # fmt: skip
        _bump_sessions(user.pk, actor)
        inbox.notify([user], "engagement.added", f"You were added to {eng.ref}", body=eng.name,
                     link=inbox.eng_link(eng), actor=actor, engagement=eng)


def _check_lead(user) -> None:
    if user is not None and not user.is_active:
        raise ValidationError({"lead": ["The lead must be an active user."]})


def create_engagement(request, actor, data: dict) -> Engagement:
    org = data["organisation"]
    if org.is_archived:
        raise Conflict("This organisation is archived.")
    _check_dates(data["start_date"], data["end_date"])
    lead = data.get("lead")
    _check_lead(lead)
    with transaction.atomic():
        eng = Engagement.objects.create(
            ref=next_ref(timezone.localdate().year),
            organisation=org,
            lead=lead,
            created_by=actor,
            **{f: data[f] for f in DETAIL_FIELDS if f in data},
        )
        audit.record(
            "engagement.created", request=request, entity=eng, engagement=eng,
            metadata={"organisation": org.name, "lead": lead.email if lead else None},
        )  # fmt: skip
        if lead is not None:
            _ensure_member(request, actor, eng, lead)
            inbox.notify([lead], "engagement.lead", f"You are the lead of {eng.ref}", body=eng.name,
                         link=inbox.eng_link(eng), actor=actor, engagement=eng)
    return eng


def clone_engagement(request, actor, src: Engagement, data: dict) -> Engagement:
    """New Planned engagement with the same organisation, type, text, team and live in-scope assets.
    Findings, notes, documents and costs are not copied."""
    src = Engagement.objects.select_related("organisation").get(pk=src.pk)
    fields = {f: getattr(src, f) for f in DETAIL_FIELDS if f not in ("name", "start_date", "end_date")}
    with transaction.atomic():
        eng = create_engagement(
            request, actor,
            {**fields, "organisation": src.organisation, "name": data["name"], "start_date": data["start_date"],
             "end_date": data["end_date"], "lead": data["lead"]},
        )  # fmt: skip
        added = []
        for m in EngagementMembership.objects.filter(engagement=src, user__is_active=True).select_related("user"):
            _, created = EngagementMembership.objects.get_or_create(
                engagement=eng, user=m.user,
                defaults={"role_override": m.role_override, "finding_scope": m.finding_scope, "added_by": actor},
            )
            if created:
                added.append(m.user)
                _bump_sessions(m.user_id, actor)
        links = EngagementAsset.objects.filter(
            engagement=src, asset__archived_at__isnull=True, asset__onboarding_status="onboarded"
        ).select_related("asset")
        EngagementAsset.objects.bulk_create(
            [EngagementAsset(engagement=eng, asset=ln.asset, in_scope=ln.in_scope, notes=ln.notes) for ln in links]
        )
        from . import scenarios

        copied = scenarios.copy_scenarios(request, actor, src, eng)
        audit.record("engagement.cloned", request=request, entity=eng, engagement=eng,
                     metadata={"source": src.ref, "members": len(added), "assets": len(links),
                               "scenarios": copied})  # fmt: skip
        inbox.notify(added, "engagement.added", f"You were added to {eng.ref}", body=eng.name,
                     link=inbox.eng_link(eng), actor=actor, engagement=eng)
    return eng


def update_engagement(request, actor, eng: Engagement, data: dict, version: int) -> Engagement:
    with transaction.atomic():
        eng = _lock(eng)
        _assert_writable(eng)
        _check_version(eng, version)
        changes = apply_changes(eng, data, DETAIL_FIELDS)
        _check_dates(eng.start_date, eng.end_date)
        if "lead" in data and data["lead"] != eng.lead:
            _check_lead(data["lead"])
            changes["lead"] = [eng.lead.email if eng.lead else None, data["lead"].email if data["lead"] else None]
            eng.lead = data["lead"]
            if eng.lead is not None:
                _ensure_member(request, actor, eng, eng.lead)
        if changes:
            eng.version += 1
            eng.save()
            audit.record("engagement.updated", request=request, entity=eng, engagement=eng, changes=changes)
            inbox.notify(inbox.engagement_people(eng), "engagement.updated", f"{eng.ref} was updated",
                         body="Changed: " + ", ".join(sorted(changes)), link=inbox.eng_link(eng), actor=actor,
                         engagement=eng)
    return eng


@refusals_audited
def change_status(
    request, actor, eng: Engagement, to_status: str, version: int, acknowledge_open_scenarios: bool = False
) -> Engagement:
    with transaction.atomic():
        eng = _lock(eng)
        _require_engagement_perm(request, actor, eng, "engagements.update_status", "engagement.status_denied")
        _assert_writable(eng)
        _check_version(eng, version)
        if to_status not in TRANSITIONS.get(eng.status, set()):
            raise ValidationError({"status": [f"Cannot move from {eng.status} to {to_status}."]})
        if to_status in ("reporting", "completed") and not acknowledge_open_scenarios:
            from . import scenarios

            pending = scenarios.open_count(eng)
            if pending:
                raise Conflict(
                    f"{pending} scenario{'s are' if pending != 1 else ' is'} not tested yet (planned, in progress "
                    "or deferred). Confirm to continue, or finish them first."
                )
        old, eng.status = eng.status, to_status
        eng.version += 1
        eng.save()
        meta = {"acknowledged_open_scenarios": True} if acknowledge_open_scenarios else None
        audit.record("engagement.status_changed", request=request, entity=eng, engagement=eng,
                     changes={"status": [old, to_status]}, metadata=meta)  # fmt: skip
        now_status = to_status.replace("_", " ")
        inbox.notify(inbox.engagement_people(eng), "engagement.status", f"{eng.ref} is now {now_status}",
                     body=eng.name, link=inbox.eng_link(eng), actor=actor, engagement=eng)
    return eng


def archive_engagement(request, actor, eng: Engagement, version: int) -> Engagement:
    with transaction.atomic():
        eng = _lock(eng)
        _assert_writable(eng)
        _check_version(eng, version)
        if eng.status not in ("completed", "cancelled"):
            raise Conflict("Only completed or cancelled engagements can be archived.")
        eng.status_before_archive, eng.status = eng.status, "archived"
        eng.archived_at = timezone.now()
        eng.version += 1
        eng.save()
        audit.record("engagement.archived", request=request, entity=eng, engagement=eng)
        inbox.notify(inbox.engagement_people(eng), "engagement.archived", f"{eng.ref} was archived", body=eng.name,
                     link=inbox.eng_link(eng), actor=actor, engagement=eng)
    return eng


def unarchive_engagement(request, actor, eng: Engagement, version: int) -> Engagement:
    with transaction.atomic():
        eng = _lock(eng)
        if not eng.is_archived:
            raise Conflict("This engagement is not archived.")
        _check_version(eng, version)
        if eng.organisation.is_archived:
            raise Conflict("The organisation is archived. Unarchive it first.")
        eng.status, eng.status_before_archive = eng.status_before_archive or "completed", ""
        eng.archived_at = None
        eng.version += 1
        eng.save()
        audit.record("engagement.unarchived", request=request, entity=eng, engagement=eng)
    return eng


@refusals_audited
def change_lead(request, actor, eng: Engagement, lead: User, version: int) -> Engagement:
    """Super Admin (``engagements.update``) swaps the lead at any time while the engagement is not archived."""
    with transaction.atomic():
        eng = _lock(eng)
        if "engagements.update" not in user_permissions(actor):
            _refuse("engagement.lead_denied", "You do not have permission to change the lead.", eng)
        _assert_writable(eng)
        _check_version(eng, version)
        _check_lead(lead)
        if eng.lead_id == lead.pk:
            raise Conflict("This user is already the lead.")
        old = eng.lead
        eng.lead = lead
        eng.version += 1
        eng.save()
        _ensure_member(request, actor, eng, lead)
        audit.record("engagement.lead_changed", request=request, entity=eng, engagement=eng,
                     changes={"lead": [old.email if old else None, lead.email]})  # fmt: skip
        inbox.notify([lead], "engagement.lead", f"You are now the lead of {eng.ref}", body=eng.name,
                     link=inbox.eng_link(eng), actor=actor, engagement=eng)
        inbox.notify([old], "engagement.lead_removed", f"You are no longer the lead of {eng.ref}", body=eng.name,
                     link=inbox.eng_link(eng), actor=actor, engagement=eng)
    return eng


@refusals_audited
def delete_engagement(request, actor, eng: Engagement, version: int, confirm_ref: str, reason: str = "") -> None:
    """Soft delete (separate from archive). Findings, evidence and history stay in the database;
    the engagement disappears from every scoped read. Always audited, the audit trail is never touched."""
    from apps.findings.models import Finding

    with transaction.atomic():
        eng = _lock(eng)
        if "engagements.delete" not in user_permissions(actor):
            _refuse("engagement.delete_denied", "You do not have permission to delete engagements.", eng)
        _check_version(eng, version)
        if confirm_ref.strip() != eng.ref:
            raise ValidationError({"confirm_ref": ["Type the engagement reference exactly to confirm."]})
        findings = Finding.all_objects.filter(engagement=eng).count()
        eng.deleted_at = timezone.now()
        eng.deleted_by = actor
        eng.version += 1
        eng.save(update_fields=["deleted_at", "deleted_by", "version", "updated_at"])
        audit.record(
            "engagement.deleted", request=request, entity=eng, engagement=eng,
            metadata={"ref": eng.ref, "name": eng.name, "organisation": eng.organisation.name,
                      "status": eng.status, "findings": findings, "reason": reason.strip() or None},
        )  # fmt: skip
        inbox.notify(inbox.engagement_people(eng), "engagement.deleted", f"{eng.ref} was deleted", body=eng.name,
                     actor=actor, engagement=eng)
        for user_id in EngagementMembership.objects.filter(engagement=eng).values_list("user_id", flat=True):
            _bump_sessions(user_id, actor)


@refusals_audited
def restore_engagement(request, actor, eng: Engagement) -> Engagement:
    """Undo a delete. Findings, team and history return with it."""
    with transaction.atomic():
        eng = Engagement.all_objects.select_for_update(of=("self",)).select_related("organisation").get(pk=eng.pk)
        if "engagements.delete" not in user_permissions(actor):
            _refuse("engagement.restore_denied", "You do not have permission to restore engagements.", eng)
        if eng.deleted_at is None:
            raise Conflict("This engagement is not deleted.")
        if eng.organisation.is_archived:
            raise Conflict("The organisation is archived. Unarchive it first.")
        eng.deleted_at = None
        eng.deleted_by = None
        eng.version += 1
        eng.save(update_fields=["deleted_at", "deleted_by", "version", "updated_at"])
        audit.record("engagement.restored", request=request, entity=eng, engagement=eng,
                     metadata={"ref": eng.ref, "name": eng.name})  # fmt: skip
        inbox.notify(inbox.engagement_people(eng), "engagement.restored", f"{eng.ref} was restored", body=eng.name,
                     link=inbox.eng_link(eng), actor=actor, engagement=eng)
        for user_id in EngagementMembership.objects.filter(engagement=eng).values_list("user_id", flat=True):
            _bump_sessions(user_id, actor)
    return eng


@refusals_audited
def join_engagement(request, actor, eng: Engagement) -> EngagementMembership:
    """The signed-in user adds themself to the team (own role, no override). Needs manage_members here."""
    with transaction.atomic():
        eng = _lock(eng)
        _require_engagement_perm(request, actor, eng, "engagements.manage_members", "engagement.member_denied")
        _assert_writable(eng)
        try:
            with transaction.atomic():
                member = EngagementMembership.objects.create(engagement=eng, user=actor, added_by=actor)
        except IntegrityError:
            raise Conflict("You are already a member of this engagement.") from None
        audit.record("engagement.member_added", request=request, entity=eng, engagement=eng,
                     metadata={"user": actor.email, "via": "self"})  # fmt: skip
    return member


# members


def _held(actor, eng: Engagement) -> frozenset:
    return user_permissions(actor) | engagement_permissions(actor, eng.pk)


def _assert_can_manage_role(request, actor, eng: Engagement, role, action: str) -> None:
    if role.all_engagements and not actor.role.all_engagements:
        _refuse(action, "You cannot grant access to all engagements.", eng)
    if not role_permission_codes(role.pk) <= _held(actor, eng):
        _refuse(action, "You cannot grant a role with more permissions than you have.", eng)


@refusals_audited
def add_member(request, actor, eng: Engagement, user: User, role_override, finding_scope: str) -> EngagementMembership:
    with transaction.atomic():
        eng = _lock(eng)
        _require_engagement_perm(request, actor, eng, "engagements.manage_members", "engagement.member_denied")
        _assert_writable(eng)
        if not user.is_active:
            raise ValidationError({"user": ["This user is deactivated."]})
        if user.pk == actor.pk:
            _refuse("engagement.member_denied", "You cannot change your own access.", eng)
        _assert_can_manage_role(request, actor, eng, user.role, "engagement.member_denied")
        if role_override is not None:
            _assert_can_manage_role(request, actor, eng, role_override, "engagement.member_denied")
        try:
            with transaction.atomic():
                member = EngagementMembership.objects.create(
                    engagement=eng, user=user, role_override=role_override,
                    finding_scope=finding_scope, added_by=actor,
                )  # fmt: skip
        except IntegrityError:
            raise Conflict("This user is already a member of the engagement.") from None
        audit.record(
            "engagement.member_added", request=request, entity=eng, engagement=eng,
            metadata={"user": user.email, "role_override": role_override.name if role_override else None,
                      "finding_scope": finding_scope or None},
        )  # fmt: skip
        _bump_sessions(user.pk)
        inbox.notify([user], "engagement.added", f"You were added to {eng.ref}", body=eng.name,
                     link=inbox.eng_link(eng), actor=actor, engagement=eng)
    return member


@refusals_audited
def update_member(request, actor, eng: Engagement, member: EngagementMembership, data: dict) -> EngagementMembership:
    with transaction.atomic():
        eng = _lock(eng)
        _require_engagement_perm(request, actor, eng, "engagements.manage_members", "engagement.member_denied")
        _assert_writable(eng)
        member = EngagementMembership.objects.select_related("user", "role_override").get(pk=member.pk)
        if member.user_id == actor.pk:
            _refuse("engagement.member_denied", "You cannot change your own access.", eng)
        _assert_can_manage_role(request, actor, eng, member.effective_role, "engagement.member_denied")
        changes = {}
        if "role_override" in data and data["role_override"] != member.role_override:
            if data["role_override"] is not None:
                _assert_can_manage_role(request, actor, eng, data["role_override"], "engagement.member_denied")
            changes["role_override"] = [
                member.role_override.name if member.role_override else None,
                data["role_override"].name if data["role_override"] else None,
            ]
            member.role_override = data["role_override"]
        if "finding_scope" in data and data["finding_scope"] != member.finding_scope:
            changes["finding_scope"] = [member.finding_scope or None, data["finding_scope"] or None]
            member.finding_scope = data["finding_scope"]
        if changes:
            member.save()
            audit.record("engagement.member_updated", request=request, entity=eng, engagement=eng,
                         changes=changes, metadata={"user": member.user.email})  # fmt: skip
            _bump_sessions(member.user_id)
    return member


@refusals_audited
def remove_member(request, actor, eng: Engagement, member: EngagementMembership) -> None:
    with transaction.atomic():
        eng = _lock(eng)
        _require_engagement_perm(request, actor, eng, "engagements.manage_members", "engagement.member_denied")
        _assert_writable(eng)
        member = EngagementMembership.objects.select_related("user", "role_override").get(pk=member.pk)
        if member.user_id == actor.pk:
            _refuse("engagement.member_denied", "You cannot change your own access.", eng)
        _assert_can_manage_role(request, actor, eng, member.effective_role, "engagement.member_denied")
        if eng.lead_id == member.user_id:
            raise Conflict("This user is the engagement lead. Assign another lead first.")
        user_id, email = member.user_id, member.user.email
        member.delete()
        audit.record("engagement.member_removed", request=request, entity=eng, engagement=eng, metadata={"user": email})
        _bump_sessions(user_id)
        inbox.notify([member.user], "engagement.removed", f"You were removed from {eng.ref}", body=eng.name,
                     actor=actor, engagement=eng)


# scope assets


def link_asset(request, actor, eng: Engagement, asset: Asset, in_scope: bool, notes: str) -> EngagementAsset:
    with transaction.atomic():
        eng = _lock(eng)
        _assert_writable(eng)
        if asset.organisation_id != eng.organisation_id:
            raise ValidationError({"asset": ["This asset does not belong to the engagement's organisation."]})
        if asset.is_archived:
            raise ValidationError({"asset": ["This asset is archived."]})
        if asset.onboarding_status != "onboarded":
            raise ValidationError(
                {"asset": ["This asset is not onboarded yet. Onboard it before adding it to an engagement."]}
            )
        try:
            with transaction.atomic():
                link = EngagementAsset.objects.create(engagement=eng, asset=asset, in_scope=in_scope, notes=notes)
        except IntegrityError:
            raise Conflict("This asset is already linked to the engagement.") from None
        audit.record("engagement.asset_linked", request=request, entity=eng, engagement=eng,
                     metadata={"asset": asset.name, "in_scope": in_scope})  # fmt: skip
    return link


def update_asset_link(request, actor, eng: Engagement, link: EngagementAsset, data: dict) -> EngagementAsset:
    with transaction.atomic():
        eng = _lock(eng)
        _assert_writable(eng)
        link = EngagementAsset.objects.select_related("asset").get(pk=link.pk)
        changes = apply_changes(link, data, ("in_scope", "notes"))
        if changes:
            link.save()
            audit.record("engagement.asset_updated", request=request, entity=eng, engagement=eng,
                         changes=changes, metadata={"asset": link.asset.name})  # fmt: skip
    return link


def unlink_asset(request, actor, eng: Engagement, link: EngagementAsset) -> None:
    with transaction.atomic():
        eng = _lock(eng)
        _assert_writable(eng)
        link = EngagementAsset.objects.select_related("asset").get(pk=link.pk)
        name = link.asset.name
        link.delete()
        audit.record("engagement.asset_unlinked", request=request, entity=eng, engagement=eng, metadata={"asset": name})


# notes


@refusals_audited
def add_note(request, actor, eng: Engagement, body: str, visibility: str) -> EngagementNote:
    with transaction.atomic():
        eng = _lock(eng)
        _require_engagement_perm(request, actor, eng, "engagement_notes.create", "engagement.note_denied")
        if visibility == "team" and not has_engagement_perm(actor, eng.pk, "engagement_notes.view_team"):
            _refuse("engagement.note_denied", "You cannot write team-only notes.", eng)
        _assert_writable(eng)
        note = EngagementNote.objects.create(engagement=eng, author=actor, body=body, visibility=visibility)
        audit.record("engagement.note_added", request=request, entity=eng, engagement=eng,
                     metadata={"note_id": str(note.pk), "visibility": visibility})  # fmt: skip
    return note


# costs. The platform permission is enforced by the viewset; the engagement is already scoped by get_object.

COST_FIELDS = ("amount", "currency", "category", "description", "incurred_on")


def add_cost(request, actor, eng: Engagement, data: dict) -> EngagementCost:
    with transaction.atomic():
        eng = _lock(eng)
        _assert_writable(eng)
        cost = EngagementCost.objects.create(engagement=eng, created_by=actor, **{k: data[k] for k in COST_FIELDS})
        audit.record("engagement.cost_added", request=request, entity=eng, engagement=eng,
                     metadata={"cost_id": str(cost.pk), "amount": cost.amount, "currency": cost.currency,
                               "category": cost.category})  # fmt: skip
    return cost


def update_cost(request, actor, eng: Engagement, cost: EngagementCost, data: dict) -> EngagementCost:
    with transaction.atomic():
        eng = _lock(eng)
        _assert_writable(eng)
        cost = EngagementCost.objects.select_related("created_by").get(pk=cost.pk)
        changes = apply_changes(cost, data, COST_FIELDS)
        if changes:
            cost.save()
            audit.record("engagement.cost_updated", request=request, entity=eng, engagement=eng,
                         changes=changes, metadata={"cost_id": str(cost.pk)})  # fmt: skip
    return cost


def delete_cost(request, actor, eng: Engagement, cost: EngagementCost) -> None:
    with transaction.atomic():
        eng = _lock(eng)
        _assert_writable(eng)
        cost = EngagementCost.objects.get(pk=cost.pk)
        meta = {"cost_id": str(cost.pk), "amount": cost.amount, "currency": cost.currency, "category": cost.category}
        cost.delete()
        audit.record("engagement.cost_deleted", request=request, entity=eng, engagement=eng, metadata=meta)
