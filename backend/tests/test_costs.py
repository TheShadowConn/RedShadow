"""Engagement costs: multi-currency lines, platform permission, scoping, audit, admin dashboard totals."""

from decimal import Decimal

import pytest

from apps.audit.models import AuditEvent
from apps.rbac.catalogue import PERMISSIONS
from tests.conftest import make_role, make_user, signed_in
from tests.test_findings import API
from tests.world import build_world


@pytest.fixture
def w(admin):
    return build_world(admin)


def curl(eng, cost=None):
    return f"{API}/engagements/{eng.pk}/costs" + (f"/{cost}" if cost else "")


def line(**over):
    return {"amount": "1500.50", "currency": "USD", "category": "labour", "description": "Testing", "incurred_on": "2026-11-01", **over}


def test_permissions_are_platform_and_admin_only_by_default(admin):
    assert PERMISSIONS["engagement_costs.view"][0] == "platform"
    assert PERMISSIONS["engagement_costs.manage"][0] == "platform"
    for role in ("pentester", "remediation", "external_vendor"):
        from apps.rbac.models import Role

        codes = set(Role.objects.get(system_key=role).permissions.values_list("code", flat=True))
        assert not codes & {"engagement_costs.view", "engagement_costs.manage"}


def test_multi_currency_totals(w, admin_client):
    for body in (line(), line(amount="500", category="tools"), line(amount="2000", currency="EUR"), line(amount="10", currency="INR")):
        assert admin_client.post(curl(w.eng_a), body, format="json").status_code == 201
    data = admin_client.get(curl(w.eng_a)).json()
    totals = {t["currency"]: Decimal(t["total"]) for t in data["totals"]}
    assert totals == {"USD": Decimal("2000.50"), "EUR": Decimal("2000"), "INR": Decimal("10")}
    assert len(data["items"]) == 4
    assert admin_client.get(curl(w.eng_b)).json()["items"] == []


def test_validation(w, admin_client):
    for bad in (line(amount="0"), line(amount="-5"), line(currency="XXX"), line(category="nope"), line(incurred_on="x"), {**line(), "extra": 1}):
        assert admin_client.post(curl(w.eng_a), bad, format="json").status_code == 400, bad


def test_update_delete_and_audit(w, admin_client):
    cid = admin_client.post(curl(w.eng_a), line(), format="json").json()["id"]
    r = admin_client.patch(curl(w.eng_a, cid), {"amount": "99.00", "currency": "GBP"}, format="json")
    assert r.status_code == 200 and r.json()["currency"] == "GBP"
    assert admin_client.delete(curl(w.eng_a, cid)).status_code == 204
    assert admin_client.get(curl(w.eng_a)).json()["items"] == []
    actions = set(AuditEvent.objects.filter(action__startswith="engagement.cost_").values_list("action", flat=True))
    assert actions == {"engagement.cost_added", "engagement.cost_updated", "engagement.cost_deleted"}


def test_cost_line_of_another_engagement_is_404(w, admin_client):
    cid = admin_client.post(curl(w.eng_a), line(), format="json").json()["id"]
    assert admin_client.patch(curl(w.eng_b, cid), {"amount": "1"}, format="json").status_code == 404
    assert admin_client.delete(curl(w.eng_b, cid)).status_code == 404


def test_archived_engagement_is_read_only(w, admin_client):
    w.eng_a.status = "completed"
    w.eng_a.save()
    assert admin_client.post(f"{API}/engagements/{w.eng_a.pk}/archive", {"version": 1}, format="json").status_code == 200
    assert admin_client.post(curl(w.eng_a), line(), format="json").status_code == 409


@pytest.mark.parametrize("who", ["p1", "r1"])
def test_staff_without_permission_denied(w, who):
    client = signed_in(getattr(w, who))
    assert client.get(curl(w.eng_a)).status_code == 403
    assert client.post(curl(w.eng_a), line(), format="json").status_code == 403


def test_custom_role_view_only(w, admin_client):
    role = make_role("Finance", ["engagement_costs.view", "engagements.view", "dashboards.admin"], all_engagements=True)
    user = make_user("fin@example.com", role)
    admin_client.post(curl(w.eng_a), line(), format="json")
    client = signed_in(user)
    assert client.get(curl(w.eng_a)).status_code == 200
    assert client.post(curl(w.eng_a), line(), format="json").status_code == 403
    dash = client.get(f"{API}/dashboards/admin").json()
    assert dash["costs"]["totals"][0]["currency"] == "USD"


def test_admin_dashboard_totals_and_hidden_without_permission(w, admin_client):
    admin_client.post(curl(w.eng_a), line(amount="100"), format="json")
    admin_client.post(curl(w.eng_a), line(amount="50", currency="EUR"), format="json")
    admin_client.post(curl(w.eng_b), line(amount="25"), format="json")
    costs = admin_client.get(f"{API}/dashboards/admin").json()["costs"]
    assert {t["currency"]: Decimal(t["total"]) for t in costs["totals"]} == {"USD": Decimal("125"), "EUR": Decimal("50")}
    assert costs["top"][0]["engagement"]["ref"] == w.eng_a.ref
    role = make_role("Dash only", ["dashboards.admin", "engagements.view"], all_engagements=True)
    client = signed_in(make_user("dash@example.com", role))
    assert client.get(f"{API}/dashboards/admin").json()["costs"] is None
