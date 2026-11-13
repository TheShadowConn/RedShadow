# ADR-0010 Session, MFA and restricted-session model

Status: accepted (2026-11-12)

**Decision:** Server-side sessions, CSRF on every unsafe request (also login), session_version for instant revocation, idle 30 min and absolute 12 h limits. After password login a session can be restricted: mfa_verify, password_change or mfa_setup. Restricted sessions reach only the endpoints that clear the restriction.

**Why:** A forced password change or MFA enrolment must not leave a usable session in between. Django contrib.auth is not installed: only its hashers and validators are reused.

**Consequences:** TOTP secrets are Fernet-encrypted with a dedicated key (secrets volume, mfa_key). Recovery codes are stored as SHA-256 hashes and are single use. Losing mfa_key makes enrolled MFA secrets unreadable: back it up.
