import pytest
from django.core.exceptions import ImproperlyConfigured
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from apps.core.logs import redact
from apps.core.secrets import secret
from apps.core.tasks import ping


def test_secret_reads_file(tmp_path, monkeypatch):
    f = tmp_path / "s"
    f.write_text("abc123\n")
    monkeypatch.setenv("X_TEST_FILE", str(f))
    assert secret("X_TEST") == "abc123"


def test_secret_env_fallback_and_missing(monkeypatch):
    monkeypatch.delenv("X_TEST_FILE", raising=False)
    monkeypatch.setenv("X_TEST", "v")
    assert secret("X_TEST") == "v"
    monkeypatch.delenv("X_TEST")
    with pytest.raises(ImproperlyConfigured):
        secret("X_TEST")


def test_secret_unreadable_file(monkeypatch):
    monkeypatch.setenv("X_TEST_FILE", "/nonexistent/file")
    with pytest.raises(ImproperlyConfigured):
        secret("X_TEST")


@pytest.mark.parametrize(
    "raw",
    ["password=hunter2", 'token: "abc.def"', "Authorization=Bearer", "api_key=zzz&x=1"],
)
def test_redact_masks_values(raw):
    out = redact(raw)
    assert "[REDACTED]" in out
    for leaked in ("hunter2", "abc.def", "zzz"):
        assert leaked not in out


def test_ping_task():
    assert ping() == "pong"


def test_default_permission_denies_by_default():
    class Protected(APIView):
        permission_classes = [IsAuthenticated]

        def get(self, request):
            return Response({})

    request = APIRequestFactory().get("/x")
    request.session = {}  # no signed-in user
    response = Protected.as_view()(request)
    assert response.status_code == 401
    assert response.data["error"]["code"] == "not_authenticated"
