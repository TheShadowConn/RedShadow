"""Administrative user management. Every rule from blueprint 5.2 is enforced here."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit import service as audit
from apps.core.errors import Conflict
from apps.rbac import guards
from apps.rbac.models import Role

from .models import User
from .services import generate_temporary_password, normalize_email


def _snapshot(user: User) -> dict:
    return {
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role.name,
        "is_active": user.is_active,
        "mfa_enabled": user.mfa_enabled,
    }


def _bump(user: User) -> None:
    """Invalidate every session of the user."""
    User.objects.filter(pk=user.pk).update(session_version=F("session_version") + 1)


def create_user(request, actor: User, email: str, display_name: str, role: Role) -> tuple[User, str]:
    guards.assert_can_grant_role(request, actor, role, "user.create_denied")
    email_n = normalize_email(email)
    try:
        validate_email(email_n)
    except DjangoValidationError as exc:
        raise ValidationError({"email": ["Enter a valid email address."]}) from exc
    temp = generate_temporary_password()
    try:
        with transaction.atomic():
            user = User(email=email_n, display_name=display_name.strip(), role=role,
                        must_change_password=True)  # fmt: skip
            user.set_password(temp)
            user.save()
            audit.record("user.created", request=request, entity=user, changes={"after": _snapshot(user)})
    except IntegrityError as exc:
        raise ValidationError({"email": ["A user with this email already exists."]}) from exc
    return user, temp


def update_user(request, actor: User, user: User, display_name: str | None, role: Role | None) -> User:
    before = _snapshot(user)
    if role is not None and role.pk != user.role_id:
        guards.assert_not_self(request, actor, user, "user.role_change_denied")
        guards.assert_outranks(request, actor, user, "user.role_change_denied")
        guards.assert_can_grant_role(request, actor, role, "user.role_change_denied", user)
        guards.assert_not_last_super_admin(request, user, "user.role_change_denied")
    elif display_name is not None and user.pk != actor.pk:
        guards.assert_outranks(request, actor, user, "user.update_denied")

    with transaction.atomic():
        if display_name is not None:
            user.display_name = display_name.strip()
        role_changed = role is not None and role.pk != user.role_id
        if role_changed:
            user.role = role
        user.save()
        if role_changed:
            _bump(user)  # new role takes effect on next sign-in
        after = _snapshot(user)
        if after != before:
            action = "user.role_changed" if role_changed else "user.updated"
            audit.record(action, request=request, entity=user,
                         changes={k: [before[k], after[k]] for k in after if before[k] != after[k]})  # fmt: skip
    return user


def deactivate_user(request, actor: User, user: User) -> User:
    action = "user.deactivate_denied"
    guards.assert_not_self(request, actor, user, action)
    guards.assert_outranks(request, actor, user, action)
    guards.assert_not_last_super_admin(request, user, action)
    with transaction.atomic():
        user.is_active = False
        user.deactivated_at = timezone.now()
        user.save(update_fields=["is_active", "deactivated_at"])
        _bump(user)
        audit.record("user.deactivated", request=request, entity=user, changes={"is_active": [True, False]})
    return user


def reactivate_user(request, actor: User, user: User) -> User:
    guards.assert_outranks(request, actor, user, "user.reactivate_denied")
    with transaction.atomic():
        user.is_active = True
        user.deactivated_at = None
        user.failed_login_count = 0
        user.locked_until = None
        user.save(update_fields=["is_active", "deactivated_at", "failed_login_count", "locked_until"])
        audit.record("user.reactivated", request=request, entity=user, changes={"is_active": [False, True]})
    return user


def reset_password(request, actor: User, user: User) -> str:
    action = "user.password_reset_denied"
    guards.assert_not_self(request, actor, user, action)
    guards.assert_outranks(request, actor, user, action)
    temp = generate_temporary_password()
    with transaction.atomic():
        user.set_password(temp)
        user.must_change_password = True
        user.failed_login_count = 0
        user.locked_until = None
        user.save(update_fields=["password", "must_change_password", "failed_login_count", "locked_until"])
        _bump(user)
        audit.record("user.password_reset", request=request, entity=user)
    return temp


def reset_mfa(request, actor: User, user: User) -> User:
    action = "user.mfa_reset_denied"
    guards.assert_not_self(request, actor, user, action)
    guards.assert_outranks(request, actor, user, action)
    with transaction.atomic():
        user.mfa_enabled = False
        user.mfa_secret = ""
        user.mfa_last_step = 0
        user.save(update_fields=["mfa_enabled", "mfa_secret_enc", "mfa_last_step"])
        user.recovery_codes.all().delete()
        _bump(user)
        audit.record("user.mfa_reset", request=request, entity=user)
    return user


def revoke_sessions(request, actor: User, user: User) -> None:
    if user.pk != actor.pk:
        guards.assert_outranks(request, actor, user, "user.sessions_revoke_denied")
    with transaction.atomic():
        _bump(user)
        audit.record("user.sessions_revoked", request=request, entity=user)


# deletion

OPEN_FINDING_STATUSES = ("draft", "open", "in_progress", "pending_verification", "reopened")
# Rows removed together with the account. Everything else that points at the user is history.
_CLEANED = {"engagementmembership", "importmapping", "recoverycode"}


def _history_references(user: User) -> dict[str, int]:
    """Rows that still point at the user after the clean-up: findings, notes, evidence, engagements ..."""
    found: dict[str, int] = {}
    for rel in User._meta.get_fields(include_hidden=True):  # most foreign keys use related_name="+"
        if not (rel.auto_created and not rel.concrete and rel.one_to_many):
            continue
        model = rel.related_model
        if model._meta.model_name in _CLEANED:
            continue
        n = model._base_manager.filter(**{rel.field.name: user}).count()
        if n:
            name = str(model._meta.verbose_name_plural).capitalize()
            found[name] = found.get(name, 0) + n
    return found


def deletion_impact(user: User) -> dict:
    """What deleting the account would do. Shown in the confirmation dialog, and used by delete_user."""
    from apps.engagements.models import Engagement, EngagementMembership
    from apps.findings.models import Finding, RetestRound
    from apps.imports.models import ImportJob, ImportMapping

    blockers = []
    active_rounds = RetestRound.objects.filter(assessor=user, status__in=RetestRound.ACTIVE).count()
    if active_rounds:
        blockers.append(f"{active_rounds} retest round(s) are assigned to this user. Reassign or cancel them first.")
    working = ImportJob.objects.filter(uploaded_by=user, status__in=ImportJob.WORKING).count()
    if working:
        blockers.append(f"{working} import(s) by this user are still running.")
    if user.is_active:
        blockers.append("Deactivate the account first. Deleting is only possible for deactivated accounts.")
    refs = _history_references(user)
    return {
        "blockers": blockers,
        "removes": {
            "memberships": EngagementMembership.objects.filter(user=user).count(),
            "saved_import_mappings": ImportMapping.objects.filter(owner=user).count(),
        },
        "clears": {
            "engagements_led": Engagement.objects.filter(lead=user)
            .exclude(status__in=("completed", "cancelled"))
            .count(),
            "findings_assigned": Finding.objects.filter(
                assigned_pentester=user, status__in=OPEN_FINDING_STATUSES
            ).count(),
            "findings_to_fix": Finding.objects.filter(remediation_owner=user, status__in=OPEN_FINDING_STATUSES).count(),
        },
        "history": refs,
        "mode": "anonymise" if refs else "remove",
    }


def delete_user(request, actor: User, user: User, confirm_email: str) -> dict:
    """Delete a deactivated account.

    The account is removed outright when nothing refers to it. When findings, notes, evidence or
    engagements do, the row stays as an anonymous tombstone (no name, e-mail or credentials) so history
    keeps its shape. Open work assigned to the user is unassigned. The audit log keeps the old e-mail.
    """
    from apps.engagements.models import Engagement, EngagementMembership
    from apps.findings.models import Finding
    from apps.imports.models import ImportMapping

    action = "user.delete_denied"
    guards.assert_not_self(request, actor, user, action)
    guards.assert_outranks(request, actor, user, action)
    guards.assert_not_last_super_admin(request, user, action)
    if user.deleted_at:
        raise Conflict("This account was already deleted.")
    if normalize_email(confirm_email) != user.email:
        raise ValidationError({"confirm_email": ["Type the account's email address to confirm."]})
    with transaction.atomic():
        user = User.objects.select_for_update().select_related("role").get(pk=user.pk)
        impact = deletion_impact(user)
        if impact["blockers"]:
            raise Conflict(" ".join(impact["blockers"]))
        before = _snapshot(user)
        EngagementMembership.objects.filter(user=user).delete()
        ImportMapping.objects.filter(owner=user).delete()
        user.recovery_codes.all().delete()
        Engagement.objects.filter(lead=user).update(lead=None)
        Finding.objects.filter(assigned_pentester=user, status__in=OPEN_FINDING_STATUSES).update(
            assigned_pentester=None, version=F("version") + 1
        )
        Finding.objects.filter(remediation_owner=user, status__in=OPEN_FINDING_STATUSES).update(
            remediation_owner=None, version=F("version") + 1
        )
        history = _history_references(user)
        metadata = {"mode": "anonymise" if history else "remove", "cleared": impact["clears"], "history": history}
        audit.record("user.deleted", request=request, entity=user, changes={"before": before}, metadata=metadata)
        if history:
            tombstone_id = str(user.pk)
            user.email = f"deleted-{tombstone_id}@deleted.invalid"
            user.display_name = "Deleted user"
            user.set_unusable_password()
            user.mfa_enabled, user.mfa_secret_enc, user.mfa_last_step = False, "", 0
            user.is_active, user.deleted_at = False, timezone.now()
            user.must_change_password = False
            user.session_version += 1
            user.save()
        else:
            user.delete()
    return metadata
