"""Authentication, MFA and password logic. All writes to accounts state go through here."""

import hashlib
import hmac
import secrets
import time
from datetime import timedelta

import pyotp
import segno
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.audit import service as audit

from .models import RecoveryCode, User

GENERIC_LOGIN_ERROR = "Invalid email or password."
GENERIC_CODE_ERROR = "Invalid code."
LOCK_THRESHOLD = 5
LOCK_DURATION = timedelta(minutes=15)
TOTP_STEP = 30
RECOVERY_CODE_COUNT = 10

_dummy_hash: str | None = None


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _burn_hash_time(password: str) -> None:
    """Spend the same time as a real check so unknown/locked accounts are not distinguishable."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = make_password("redshadow-timing-parity")
    check_password(password, _dummy_hash)


def generate_temporary_password() -> str:
    return secrets.token_urlsafe(16)


def validate_new_password(password: str, user: User | None = None) -> None:
    try:
        validate_password(password, user)
    except DjangoValidationError as exc:
        raise DRFValidationError({"new_password": list(exc.messages)}) from exc


# --- sessions -------------------------------------------------------------------------------


def start_session(request, user: User, mfa_verified: bool) -> None:
    session = request._request.session
    session.flush()  # new session key: prevents fixation
    session["uid"] = str(user.pk)
    session["sv"] = user.session_version
    session["login_at"] = int(time.time())
    session["mfa_ok"] = bool(mfa_verified)


def end_session(request) -> None:
    request._request.session.flush()


# --- login ----------------------------------------------------------------------------------


def _register_failure(user: User) -> bool:
    """Count a failed attempt. Returns True when the account just became locked."""
    with transaction.atomic():
        locked = User.objects.select_for_update().get(pk=user.pk)
        locked.failed_login_count += 1
        just_locked = locked.failed_login_count >= LOCK_THRESHOLD
        if just_locked:
            locked.locked_until = timezone.now() + LOCK_DURATION
            locked.failed_login_count = 0
        locked.save(update_fields=["failed_login_count", "locked_until"])
    return just_locked


def login(request, email: str, password: str) -> User:
    email_n = normalize_email(email)
    user = User.objects.select_related("role").filter(email=email_n).first()

    if user is None or not user.is_active:
        _burn_hash_time(password)
        audit.record("auth.login_failed", request=request, actor_label=email_n, outcome="failure",
                     metadata={"reason": "unknown_or_inactive"})  # fmt: skip
        raise AuthenticationFailed(GENERIC_LOGIN_ERROR)

    if user.is_locked:
        _burn_hash_time(password)
        audit.record("auth.login_blocked", request=request, actor=user, outcome="denied",
                     metadata={"reason": "account_locked"})  # fmt: skip
        raise AuthenticationFailed(GENERIC_LOGIN_ERROR)

    if not user.check_password(password):
        just_locked = _register_failure(user)
        audit.record("auth.login_failed", request=request, actor=user, outcome="failure",
                     metadata={"reason": "bad_password", "locked": just_locked})  # fmt: skip
        raise AuthenticationFailed(GENERIC_LOGIN_ERROR)

    User.objects.filter(pk=user.pk).update(failed_login_count=0, locked_until=None, last_login=timezone.now())
    user.refresh_from_db()
    start_session(request, user, mfa_verified=False)
    audit.record("auth.login", request=request, actor=user, metadata={"mfa_enabled": user.mfa_enabled})
    return user


# --- password -------------------------------------------------------------------------------


def change_password(request, user: User, current: str, new: str) -> None:
    if not user.check_password(current):
        audit.record("auth.password_change_failed", request=request, actor=user, outcome="failure")
        raise DRFValidationError({"current_password": ["Current password is incorrect."]})
    if current == new:
        raise DRFValidationError({"new_password": ["Choose a password you have not used just now."]})
    validate_new_password(new, user)
    with transaction.atomic():
        user.set_password(new)
        user.must_change_password = False
        user.last_password_change = timezone.now()
        user.session_version = F("session_version") + 1
        user.save(update_fields=["password", "must_change_password", "last_password_change",
                                 "session_version"])  # fmt: skip
        user.refresh_from_db()
        audit.record("auth.password_changed", request=request, actor=user)
    # Same device stays signed in on a fresh session; every other session is revoked.
    start_session(request, user, mfa_verified=bool(request._request.session.get("mfa_ok", False)))


# --- MFA (TOTP) -----------------------------------------------------------------------------


def begin_mfa_setup(request, user: User) -> dict:
    if user.mfa_enabled:
        raise DRFValidationError({"detail": "MFA is already enabled. Ask an admin to reset it."})
    secret = pyotp.random_base32()
    user.mfa_secret = secret
    user.save(update_fields=["mfa_secret_enc"])
    uri = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name="RedShadow")
    svg = segno.make(uri, error="m").svg_data_uri(scale=6, border=2, dark="#1f3038", light="#ffffff")
    audit.record("auth.mfa_setup_started", request=request, actor=user)
    return {"secret": secret, "otpauth_uri": uri, "qr_svg": svg}


def _check_totp(user: User, code: str) -> bool:
    """Accepts +-1 step; a step can be used once (replay protection)."""
    if not user.mfa_secret_enc or not code.isdigit() or len(code) != 6:
        return False
    totp = pyotp.TOTP(user.mfa_secret)
    current = int(time.time() // TOTP_STEP)
    for step in (current - 1, current, current + 1):
        if step > user.mfa_last_step and hmac.compare_digest(totp.generate_otp(step), code):
            User.objects.filter(pk=user.pk).update(mfa_last_step=step)
            user.mfa_last_step = step
            return True
    return False


def _hash_recovery(code: str) -> str:
    return hashlib.sha256(code.strip().lower().replace("-", "").encode()).hexdigest()


def _mfa_failure(request, user: User, kind: str) -> None:
    just_locked = _register_failure(user)
    audit.record("auth.mfa_failed", request=request, actor=user, outcome="failure",
                 metadata={"method": kind, "locked": just_locked})  # fmt: skip
    raise AuthenticationFailed(GENERIC_CODE_ERROR)


def confirm_mfa_setup(request, user: User, code: str) -> list[str]:
    if user.mfa_enabled:
        raise DRFValidationError({"detail": "MFA is already enabled."})
    if not _check_totp(user, code):
        _mfa_failure(request, user, "setup")
    with transaction.atomic():
        user.mfa_enabled = True
        user.save(update_fields=["mfa_enabled"])
        user.recovery_codes.all().delete()
        plain = [f"{secrets.token_hex(3)}-{secrets.token_hex(3)}" for _ in range(RECOVERY_CODE_COUNT)]
        RecoveryCode.objects.bulk_create([RecoveryCode(user=user, code_hash=_hash_recovery(c)) for c in plain])
        audit.record("auth.mfa_enabled", request=request, actor=user)
    request._request.session["mfa_ok"] = True
    return plain


def verify_mfa(request, user: User, code: str | None, recovery_code: str | None) -> None:
    if code:
        if not _check_totp(user, code):
            _mfa_failure(request, user, "totp")
        method = "totp"
    elif recovery_code:
        row = user.recovery_codes.filter(code_hash=_hash_recovery(recovery_code), used_at__isnull=True).first()
        if row is None:
            _mfa_failure(request, user, "recovery")
        row.used_at = timezone.now()
        row.save(update_fields=["used_at"])
        method = "recovery"
    else:
        raise DRFValidationError({"code": ["Enter a code."]})
    request._request.session["mfa_ok"] = True
    audit.record("auth.mfa_verified", request=request, actor=user, metadata={"method": method})


def remaining_recovery_codes(user: User) -> int:
    return user.recovery_codes.filter(used_at__isnull=True).count()
