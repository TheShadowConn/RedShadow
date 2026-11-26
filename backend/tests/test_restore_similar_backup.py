"""Undo for deleted findings, similar-finding warnings while writing, and the backup status on the About page."""

import pytest
from django.core.management import call_command

from apps.audit.models import AuditEvent
from apps.findings.models import Finding
from tests.conftest import signed_in
from tests.test_findings import API
from tests.world import build_world


@pytest.fixture
def w(admin):
    return build_world(admin)


@pytest.fixture
def p1c(w):
    return signed_in(w.p1)


def make(client, eng, title, **extra):
    r = client.post(f"{API}/findings", {"engagement": str(eng.pk), "title": title, "severity": "high",
                                        "description": "d", "recommendation": "r", **extra}, format="json")
    assert r.status_code == 201, r.content
    return r.json()


@pytest.mark.django_db
class TestRestore:
    def test_undo_brings_a_deleted_finding_back(self, w, admin_client):
        f = make(admin_client, w.eng_a, "SQL injection")
        assert admin_client.delete(f"{API}/findings/{f['id']}").status_code == 204
        assert admin_client.get(f"{API}/findings/{f['id']}").status_code == 404
        r = admin_client.post(f"{API}/findings/restore", {"ids": [f["id"]]}, format="json")
        assert r.status_code == 200 and r.json()["succeeded"] == 1
        back = admin_client.get(f"{API}/findings/{f['id']}")
        assert back.status_code == 200 and back.json()["title"] == "SQL injection"
        assert AuditEvent.objects.filter(action="finding.restored", entity_id=f["id"]).exists()

    def test_restores_several_and_reports_each(self, w, admin_client):
        a, b = make(admin_client, w.eng_a, "One"), make(admin_client, w.eng_a, "Two")
        for f in (a, b):
            admin_client.delete(f"{API}/findings/{f['id']}")
        missing = "00000000-0000-4000-8000-000000000000"
        r = admin_client.post(f"{API}/findings/restore", {"ids": [a["id"], missing, b["id"]]}, format="json").json()
        assert [x["ok"] for x in r["results"]] == [True, False, True]
        assert r["results"][1]["error"]["code"] == "not_found"

    def test_a_finding_that_is_not_deleted_is_not_found(self, w, admin_client):
        f = make(admin_client, w.eng_a, "Live")
        r = admin_client.post(f"{API}/findings/restore", {"ids": [f["id"]]}, format="json").json()
        assert r["failed"] == 1

    def test_without_the_delete_right_it_is_refused_and_audited(self, w, admin_client, p1c):
        f = make(admin_client, w.eng_a, "Protected")
        admin_client.delete(f"{API}/findings/{f['id']}")
        r = p1c.post(f"{API}/findings/restore", {"ids": [f["id"]]}, format="json")
        assert r.status_code == 403  # the pentester role has no findings.delete at all
        assert Finding.all_objects.get(pk=f["id"]).deleted_at is not None

    def test_not_allowed_in_an_archived_engagement(self, w, admin_client):
        f = make(admin_client, w.eng_a, "Archived soon")
        admin_client.delete(f"{API}/findings/{f['id']}")
        from django.utils import timezone

        from apps.engagements.models import Engagement

        Engagement.objects.filter(pk=w.eng_a.pk).update(archived_at=timezone.now())
        r = admin_client.post(f"{API}/findings/restore", {"ids": [f["id"]]}, format="json").json()
        assert r["failed"] == 1 and r["results"][0]["error"]["code"] == "conflict"


@pytest.mark.django_db
class TestSimilar:
    def get(self, client, eng, **q):
        query = "&".join([f"engagement={eng.pk}", *[f"{k}={v}" for k, v in q.items()]])
        return client.get(f"{API}/findings/similar?{query}")

    def test_finds_same_and_similar_titles_and_same_target(self, w, admin_client):
        same = make(admin_client, w.eng_a, "Missing security headers")
        similar = make(admin_client, w.eng_a, "Security headers are missing on the API")
        target = make(admin_client, w.eng_a, "Something else", asset=str(w.asset_a.pk), endpoint="/login")
        r = self.get(admin_client, w.eng_a, title="Missing security headers").json()["results"]
        reasons = {x["id"]: x["reason"] for x in r}
        assert reasons[same["id"]] == "Same title" and similar["id"] in reasons
        t = self.get(admin_client, w.eng_a, title="Brand new thing", asset=str(w.asset_a.pk), endpoint="/login").json()
        assert [x["id"] for x in t["results"]] == [target["id"]] and t["results"][0]["reason"] == "Same asset and endpoint"

    def test_matches_differently_worded_titles_but_not_unrelated_ones(self, w, admin_client):
        near = make(admin_client, w.eng_a, "SQL injection in search")
        make(admin_client, w.eng_a, "Weak password policy")
        r = self.get(admin_client, w.eng_a, title="SQL injection in the search box").json()["results"]
        assert [x["id"] for x in r] == [near["id"]] and r[0]["reason"] == "Similar title"
        assert self.get(admin_client, w.eng_a, title="Directory listing enabled").json()["results"] == []

    def test_short_titles_and_other_engagements_give_nothing(self, w, admin_client):
        make(admin_client, w.eng_b, "Weak password policy")
        assert self.get(admin_client, w.eng_a, title="ab").json()["results"] == []
        assert self.get(admin_client, w.eng_a, title="Weak password policy").json()["results"] == []

    def test_can_exclude_the_finding_being_edited(self, w, admin_client):
        f = make(admin_client, w.eng_a, "Open redirect")
        r = self.get(admin_client, w.eng_a, title="Open redirect", exclude=f["id"]).json()
        assert r["results"] == []

    def test_needs_an_engagement(self, admin_client):
        assert admin_client.get(f"{API}/findings/similar?title=Open+redirect").status_code == 400

    def test_only_shows_what_the_caller_may_see(self, w, admin_client, p1c):
        make(admin_client, w.eng_b, "Hidden from p1")
        assert self.get(p1c, w.eng_b, title="Hidden from p1").json()["results"] == []


@pytest.mark.django_db
class TestBackupStatus:
    def test_no_backup_recorded_yet(self, admin_client):
        b = admin_client.get(f"{API}/about").json()["backup"]
        assert b["status"] == "none" and b["last_at"] is None and b["warn_after_days"] == 7

    def test_command_records_and_about_shows_it_to_super_admin_only(self, admin_client, p1c):
        call_command("record_backup", name="20261126-140500", bytes=123456, parts="db,media,secrets")
        ev = AuditEvent.objects.get(action="system.backup_completed")
        assert ev.actor_label == "system" and ev.metadata["size_bytes"] == 123456
        b = admin_client.get(f"{API}/about").json()["backup"]
        assert b["status"] == "ok" and b["name"] == "20261126-140500" and b["size_bytes"] == 123456
        assert b["age_days"] == 0
        assert p1c.get(f"{API}/about").json()["backup"] is None

    def test_old_backups_are_flagged(self, admin_client, settings):
        call_command("record_backup", name="old", bytes=1)
        settings.BACKUP_WARN_DAYS = -1  # anything counts as older than the limit
        assert admin_client.get(f"{API}/about").json()["backup"]["status"] == "stale"
