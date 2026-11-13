"""Administrative user management. Every rule from blueprint 5.2 is enforced here."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit import service as audit
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
