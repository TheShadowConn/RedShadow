from dataclasses import dataclass

RESTRICTION_MFA_VERIFY = "mfa_verify"
RESTRICTION_PASSWORD_CHANGE = "password_change"  # noqa: S105
RESTRICTION_MFA_SETUP = "mfa_setup"


@dataclass(frozen=True)
class SessionState:
    mfa_verified: bool


def restriction(user, state: SessionState | None) -> str | None:
    """What the signed-in user must still do before the session is fully usable."""
    verified = bool(state and state.mfa_verified)
    if user.mfa_enabled and not verified:
        return RESTRICTION_MFA_VERIFY
    if user.must_change_password:
        return RESTRICTION_PASSWORD_CHANGE
    if user.role.mfa_required and not user.mfa_enabled:
        return RESTRICTION_MFA_SETUP
    return None
