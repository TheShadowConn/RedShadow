import pytest
from django.conf import settings
from rest_framework.test import APIClient

from tests.conftest import make_user, signed_in


@pytest.mark.django_db
class TestAbout:
    def test_signed_in_user_gets_build_facts(self, admin):
        r = signed_in(admin).get("/api/v1/about")
        assert r.status_code == 200
        body = r.json()
        assert body["name"] == "RedShadow"
        assert body["version"] == settings.APP_VERSION
        assert set(body) == {"name", "version", "build", "build_date", "django", "python", "backup"}

    @pytest.mark.parametrize("role", ["pentester", "remediation"])
    def test_other_roles_can_read(self, role):
        user = make_user(f"{role}@x.test", role=role)
        assert signed_in(user).get("/api/v1/about").status_code == 200

    def test_anonymous_refused(self, db):
        assert APIClient().get("/api/v1/about").status_code in (401, 403)
