"""Tags as groups: one spelling per organisation, the untagged filter, scope links, template and import."""

import pytest

from apps.organisations import services as org_services
from apps.organisations.models import Asset
from tests.test_asset_tags import make, names, tags_of
from tests.test_asset_tags import w as w  # noqa: F401  (fixture)
from tests.test_findings import API


@pytest.mark.django_db
class TestSpelling:
    def test_create_reuses_the_spelling_in_use(self, w, admin_client):
        make(w, "A", ["IT Help Desk"])
        assert tags_of(make(w, "B", [" it help desk ", "IT HELP DESK", "Network"])) == ["IT Help Desk", "Network"]

    def test_edit_reuses_spelling_but_sole_holder_can_change_it(self, w, admin_client):
        make(w, "A", ["IT Help Desk"])
        b = make(w, "B", ["netops"])
        org_services.update_asset(None, w.admin, b, {"tags": ["it help desk", "NetOps"]})
        assert tags_of(b) == ["IT Help Desk", "NetOps"]


@pytest.mark.django_db
def test_untagged_filter(w, admin_client):
    make(w, "Tagged", ["x"])
    make(w, "Plain", [])
    found = names(admin_client.get(f"{API}/assets?untagged=true&organisation={w.org_a.pk}"))
    assert "Plain" in found and "Tagged" not in found
    summary = admin_client.get(f"{API}/assets/summary?untagged=true&organisation={w.org_a.pk}").json()
    assert summary["total"] == len(found)


@pytest.mark.django_db
def test_scope_links_carry_tags(w, admin_client):
    Asset.objects.filter(pk=w.asset_a.pk).update(tags=["Network Engineering"])
    rows = []
    for engagement in w.asset_a.engagement_assets.values_list("engagement_id", flat=True):
        rows += admin_client.get(f"{API}/engagements/{engagement}/assets").json()
    assert ["Network Engineering"] in [r["asset"]["tags"] for r in rows]
