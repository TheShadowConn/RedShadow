import pyotp
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.rbac.models import Permission, Role, RolePermission

PASSWORD = "Correct-Horse-Battery-9"
# Fixed test-only TOTP secret: 32 base32 characters (160 bits). pyotp rejects secrets under 112 bits.
TEST_MFA_SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"
SAFE = {"GET", "HEAD", "OPTIONS"}


class Api(APIClient):
    """API client that enforces real CSRF and sends the token like the SPA does."""

    def __init__(self):
        super().__init__(enforce_csrf_checks=True)
        self._csrf = None

    def request(self, **kwargs):
        if kwargs.get("REQUEST_METHOD", "GET") not in SAFE:
            if self._csrf is None:
                self._csrf = super().request(REQUEST_METHOD="GET", PATH_INFO="/api/v1/auth/csrf").json()["csrfToken"]
            kwargs["HTTP_X_CSRFTOKEN"] = self._csrf
        return super().request(**kwargs)

    def login(self, user, password=PASSWORD):
        r = self.post("/api/v1/auth/login", {"email": user.email, "password": password}, format="json")
        assert r.status_code == 200, r.content
        return r


@pytest.fixture
def api():
    return Api()


def make_user(email="user@example.com", role="pentester", password=PASSWORD, **extra):
    role_obj = role if isinstance(role, Role) else Role.objects.get(system_key=role)
    extra.setdefault("display_name", email.split("@")[0])
    extra.setdefault("must_change_password", False)
    user = User(email=email, role=role_obj, **extra)
    user.set_password(password)
    user.save()
    return user


def make_role(name, codes=(), **flags):
    role = Role.objects.create(name=name, **flags)
    RolePermission.objects.bulk_create(
        [RolePermission(role=role, permission=Permission.objects.get(code=c)) for c in codes]
    )
    return role


def signed_in(user, password=PASSWORD):
    client = Api()
    client.login(user, password)
    if user.mfa_enabled:
        User.objects.filter(pk=user.pk).update(mfa_last_step=0)  # test helper: allow repeat sign-ins
        code = pyotp.TOTP(user.mfa_secret).now()
        r = client.post("/api/v1/auth/mfa/verify", {"code": code}, format="json")
        assert r.status_code == 200, r.content
    return client


@pytest.fixture
def admin(db):
    return make_user("admin@example.com", "super_admin", mfa_enabled=True, **_mfa(TEST_MFA_SECRET))


def _mfa(secret):
    from apps.accounts import crypto

    return {"mfa_secret_enc": crypto.encrypt(secret)}


@pytest.fixture
def admin_client(admin):
    return signed_in(admin)


@pytest.fixture
def pentester(db):
    return make_user("pen@example.com", "pentester")


@pytest.fixture
def remediation(db):
    return make_user("rem@example.com", "remediation")
