"""Section E: notifications are created with the change, readable only by the recipient."""

import pytest

from apps.notifications.models import Notification
from tests.conftest import make_user, signed_in
from tests.test_findings import furl, make, publish
from tests.world import build_world

API = "/api/v1"


@pytest.fixture
def w(admin):
    return build_world(admin)


def mine(user, kind=None):
    qs = Notification.objects.filter(recipient=user)
    return qs.filter(kind=kind) if kind else qs


@pytest.mark.django_db
class TestTriggers:
    def test_lead_on_create_is_notified_not_the_actor(self, w, admin):
        assert mine(w.p1, "engagement.lead").count() == 1
        assert mine(admin).count() == 0

    def test_lead_change_notifies_new_and_old_lead(self, admin_client, w):
        admin_client.post(f"{API}/engagements/{w.eng_a.pk}/lead", {"lead": str(w.p3.pk), "version": 1}, format="json")
        assert mine(w.p3, "engagement.lead").count() == 1
        assert mine(w.p1, "engagement.lead_removed").count() == 1
        assert mine(w.p3, "engagement.added").count() == 1

    def test_member_added_removed_and_status(self, admin_client, w):
        admin_client.post(f"{API}/engagements/{w.eng_b.pk}/members", {"user": str(w.p3.pk)}, format="json")
        assert mine(w.p3, "engagement.added").count() == 1
        admin_client.post(
            f"{API}/engagements/{w.eng_b.pk}/status", {"status": "scheduled", "version": 1}, format="json"
        )
        assert mine(w.p3, "engagement.status").count() == 1 and mine(w.p2, "engagement.status").count() == 1
        admin_client.delete(f"{API}/engagements/{w.eng_b.pk}/members/{w.p3.pk}")
        assert mine(w.p3, "engagement.removed").count() == 1

    def test_finding_assignment_status_and_comment(self, w, admin_client):
        p1c = signed_in(w.p1)
        f = make(p1c, w.eng_a, remediation_owner=str(w.r1.pk))
        assert mine(w.r1, "finding.assigned").count() == 1 and mine(w.p1).filter(kind="finding.assigned").count() == 0
        f = publish(p1c, f)
        assert mine(w.r1, "finding.status").count() == 1  # the publish, made by the pentester
        r1c = signed_in(w.r1)
        r = r1c.post(furl(f, "/transition"), {"to": "in_progress", "version": f["version"]}, format="json")
        assert r.status_code == 200, r.content
        assert mine(w.p1, "finding.status").count() == 1
        assert mine(w.r1, "finding.status").count() == 1  # the actor is never notified of their own move

    def test_no_notification_for_inactive_user(self, w):
        w.p3.is_active = False
        w.p3.save()
        from apps.notifications.services import notify

        assert notify([w.p3], "x", "t") == 0


@pytest.mark.django_db
class TestApi:
    def test_list_count_read_and_isolation(self, w):
        c = signed_in(w.p1)
        n = mine(w.p1).first()
        assert n is not None
        assert c.get(f"{API}/notifications/unread-count").json()["count"] >= 1
        listed = c.get(f"{API}/notifications").json()["results"]
        assert listed and set(listed[0]) == {"id", "kind", "title", "body", "link", "actor", "read", "created_at"}
        other = signed_in(w.p2)
        assert other.post(f"{API}/notifications/{n.pk}/read", {}, format="json").status_code == 404
        assert all(x["id"] != str(n.pk) for x in other.get(f"{API}/notifications").json()["results"])
        assert c.post(f"{API}/notifications/{n.pk}/read", {}, format="json").status_code == 200
        n.refresh_from_db()
        assert n.read_at is not None
        assert c.post(f"{API}/notifications/not-a-uuid/read", {}, format="json").status_code == 404

    def test_read_all_and_unread_filter(self, w):
        c = signed_in(w.p1)
        assert c.post(f"{API}/notifications/read-all", {}, format="json").json()["marked"] >= 1
        assert c.get(f"{API}/notifications/unread-count").json()["count"] == 0
        assert c.get(f"{API}/notifications?unread=true").json()["count"] == 0

    def test_anonymous_is_refused(self, client):
        assert client.get(f"{API}/notifications").status_code in (401, 403)

    def test_deleted_user_notifications_go_with_them(self, w):
        u = make_user("gone@example.com", "pentester")
        Notification.objects.create(recipient=u, kind="x", title="t")
        u.delete()
        assert not Notification.objects.filter(kind="x").exists()


@pytest.mark.django_db
class TestSweeps:
    def test_due_soon_overdue_once_and_prune(self, w):
        import datetime

        from django.utils import timezone

        from apps.findings import services as fsvc
        from apps.findings.models import Finding
        from apps.findings.tasks import due_soon_sweep, sla_sweep
        from apps.notifications.tasks import prune

        p1c = signed_in(w.p1)
        f = publish(p1c, make(p1c, w.eng_a, remediation_owner=str(w.r1.pk)))
        today = timezone.localdate()
        Finding.objects.filter(pk=f["id"]).update(due_date=today + datetime.timedelta(days=2))
        assert due_soon_sweep() == 1 and due_soon_sweep() == 0
        assert mine(w.r1, "finding.due_soon").count() == 1 and mine(w.p1, "finding.due_soon").count() == 1
        Finding.objects.filter(pk=f["id"]).update(due_date=today - datetime.timedelta(days=1))
        assert sla_sweep() == 1 and sla_sweep() == 0
        assert mine(w.r1, "finding.overdue").count() == 1
        assert fsvc.DUE_SOON_DAYS == 3
        old = timezone.now() - datetime.timedelta(days=120)
        stale = mine(w.r1).first()
        Notification.objects.filter(pk=stale.pk).update(read_at=old, created_at=old)
        keep = mine(w.r1).exclude(pk=stale.pk).first()
        assert prune() == 1 and Notification.objects.filter(pk=keep.pk).exists()


@pytest.mark.django_db
class TestSettings:
    def test_defaults_update_and_mute(self, w, admin_client):
        c = signed_in(w.p3)
        got = c.get(f"{API}/notifications/settings").json()
        assert got["muted"] == [] and got["email_enabled"] is False and got["email_available"] is False
        r = c.put(f"{API}/notifications/settings", {"muted": ["engagement"], "email_enabled": False}, format="json")
        assert r.status_code == 200 and r.json()["muted"] == ["engagement"]
        admin_client.post(f"{API}/engagements/{w.eng_b.pk}/members", {"user": str(w.p3.pk)}, format="json")
        assert mine(w.p3, "engagement.added").count() == 0
        signed_in(w.p3).put(f"{API}/notifications/settings", {"muted": [], "email_enabled": False}, format="json")
        admin_client.delete(f"{API}/engagements/{w.eng_b.pk}/members/{w.p3.pk}")
        admin_client.post(f"{API}/engagements/{w.eng_b.pk}/members", {"user": str(w.p3.pk)}, format="json")
        assert mine(w.p3, "engagement.added").count() == 1

    def test_validation_and_isolation(self, w):
        c = signed_in(w.p3)
        assert (
            c.put(
                f"{API}/notifications/settings", {"muted": ["nope"], "email_enabled": False}, format="json"
            ).status_code
            == 400
        )
        assert c.put(f"{API}/notifications/settings", {"muted": []}, format="json").status_code == 400
        c.put(f"{API}/notifications/settings", {"muted": ["findings"], "email_enabled": True}, format="json")
        assert signed_in(w.p2).get(f"{API}/notifications/settings").json()["muted"] == []

    def test_email_sent_only_when_enabled_and_opted_in(
        self, w, settings, mailoutbox, django_capture_on_commit_callbacks
    ):
        settings.EMAIL_ENABLED = True
        signed_in(w.p3).put(f"{API}/notifications/settings", {"muted": [], "email_enabled": True}, format="json")
        from apps.notifications.services import notify

        with django_capture_on_commit_callbacks(execute=True):
            notify([w.p3, w.p2], "finding.assigned", "F-1 was assigned to you", body="t", link="/findings/1")
        assert [m.to for m in mailoutbox] == [[w.p3.email]]
        with django_capture_on_commit_callbacks(execute=True):
            notify([w.p3], "engagement.status", "status")  # not an email group
        assert len(mailoutbox) == 1
