import pytest
from django.test import Client

from apps.core import views


@pytest.fixture
def client():
    return Client()


def test_live_ok_without_auth(client):
    r = client.get("/api/v1/health/live")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.django_db
def test_ready_ok(client):
    r = client.get("/api/v1/health/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "checks": {"database": "ok", "redis": "ok"}}


def test_ready_503_when_redis_down(client, monkeypatch):
    monkeypatch.setattr(views.ReadyView, "_database", staticmethod(lambda: "ok"))
    monkeypatch.setattr(views.ReadyView, "_redis", staticmethod(lambda: "fail"))
    r = client.get("/api/v1/health/ready")
    assert r.status_code == 503
    assert r.json()["checks"]["redis"] == "fail"


def test_ready_does_not_leak_error_details(client, monkeypatch):
    def boom():
        raise RuntimeError("password=hunter2 host=db")

    monkeypatch.setattr(views.connection, "cursor", boom)
    monkeypatch.setattr(views.ReadyView, "_redis", staticmethod(lambda: "ok"))
    r = client.get("/api/v1/health/ready")
    assert r.status_code == 503
    assert "hunter2" not in r.content.decode()


def test_request_id_generated_and_echoed(client):
    r = client.get("/api/v1/health/live")
    assert len(r["X-Request-ID"]) == 32
    r2 = client.get("/api/v1/health/live", headers={"X-Request-ID": "abcd1234-trace"})
    assert r2["X-Request-ID"] == "abcd1234-trace"


def test_invalid_request_id_replaced(client):
    r = client.get("/api/v1/health/live", headers={"X-Request-ID": "bad id;<script>"})
    assert r["X-Request-ID"] != "bad id;<script>"


def test_unknown_route_returns_error_envelope(client):
    r = client.get("/api/v1/nope")
    assert r.status_code == 404
    err = r.json()["error"]
    assert err["code"] == "not_found"
    assert err["request_id"] == r["X-Request-ID"]


def test_health_rejects_post(client):
    r = client.post("/api/v1/health/live")
    assert r.status_code == 405
    assert r.json()["error"]["code"] == "method_not_allowed"
