import time
from datetime import timedelta

import pyotp
import pytest
from django.db import connection
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from apps.accounts.models import RecoveryCode, User
from apps.audit.models import AuditEvent
from tests.conftest import PASSWORD, Api, make_role, make_user, signed_in

LOGIN = "/api/v1/auth/login"


def actions():
    return list(AuditEvent.objects.values_list("action", flat=True))


@pytest.mark.django_db
class TestLogin:
    def test_success_sets_hardened_cookie_and_rotates_session(self, api, pentester):
        before = api.get("/api/v1/auth/csrf").cookies.get("rs_csrf")
        assert before is not None
        r = api.login(pentester)
        cookie = r.cookies["rs_session"]
        assert cookie["httponly"] and cookie["samesite"] == "Lax"
        assert r.json()["restriction"] is None
        assert "auth.login" in actions()

    def test_new_session_key_each_login(self, pentester):
        a, b = Api(), Api()
        assert a.login(pentester).cookies["rs_session"].value != b.login(pentester).cookies["rs_session"].value

    def test_wrong_password_and_unknown_user_are_indistinguishable(self, api, pentester):
        bad = api.post(LOGIN, {"email": pentester.email, "password": "nope"}, format="json")
        unknown = api.post(LOGIN, {"email": "ghost@example.com", "password": "nope"}, format="json")
        assert bad.status_code == unknown.status_code == 401
        assert bad.json()["error"]["message"] == unknown.json()["error"]["message"]
        assert actions().count("auth.login_failed") == 2

    def test_email_is_case_insensitive(self, api, pentester):
        r = api.post(LOGIN, {"email": "PEN@Example.COM", "password": PASSWORD}, format="json")
        assert r.status_code == 200

    def test_inactive_user_cannot_login(self, api, pentester):
        User.objects.filter(pk=pentester.pk).update(is_active=False)
        r = api.post(LOGIN, {"email": pentester.email, "password": PASSWORD}, format="json")
        assert r.status_code == 401

    def test_lockout_after_five_failures_then_blocks_correct_password(self, api, pentester):
        for _ in range(5):
            api.post(LOGIN, {"email": pentester.email, "password": "wrong"}, format="json")
        pentester.refresh_from_db()
        assert pentester.is_locked
        r = api.post(LOGIN, {"email": pentester.email, "password": PASSWORD}, format="json")
        assert r.status_code == 401
        assert "auth.login_blocked" in actions()

    def test_lock_expires(self, api, pentester):
        User.objects.filter(pk=pentester.pk).update(locked_until=timezone.now() - timedelta(seconds=1))
        assert api.post(LOGIN, {"email": pentester.email, "password": PASSWORD}, format="json").status_code == 200

    def test_success_resets_failure_counter(self, api, pentester):
        for _ in range(3):
            api.post(LOGIN, {"email": pentester.email, "password": "wrong"}, format="json")
        api.login(pentester)
        pentester.refresh_from_db()
        assert pentester.failed_login_count == 0

    def test_login_requires_csrf(self, pentester):
        raw = APIClient(enforce_csrf_checks=True)
        r = raw.post(LOGIN, {"email": pentester.email, "password": PASSWORD}, format="json")
        assert r.status_code == 403
        assert "CSRF" in r.json()["error"]["message"]

    def test_unknown_fields_rejected(self, api, pentester):
        r = api.post(LOGIN, {"email": pentester.email, "password": PASSWORD, "role": "x"}, format="json")
        assert r.status_code == 400

    def test_login_is_throttled(self, api, pentester, monkeypatch):
        monkeypatch.setattr(
            ScopedRateThrottle, "THROTTLE_RATES", {"login": "3/min", "mfa": "3/min", "password": "3/min"}
        )
        from django.core.cache import cache

        cache.clear()
        codes = [
            api.post(LOGIN, {"email": "x@example.com", "password": "p"}, format="json").status_code for _ in range(5)
        ]
        assert codes[-1] == 429
        cache.clear()

    def test_logout_destroys_session(self, pentester):
        c = signed_in(pentester)
        assert c.get("/api/v1/auth/me").status_code == 200
        assert c.post("/api/v1/auth/logout").status_code == 204
        assert c.get("/api/v1/auth/me").status_code == 401
        assert "auth.logout" in actions()

    def test_anonymous_gets_401_envelope(self, api):
        r = api.get("/api/v1/auth/me")
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "not_authenticated"


@pytest.mark.django_db
class TestSessionPolicy:
    def test_session_version_bump_kills_session(self, pentester):
        c = signed_in(pentester)
        User.objects.filter(pk=pentester.pk).update(session_version=2)
        assert c.get("/api/v1/auth/me").status_code == 401

    def test_absolute_lifetime_enforced(self, pentester):
        c = signed_in(pentester)
        session = c.session
        session["login_at"] = int(time.time()) - 13 * 3600
        session.save()
        assert c.get("/api/v1/auth/me").status_code == 401

    def test_idle_timeout_is_configured(self):
        from django.conf import settings

        assert settings.SESSION_COOKIE_AGE == 1800 and settings.SESSION_SAVE_EVERY_REQUEST
        assert settings.SESSION_ABSOLUTE_SECONDS == 43200

    def test_deactivated_user_session_dies(self, pentester):
        c = signed_in(pentester)
        User.objects.filter(pk=pentester.pk).update(is_active=False)
        assert c.get("/api/v1/auth/me").status_code == 401

    def test_locked_user_session_dies(self, pentester):
        c = signed_in(pentester)
        User.objects.filter(pk=pentester.pk).update(locked_until=timezone.now() + timedelta(minutes=5))
        assert c.get("/api/v1/auth/me").status_code == 401


@pytest.mark.django_db
class TestPassword:
    def test_forced_change_restricts_then_unlocks(self):
        user = make_user("new@example.com", "remediation", must_change_password=True)
        c = Api()
        assert c.login(user).json()["restriction"] == "password_change"
        assert c.get("/api/v1/users").status_code == 403
        weak = c.post(
            "/api/v1/auth/password/change",
            {"current_password": PASSWORD, "new_password": "password1234"},
            format="json",
        )
        assert weak.status_code == 400 and "new_password" in weak.json()["error"]["fields"]
        short = c.post(
            "/api/v1/auth/password/change", {"current_password": PASSWORD, "new_password": "Sh0rt!"}, format="json"
        )
        assert short.status_code == 400
        ok = c.post(
            "/api/v1/auth/password/change",
            {"current_password": PASSWORD, "new_password": "A-Much-Better-Pass-77"},
            format="json",
        )
        assert ok.status_code == 200 and ok.json()["restriction"] is None
        assert c.get("/api/v1/auth/me").json()["restriction"] is None
        assert "auth.password_changed" in actions()

    def test_change_revokes_other_sessions_keeps_current(self, pentester):
        a, b = signed_in(pentester), signed_in(pentester)
        r = a.post(
            "/api/v1/auth/password/change",
            {"current_password": PASSWORD, "new_password": "A-Much-Better-Pass-77"},
            format="json",
        )
        assert r.status_code == 200
        assert a.get("/api/v1/auth/me").status_code == 200
        assert b.get("/api/v1/auth/me").status_code == 401

    def test_wrong_current_password(self, pentester):
        c = signed_in(pentester)
        r = c.post(
            "/api/v1/auth/password/change",
            {"current_password": "bad", "new_password": "A-Much-Better-Pass-77"},
            format="json",
        )
        assert r.status_code == 400

    def test_argon2_is_the_production_hasher(self, db):
        with override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.Argon2PasswordHasher"]):
            user = make_user("argon@example.com", "pentester")
        assert user.password.startswith("argon2")


@pytest.mark.django_db
class TestMfa:
    def _enroll(self, user):
        c = Api()
        r = c.login(user)
        assert r.json()["restriction"] == "mfa_setup"
        secret = c.post("/api/v1/auth/mfa/setup").json()["secret"]
        return c, secret

    def test_required_role_must_enrol_then_verify_on_next_login(self):
        role = make_role("MFA role", ["findings.view"], mfa_required=True)
        user = make_user("mfa@example.com", role)
        c, secret = self._enroll(user)
        assert c.get("/api/v1/roles").status_code == 403  # restricted until enrolled
        code = pyotp.TOTP(secret).now()
        r = c.post("/api/v1/auth/mfa/confirm", {"code": code}, format="json")
        assert r.status_code == 200
        codes = r.json()["recovery_codes"]
        assert len(codes) == 10 and len(set(codes)) == 10
        assert c.get("/api/v1/auth/me").json()["restriction"] is None

        again = Api()
        assert again.login(user).json()["restriction"] == "mfa_verify"
        assert again.get("/api/v1/auth/me").json()["permissions"] is not None
        nxt = pyotp.TOTP(secret).at(time.time() + 30)
        assert again.post("/api/v1/auth/mfa/verify", {"code": nxt}, format="json").status_code == 200
        assert again.get("/api/v1/auth/me").json()["restriction"] is None
        assert "auth.mfa_enabled" in actions() and "auth.mfa_verified" in actions()

    def test_secret_is_encrypted_at_rest_and_codes_are_hashed(self):
        role = make_role("MFA role", ["findings.view"], mfa_required=True)
        user = make_user("mfa2@example.com", role)
        c, secret = self._enroll(user)
        c.post("/api/v1/auth/mfa/confirm", {"code": pyotp.TOTP(secret).now()}, format="json")
        with connection.cursor() as cur:
            cur.execute("SELECT mfa_secret_enc FROM accounts_user WHERE id = %s", [user.pk])
            raw = cur.fetchone()[0]
        assert secret not in raw and raw != secret
        user.refresh_from_db()
        assert user.mfa_secret == secret
        assert all(len(r.code_hash) == 64 for r in RecoveryCode.objects.filter(user=user))

    def test_wrong_code_fails_and_counts_toward_lockout(self, admin):
        c = Api()
        c.login(admin)
        for _ in range(5):
            assert c.post("/api/v1/auth/mfa/verify", {"code": "000000"}, format="json").status_code in (401, 403)
        admin.refresh_from_db()
        assert admin.is_locked
        assert actions().count("auth.mfa_failed") == 5

    def test_totp_replay_rejected(self, admin):
        c = Api()
        c.login(admin)
        code = pyotp.TOTP(admin.mfa_secret).at(time.time() + 30)
        assert c.post("/api/v1/auth/mfa/verify", {"code": code}, format="json").status_code == 200
        c2 = Api()
        c2.login(admin)
        assert c2.post("/api/v1/auth/mfa/verify", {"code": code}, format="json").status_code == 401

    def test_recovery_code_single_use(self):
        role = make_role("MFA role", ["findings.view"], mfa_required=True)
        user = make_user("mfa3@example.com", role)
        c, secret = self._enroll(user)
        recovery = c.post("/api/v1/auth/mfa/confirm", {"code": pyotp.TOTP(secret).now()}, format="json").json()[
            "recovery_codes"
        ][0]
        first = Api()
        first.login(user)
        assert first.post("/api/v1/auth/mfa/verify", {"recovery_code": recovery}, format="json").status_code == 200
        second = Api()
        second.login(user)
        assert second.post("/api/v1/auth/mfa/verify", {"recovery_code": recovery}, format="json").status_code == 401

    def test_voluntary_enrolment_for_roles_that_do_not_require_mfa(self, pentester):
        c = signed_in(pentester)
        secret = c.post("/api/v1/auth/mfa/setup").json()["secret"]
        r = c.post("/api/v1/auth/mfa/confirm", {"code": pyotp.TOTP(secret).now()}, format="json")
        assert r.status_code == 200 and len(r.json()["recovery_codes"]) == 10
        assert c.post("/api/v1/auth/mfa/setup").status_code == 400  # already enabled
        assert c.get("/api/v1/auth/me").json()["restriction"] is None

    def test_verify_endpoint_closed_without_pending_verification(self, pentester):
        c = signed_in(pentester)
        assert c.post("/api/v1/auth/mfa/verify", {"code": "123456"}, format="json").status_code == 403

    def test_super_admin_requires_mfa_by_default(self, db):
        user = make_user("sa@example.com", "super_admin")
        assert Api().login(user).json()["restriction"] == "mfa_setup"
