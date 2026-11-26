"""Asset tags: filter, catalogue, counts, add and remove on many assets, rename, delete, permissions."""

import pytest

from apps.audit.models import AuditEvent
from apps.organisations import services as org_services
from apps.organisations.models import Asset
from tests.conftest import signed_in
from tests.test_findings import API
from tests.world import build_world


@pytest.fixture
def w(admin):
    w = build_world(admin)
    w.admin = admin
    return w


def make(w, name, tags, org=None, pending=False):
    asset = org_services.create_asset(None, w.admin, org or w.org_a, {"name": name, "type": "host", "tags": tags})
    if pending:
        Asset.objects.filter(pk=asset.pk).update(onboarding_status="pending")
    return asset


def tags_of(asset):
    asset.refresh_from_db()
    return asset.tags


def names(response):
    return {a["name"] for a in response.json()["results"]}


def post(client, path, body):
    return client.post(f"{API}/assets/tags/{path}", body, format="json")


@pytest.mark.django_db
class TestRead:
    def test_filter_is_exact_and_ignores_case(self, w, admin_client):
        make(w, "A", ["Service-Delivery"])
        make(w, "B", ["service-delivery-uk"])
        assert names(admin_client.get(f"{API}/assets?tag=service-delivery")) == {"A"}
        assert names(admin_client.get(f"{API}/assets?tag=service")) == set()

    def test_counts_follow_tag_and_organisation(self, w, admin_client):
        make(w, "A", ["sd"])
        make(w, "B", ["SD"], pending=True)
        make(w, "C", ["sd"], org=w.org_b)
        archived = make(w, "D", ["sd"])
        org_services.set_asset_archived(None, w.admin, archived, True)
        summary = admin_client.get(f"{API}/assets/summary?tag=sd&organisation={w.org_a.pk}").json()
        assert summary == {"total": 2, "onboarded": 1, "pending": 1, "archived": 1}
        (row,) = admin_client.get(f"{API}/assets/tags").json()
        assert (row["tag"].lower(), row["assets"], row["onboarded"], row["archived"]) == ("sd", 3, 2, 1)

    def test_catalogue_and_filter_stay_inside_the_callers_scope(self, w):
        w.asset_a.tags, w.asset_b.tags = ["mine"], ["theirs"]
        w.asset_a.save()
        w.asset_b.save()
        client = signed_in(w.p1)
        assert [r["tag"] for r in client.get(f"{API}/assets/tags").json()] == ["mine"]
        assert client.get(f"{API}/assets?tag=theirs").json()["count"] == 0
        assert client.get(f"{API}/assets/summary?tag=theirs").json()["total"] == 0


@pytest.mark.django_db
class TestAssign:
    def test_add_and_remove_on_many_assets(self, w, admin_client):
        a, b = make(w, "A", ["old"]), make(w, "B", ["Dev"])
        r = post(admin_client, "assign", {"ids": [str(a.pk), str(b.pk)], "add": ["dev", "Dev"], "remove": ["OLD"]})
        assert r.status_code == 200, r.content
        assert tags_of(a) == ["Dev"] and tags_of(b) == ["Dev"]
        assert r.json() == {"updated": 1, "skipped": [], "not_found": 0}
        assert AuditEvent.objects.filter(action="asset.updated", entity_id=str(a.pk)).exists()

    def test_archived_and_full_assets_are_skipped_with_a_reason(self, w, admin_client):
        full = make(w, "Full", [f"t{i}" for i in range(20)])
        archived = make(w, "Old", [])
        org_services.set_asset_archived(None, w.admin, archived, True)
        r = post(admin_client, "assign", {"ids": [str(full.pk), str(archived.pk)], "add": ["new"]}).json()
        assert r["updated"] == 0 and {s["name"] for s in r["skipped"]} == {"Full", "Old"}
        assert tags_of(archived) == [] and len(tags_of(full)) == 20

    def test_full_asset_can_still_swap_one_tag(self, w, admin_client):
        full = make(w, "Full", [f"t{i}" for i in range(20)])
        r = post(admin_client, "assign", {"ids": [str(full.pk)], "add": ["new"], "remove": ["t0"]}).json()
        assert r["updated"] == 1 and "new" in tags_of(full)

    @pytest.mark.parametrize(
        "body",
        [{"add": ["a,b"]}, {"add": ["a;b"]}, {"add": [""]}, {"add": ["x" * 41]}, {}, {"add": [], "remove": []}],
    )
    def test_bad_input_is_400(self, w, admin_client, body):
        r = post(admin_client, "assign", {"ids": [str(w.asset_a.pk)], **body})
        assert r.status_code == 400, r.content


@pytest.mark.django_db
class TestRenameAndDelete:
    def test_rename_merges_and_keeps_other_tags(self, w, admin_client):
        a, b = make(w, "A", ["sd", "x"]), make(w, "B", ["SD", "Service-Delivery"])
        r = post(admin_client, "rename", {"tag": "sd", "new_name": "service-delivery"})
        assert r.status_code == 200 and r.json()["updated"] == 2, r.content
        assert tags_of(a) == ["service-delivery", "x"] and tags_of(b) == ["service-delivery"]

    def test_rename_can_change_only_the_case(self, w, admin_client):
        a = make(w, "A", ["devops"])
        assert post(admin_client, "rename", {"tag": "devops", "new_name": "DevOps"}).json()["updated"] == 1
        assert tags_of(a) == ["DevOps"]

    def test_delete_within_one_organisation(self, w, admin_client):
        a, c = make(w, "A", ["sd", "keep"]), make(w, "C", ["sd"], org=w.org_b)
        r = post(admin_client, "delete", {"tag": "sd", "organisation": str(w.org_a.pk)})
        assert r.status_code == 200 and r.json()["updated"] == 1
        assert tags_of(a) == ["keep"] and tags_of(c) == ["sd"]
        assert Asset.objects.filter(pk=a.pk).exists()

    def test_archived_assets_are_left_alone_and_reported(self, w, admin_client):
        a = make(w, "A", ["sd"])
        org_services.set_asset_archived(None, w.admin, a, True)
        r = post(admin_client, "delete", {"tag": "sd"}).json()
        assert r["updated"] == 0 and r["skipped"][0]["name"] == "A" and tags_of(a) == ["sd"]

    def test_unknown_tag_is_404(self, w, admin_client):
        assert post(admin_client, "rename", {"tag": "nope", "new_name": "x"}).status_code == 404
        assert post(admin_client, "delete", {"tag": "nope"}).status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize("who", ["p1", "r1"])
def test_only_asset_editors_change_tags(w, who):
    w.asset_a.tags = ["mine"]
    w.asset_a.save()
    client = signed_in(getattr(w, who))
    assert post(client, "assign", {"ids": [str(w.asset_a.pk)], "add": ["x"]}).status_code == 403
    assert post(client, "rename", {"tag": "mine", "new_name": "x"}).status_code == 403
    assert post(client, "delete", {"tag": "mine"}).status_code == 403
    assert tags_of(w.asset_a) == ["mine"]
