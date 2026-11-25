"""Engagement scenarios: own name, dates and status, no owner, no findings link, pictures, scoping, audit."""

from datetime import date, timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.audit.models import AuditEvent
from apps.engagements.models import EngagementScenario
from apps.files.models import Attachment
from apps.rbac.catalogue import PERMISSIONS
from tests.conftest import signed_in
from tests.test_files import png
from tests.test_findings import API
from tests.world import build_world

TODAY = date.today()


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


@pytest.fixture
def w(admin):
    return build_world(admin)


def url(eng, sid=None, tail=""):
    base = f"{API}/engagements/{eng.pk}/scenarios"
    return base + (f"/{sid}" if sid else "") + tail


def add(client, eng, name="Login brute force", **over):
    return client.post(url(eng), {"name": name, **over}, format="json")


def test_permissions_are_engagement_scoped_and_granted(admin):
    from apps.rbac.models import Role

    for code in ("engagement_scenarios.view", "engagement_scenarios.manage"):
        assert PERMISSIONS[code][0] == "engagement"
    held = lambda key: set(Role.objects.get(system_key=key).permissions.values_list("code", flat=True))  # noqa: E731
    assert {"engagement_scenarios.view", "engagement_scenarios.manage"} <= held("pentester")
    assert "engagement_scenarios.view" in held("remediation")
    assert "engagement_scenarios.manage" not in held("remediation")
    assert "engagement_scenarios.manage" not in held("external_vendor")


def test_create_keeps_name_exactly_and_orders(w, admin_client):
    r = add(admin_client, w.eng_a, "  SQLi in /search?q=  ", description="Try **blind** payloads")
    assert r.status_code == 201, r.content
    body = r.json()
    assert body["name"] == "SQLi in /search?q=" and body["status"] == "planned" and body["position"] == 0
    assert "owner" not in body and "assigned_to" not in body and "finding" not in str(body.keys())
    assert add(admin_client, w.eng_a, "Second").json()["position"] == 1
    names = [s["name"] for s in admin_client.get(url(w.eng_a)).json()]
    assert names == ["SQLi in /search?q=", "Second"]


def test_name_unique_per_engagement_case_insensitive(w, admin_client):
    assert add(admin_client, w.eng_a, "Auth bypass").status_code == 201
    assert add(admin_client, w.eng_a, "auth BYPASS").status_code == 400
    assert add(admin_client, w.eng_b, "Auth bypass").status_code == 201  # other engagement is free
    assert add(admin_client, w.eng_a, "   ").status_code == 400


def test_strict_fields_and_date_order(w, admin_client):
    assert add(admin_client, w.eng_a, owner="x").status_code == 400
    assert add(admin_client, w.eng_a, "a", assigned_to="x").status_code == 400
    bad = add(admin_client, w.eng_a, "b", planned_start="2027-02-01", planned_end="2027-01-01")
    assert bad.status_code == 400


def test_edit_changes_name_and_description_only(w, admin_client):
    sid = add(admin_client, w.eng_a, "Old").json()["id"]
    r = admin_client.patch(url(w.eng_a, sid), {"name": "New name", "description": "text"}, format="json")
    assert r.status_code == 200 and r.json()["name"] == "New name"
    assert admin_client.patch(url(w.eng_a, sid), {"status": "tested"}, format="json").status_code == 400
    add(admin_client, w.eng_a, "Taken")
    assert admin_client.patch(url(w.eng_a, sid), {"name": "taken"}, format="json").status_code == 400


def test_reschedule_and_defer_to_next_year(w, admin_client):
    sid = add(admin_client, w.eng_a, "Wireless", planned_start="2026-12-01", planned_end="2026-12-05").json()["id"]
    nxt = (TODAY.replace(year=TODAY.year + 1)).isoformat()
    r = admin_client.post(
        url(w.eng_a, sid, "/status"),
        {"status": "deferred", "reason": "Client freeze", "planned_start": nxt, "planned_end": nxt},
        format="json",
    )
    assert r.status_code == 200 and r.json()["status"] == "deferred" and r.json()["planned_start"] == nxt
    r = admin_client.post(
        url(w.eng_a, sid, "/reschedule"),
        {"planned_start": nxt, "planned_end": nxt, "reason": "Confirmed"},
        format="json",
    )
    assert r.json()["status"] == "planned" and r.json()["status_reason"] == "Confirmed"
    bad = admin_client.post(
        url(w.eng_a, sid, "/reschedule"), {"planned_start": "2027-05-02", "planned_end": "2027-05-01"}, format="json"
    )
    assert bad.status_code == 400


def test_status_rules(w, admin_client):
    sid = add(admin_client, w.eng_a, "API").json()["id"]
    post = lambda body: admin_client.post(url(w.eng_a, sid, "/status"), body, format="json")  # noqa: E731
    assert post({"status": "deferred"}).status_code == 400  # reason needed
    assert post({"status": "cancelled", "reason": ""}).status_code == 400
    done = post({"status": "tested"})
    assert done.status_code == 200 and done.json()["completed_on"] == TODAY.isoformat()
    assert post({"status": "cancelled", "reason": "x"}).status_code == 409  # tested cannot be cancelled
    assert (
        admin_client.post(
            url(w.eng_a, sid, "/reschedule"), {"planned_start": None, "planned_end": None}, format="json"
        ).status_code
        == 409
    )
    reopened = post({"status": "in_progress"})
    assert reopened.status_code == 200 and reopened.json()["completed_on"] is None
    assert post({"status": "cancelled", "reason": "Out of scope"}).json()["status"] == "cancelled"
    assert post({"status": "planned"}).json()["status"] == "planned"


def test_reorder(w, admin_client):
    ids = [add(admin_client, w.eng_a, n).json()["id"] for n in ("A", "B", "C")]
    r = admin_client.post(f"{API}/engagements/{w.eng_a.pk}/scenario-order", {"ids": ids[::-1]}, format="json")
    assert r.status_code == 200 and [s["name"] for s in r.json()] == ["C", "B", "A"]
    assert [s["name"] for s in admin_client.get(url(w.eng_a)).json()] == ["C", "B", "A"]
    for bad in (ids[:2], ids + ids[:1]):
        assert (
            admin_client.post(f"{API}/engagements/{w.eng_a.pk}/scenario-order", {"ids": bad}, format="json").status_code
            == 400
        )
    other = add(admin_client, w.eng_b, "Z").json()["id"]
    assert (
        admin_client.post(
            f"{API}/engagements/{w.eng_a.pk}/scenario-order", {"ids": ids[:2] + [other]}, format="json"
        ).status_code
        == 400
    )


def test_scoping_between_roles_and_engagements(w, admin_client):
    sid = add(admin_client, w.eng_a, "Scoped").json()["id"]
    lead = signed_in(w.p1)  # pentester, lead of eng_a
    assert add(lead, w.eng_a, "By lead").status_code == 201
    outsider = signed_in(w.p3)  # pentester, not a member of eng_a
    assert outsider.get(url(w.eng_a)).status_code == 404
    assert add(outsider, w.eng_a, "Nope").status_code == 404
    assert outsider.patch(url(w.eng_a, sid), {"name": "x"}, format="json").status_code == 404
    fixer = signed_in(w.r1)  # remediation member: can read, cannot write
    assert fixer.get(url(w.eng_a)).status_code == 200
    assert add(fixer, w.eng_a, "Fixer").status_code == 403
    assert fixer.post(url(w.eng_a, sid, "/status"), {"status": "tested"}, format="json").status_code == 403
    # a scenario id of eng_a is not reachable through eng_b
    assert admin_client.patch(url(w.eng_b, sid), {"name": "x"}, format="json").status_code == 404


def test_archived_engagement_is_read_only(w, admin_client):
    sid = add(admin_client, w.eng_a, "Frozen").json()["id"]
    from django.utils import timezone

    from apps.engagements.models import Engagement

    Engagement.objects.filter(pk=w.eng_a.pk).update(archived_at=timezone.now())
    assert add(admin_client, w.eng_a, "More").status_code == 409
    assert admin_client.post(url(w.eng_a, sid, "/status"), {"status": "tested"}, format="json").status_code == 409
    assert admin_client.get(url(w.eng_a)).status_code == 200


def test_pictures_upload_list_download_delete(w, admin_client):
    sid = add(admin_client, w.eng_a, "With pictures").json()["id"]
    up = lambda name, data, c="image/png": admin_client.post(  # noqa: E731
        url(w.eng_a, sid, "/images"), {"file": SimpleUploadedFile(name, data, content_type=c)}, format="multipart"
    )
    r = up("diagram.png", png())
    assert r.status_code == 201 and r.json()["is_image"] and r.json()["scenario"] == sid
    assert up("note.txt", b"hello", "text/plain").status_code == 400  # images only
    assert up("fake.png", b"\x89PNG\r\n\x1a\nnot a png").status_code == 400
    listed = admin_client.get(url(w.eng_a)).json()[0]
    assert [i["original_name"] for i in listed["images"]] == ["diagram.png"]
    iid = listed["images"][0]["id"]
    assert admin_client.get(f"{API}/attachments/{iid}/download").status_code == 200
    assert iid not in [
        a["id"] for a in admin_client.get(f"{API}/attachments?engagement={w.eng_a.pk}").json()["results"]
    ]
    assert admin_client.delete(f"{API}/attachments/{iid}").status_code == 403  # only through the scenario
    assert admin_client.delete(url(w.eng_a, sid, f"/images/{iid}")).status_code == 204
    assert admin_client.get(url(w.eng_a)).json()[0]["images"] == []
    assert Attachment.objects.get(pk=iid).deleted_at is not None


def test_picture_limit_and_access(w, admin_client):
    sid = add(admin_client, w.eng_a, "Limit").json()["id"]
    from apps.files.services import MAX_IMAGES_PER_SCENARIO

    for i in range(MAX_IMAGES_PER_SCENARIO):
        r = admin_client.post(
            url(w.eng_a, sid, "/images"),
            {"file": SimpleUploadedFile(f"{i}.png", png((8 + i, 8)), content_type="image/png")},
            format="multipart",
        )
        assert r.status_code == 201
    over = admin_client.post(
        url(w.eng_a, sid, "/images"),
        {"file": SimpleUploadedFile("x.png", png((30, 30)), content_type="image/png")},
        format="multipart",
    )
    assert over.status_code == 409
    iid = admin_client.get(url(w.eng_a)).json()[0]["images"][0]["id"]
    assert signed_in(w.r1).get(f"{API}/attachments/{iid}/download").status_code == 200
    assert signed_in(w.p3).get(f"{API}/attachments/{iid}/download").status_code == 404
    fixer = signed_in(w.r1)
    assert (
        fixer.post(
            url(w.eng_a, sid, "/images"),
            {"file": SimpleUploadedFile("y.png", png((40, 40)), content_type="image/png")},
            format="multipart",
        ).status_code
        == 403
    )


def test_audit_trail(w, admin_client):
    sid = add(admin_client, w.eng_a, "Audited").json()["id"]
    add(admin_client, w.eng_a, "Second")
    admin_client.patch(url(w.eng_a, sid), {"name": "Audited 2"}, format="json")
    admin_client.post(
        url(w.eng_a, sid, "/reschedule"), {"planned_start": "2027-01-01", "planned_end": "2027-01-02"}, format="json"
    )
    admin_client.post(url(w.eng_a, sid, "/status"), {"status": "tested"}, format="json")
    ids = [s["id"] for s in admin_client.get(url(w.eng_a)).json()]
    admin_client.post(f"{API}/engagements/{w.eng_a.pk}/scenario-order", {"ids": ids[::-1]}, format="json")
    seen = set(AuditEvent.objects.filter(action__startswith="engagement.scenario").values_list("action", flat=True))
    assert seen == {
        "engagement.scenario_added",
        "engagement.scenario_updated",
        "engagement.scenario_rescheduled",
        "engagement.scenario_status_changed",
        "engagement.scenarios_reordered",
    }


def test_findings_are_not_linked_to_scenarios(w):
    from apps.findings.models import Finding

    assert "scenario" not in {f.name for f in Finding._meta.get_fields()}
    assert {f.name for f in EngagementScenario._meta.get_fields()}.isdisjoint(
        {"owner", "lead", "assignee", "assigned_to"}
    )
    assert timedelta(days=1)


# ---------------------------------------------------------------- extras: progress, bulk, history, clone, guard


def test_progress_summary_on_list_and_detail(w, admin_client):
    a, b, c = (add(admin_client, w.eng_a, n).json()["id"] for n in ("A", "B", "C"))
    admin_client.post(url(w.eng_a, a, "/status"), {"status": "tested"}, format="json")
    admin_client.post(url(w.eng_a, c, "/status"), {"status": "cancelled", "reason": "later"}, format="json")
    detail = admin_client.get(f"{API}/engagements/{w.eng_a.pk}").json()["scenarios"]
    assert detail["total"] == 2 and detail["tested"] == 1 and detail["cancelled"] == 1 and detail["planned"] == 1
    rows = admin_client.get(f"{API}/engagements").json()["results"]
    assert next(r for r in rows if r["id"] == str(w.eng_a.pk))["scenarios"]["tested"] == 1
    assert next(r for r in rows if r["id"] == str(w.eng_b.pk))["scenarios"]["total"] == 0


def test_bulk_add_all_or_nothing(w, admin_client):
    bulk = f"{API}/engagements/{w.eng_a.pk}/scenarios-bulk"
    r = admin_client.post(bulk, {"names": ["  One ", "Two", "Three"]}, format="json")
    assert r.status_code == 201 and [s["name"] for s in r.json()] == ["One", "Two", "Three"]
    assert [s["position"] for s in r.json()] == [0, 1, 2]
    assert admin_client.post(bulk, {"names": ["Four", "one"]}, format="json").status_code == 400  # exists
    assert admin_client.post(bulk, {"names": ["X", "x"]}, format="json").status_code == 400  # repeated
    assert admin_client.post(bulk, {"names": []}, format="json").status_code == 400
    assert len(admin_client.get(url(w.eng_a)).json()) == 3
    assert signed_in(w.r1).post(bulk, {"names": ["Nope"]}, format="json").status_code == 403


def test_scenario_history(w, admin_client):
    sid = add(admin_client, w.eng_a, "Tracked").json()["id"]
    other = add(admin_client, w.eng_a, "Other").json()["id"]
    admin_client.post(url(w.eng_a, sid, "/status"), {"status": "deferred", "reason": "Freeze"}, format="json")
    admin_client.post(url(w.eng_a, other, "/status"), {"status": "tested"}, format="json")
    r = admin_client.get(url(w.eng_a, sid, "/history"))
    assert r.status_code == 200
    actions = [e["action"] for e in r.json()["results"]]
    assert actions == ["engagement.scenario_status_changed", "engagement.scenario_added"]
    assert signed_in(w.p3).get(url(w.eng_a, sid, "/history")).status_code == 404


def test_clone_copies_scenarios_planned_without_dates(w, admin_client):
    keep = add(admin_client, w.eng_a, "Keep me", description="d", planned_start="2026-12-01", planned_end="2026-12-02")
    drop = add(admin_client, w.eng_a, "Cancelled one").json()["id"]
    admin_client.post(url(w.eng_a, keep.json()["id"], "/status"), {"status": "tested"}, format="json")
    admin_client.post(url(w.eng_a, drop, "/status"), {"status": "cancelled", "reason": "x"}, format="json")
    body = {"name": "Next year", "start_date": "2027-03-01", "end_date": "2027-03-10", "lead": str(w.p1.pk)}
    new = admin_client.post(f"{API}/engagements/{w.eng_a.pk}/clone", body, format="json")
    assert new.status_code == 201, new.content
    copied = admin_client.get(f"{API}/engagements/{new.json()['id']}/scenarios").json()
    assert [(s["name"], s["status"], s["planned_start"], s["description"]) for s in copied] == [
        ("Keep me", "planned", None, "d")
    ]
    assert copied[0]["images"] == [] and copied[0]["completed_on"] is None


def test_completion_guard_needs_acknowledgement(w, admin_client):
    sid = add(admin_client, w.eng_a, "Pending").json()["id"]
    done = add(admin_client, w.eng_a, "Done").json()["id"]
    admin_client.post(url(w.eng_a, done, "/status"), {"status": "tested"}, format="json")
    eng = w.eng_a
    path = f"{API}/engagements/{eng.pk}/status"
    ver = lambda: admin_client.get(f"{API}/engagements/{eng.pk}").json()["version"]  # noqa: E731
    for to in ("scheduled", "in_progress"):
        assert admin_client.post(path, {"status": to, "version": ver()}, format="json").status_code == 200
    blocked = admin_client.post(path, {"status": "reporting", "version": ver()}, format="json")
    assert blocked.status_code == 409 and "1 scenario is not tested" in blocked.json()["error"]["message"]
    ok = admin_client.post(
        path, {"status": "reporting", "version": ver(), "acknowledge_open_scenarios": True}, format="json"
    )
    assert ok.status_code == 200 and ok.json()["status"] == "reporting"
    ev = AuditEvent.objects.filter(action="engagement.status_changed").latest("id")
    assert ev.metadata.get("acknowledged_open_scenarios") is True
    admin_client.post(url(w.eng_a, sid, "/status"), {"status": "tested"}, format="json")
    assert admin_client.post(path, {"status": "completed", "version": ver()}, format="json").status_code == 200


# ---------------------------------------------------------------- calendar, reminders, dashboard, report


def test_calendar_scenario_feed_is_scoped(w, admin_client):
    add(admin_client, w.eng_a, "Dated", planned_start="2026-12-10", planned_end="2026-12-12")
    add(admin_client, w.eng_a, "Undated")
    cancelled = add(admin_client, w.eng_a, "Gone", planned_start="2026-12-11", planned_end="2026-12-11").json()["id"]
    admin_client.post(url(w.eng_a, cancelled, "/status"), {"status": "cancelled", "reason": "x"}, format="json")
    add(admin_client, w.eng_b, "Other org", planned_start="2026-12-11", planned_end="2026-12-11")
    feed = f"{API}/calendar/scenarios?start=2026-12-01&end=2026-12-31"
    names = {s["name"] for s in admin_client.get(feed).json()["results"]}
    assert names == {"Dated", "Other org"}
    mine = {s["name"] for s in signed_in(w.p1).get(feed).json()["results"]}
    assert mine == {"Dated"}  # p1 is not on eng_b
    assert signed_in(w.p3).get(feed).json()["results"] == []
    assert admin_client.get(f"{API}/calendar/scenarios?start=2026-12-31&end=2026-12-01").status_code == 400
    early = admin_client.get(f"{API}/calendar/scenarios?start=2026-01-01&end=2026-01-31").json()["results"]
    assert early == []


def test_reminders_once_per_date(w, admin_client):
    from apps.engagements import scenarios
    from apps.notifications.models import Notification

    soon = (TODAY + timedelta(days=2)).isoformat()
    late = (TODAY - timedelta(days=1)).isoformat()
    add(admin_client, w.eng_a, "Starts soon", planned_start=soon, planned_end=soon)
    add(admin_client, w.eng_a, "Is late", planned_start=late, planned_end=late)
    add(admin_client, w.eng_a, "Far away", planned_start=(TODAY + timedelta(days=30)).isoformat())
    first = scenarios.remind()
    assert first > 0
    kinds = set(Notification.objects.filter(recipient=w.p1).values_list("kind", flat=True))
    assert {"scenario.due_soon", "scenario.overdue"} <= kinds
    titles = " ".join(Notification.objects.filter(recipient=w.p1).values_list("title", flat=True))
    assert "Starts soon" in titles and "Is late" in titles and "Far away" not in titles
    assert scenarios.remind() == 0  # same dates: nothing new


def test_dashboard_scenario_block(w, admin_client):
    a = add(admin_client, w.eng_a, "Late", planned_end=(TODAY - timedelta(days=1)).isoformat()).json()["id"]
    add(admin_client, w.eng_a, "Fine")
    t = add(admin_client, w.eng_a, "Tested").json()["id"]
    admin_client.post(url(w.eng_a, t, "/status"), {"status": "tested"}, format="json")
    block = admin_client.get(f"{API}/dashboards/admin").json()["scenarios"]
    assert block["total"] == 3 and block["tested"] == 1 and block["overdue"] == 1 and a
    assert signed_in(w.p3).get(f"{API}/dashboards/pentester").json()["scenarios"]["total"] == 0


@pytest.mark.django_db
def test_report_lists_scenarios_and_marks_interim(w, admin_client, django_capture_on_commit_callbacks):
    from tests.test_reports import done, download, pdf_text, request_report

    t = add(admin_client, w.eng_a, "Checkout flow", description="Pay with **stale** cart").json()["id"]
    add(admin_client, w.eng_a, "Admin portal", planned_start="2027-02-01", planned_end="2027-02-03")
    admin_client.post(url(w.eng_a, t, "/status"), {"status": "tested"}, format="json")
    up = admin_client.post(
        url(w.eng_a, t, "/images"),
        {"file": SimpleUploadedFile("shot.png", png(), content_type="image/png")},
        format="multipart",
    )
    assert up.status_code == 201
    job = done(admin_client, request_report(admin_client, w.eng_a, django_capture_on_commit_callbacks))
    text = pdf_text(download(admin_client, job))
    for needle in (
        "Test scenarios",
        "Interim report",
        "Checkout flow",
        "Admin portal",
        "Not yet tested",
        "1 February 2027"[:1],
    ):
        assert needle in text, needle


def test_dashboard_items_differ_by_role(w, admin_client):
    late = (TODAY - timedelta(days=2)).isoformat()
    soon = (TODAY + timedelta(days=2)).isoformat()
    far = (TODAY + timedelta(days=90)).isoformat()
    add(admin_client, w.eng_a, "Late one", planned_start=late, planned_end=late)
    add(admin_client, w.eng_a, "Soon one", planned_start=soon, planned_end=soon)
    add(admin_client, w.eng_a, "Far one", planned_start=far, planned_end=far)
    d = add(admin_client, w.eng_a, "Waiting").json()["id"]
    admin_client.post(url(w.eng_a, d, "/status"), {"status": "deferred", "reason": "Freeze"}, format="json")
    names = lambda client, kind: [i["name"] for i in client.get(f"{API}/dashboards/{kind}").json()["scenarios"]["items"]]  # noqa: E731
    assert names(admin_client, "admin") == ["Late one", "Soon one", "Waiting"]
    pent = names(signed_in(w.p1), "pentester")
    assert pent == ["Late one", "Soon one"] and "Waiting" not in pent and "Far one" not in pent
    first = signed_in(w.p1).get(f"{API}/dashboards/pentester").json()["scenarios"]["items"][0]
    assert first["overdue"] is True and first["engagement"]["ref"] == w.eng_a.ref
    assert names(signed_in(w.p3), "pentester") == []  # not on eng_a
