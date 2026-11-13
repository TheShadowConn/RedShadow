"""Phase 8: findings CSV export."""

import csv
import hashlib
import io

import pytest

from apps.audit.models import AuditEvent
from apps.findings import exports
from tests.conftest import make_role, make_user, signed_in
from tests.test_findings import API, furl, make, publish
from tests.world import build_world

URL = f"{API}/findings/export.csv"


@pytest.fixture
def w(admin):
    return build_world(admin)


@pytest.fixture
def p1c(w):
    return signed_in(w.p1)


@pytest.fixture
def r1c(w):
    return signed_in(w.r1)


def table(response):
    assert response.status_code == 200, response.content
    return list(csv.reader(io.StringIO(b"".join(response.streaming_content).decode())))


@pytest.mark.django_db
class TestExport:
    def test_columns_filters_and_audit(self, w, p1c):
        make(p1c, w.eng_a, title="Alpha", severity="critical")
        make(p1c, w.eng_a, title="Beta", severity="low")
        r = p1c.get(f"{URL}?severity=critical")
        t = table(r)
        assert t[0] == exports.COLUMNS and len(t) == 2 and t[1][3] == "Alpha" and t[1][4] == "critical"
        assert "attachment" in r["Content-Disposition"] and r["Cache-Control"] == "no-store"
        ev = AuditEvent.objects.get(action="finding.exported")
        assert ev.metadata["rows"] == 1 and ev.metadata["filters"] == {"severity": "critical"}

    def test_hash_in_the_log_matches_the_file(self, w, p1c):
        make(p1c, w.eng_a)
        r = p1c.get(URL)
        body = b"".join(r.streaming_content)
        assert AuditEvent.objects.get(action="finding.exported").metadata["sha256"] == hashlib.sha256(body).hexdigest()

    def test_only_what_the_caller_can_see(self, w, p1c, r1c, admin_client):
        draft = make(p1c, w.eng_a, title="Draft one")
        mine = publish(p1c, make(p1c, w.eng_a, title="Assigned"))
        p1c.patch(furl(mine), {"version": mine["version"], "remediation_owner": str(w.r1.pk)}, format="json")
        publish(p1c, make(p1c, w.eng_a, title="Unassigned published"))
        make(admin_client, w.eng_b, title="Other engagement")
        assert {r[3] for r in table(r1c.get(URL))[1:]} == {"Assigned"}
        assert {r[3] for r in table(p1c.get(URL))[1:]} == {"Draft one", "Assigned", "Unassigned published"}
        assert {r[3] for r in table(admin_client.get(URL))[1:]} == {
            "Draft one",
            "Assigned",
            "Unassigned published",
            "Other engagement",
        }
        assert draft["id"]

    def test_formula_cells_are_neutralised(self, w, p1c):
        make(p1c, w.eng_a, title='=HYPERLINK("http://x")', description="+cmd")
        row = table(p1c.get(URL))[1]
        assert row[3].startswith("'=") and row[16].startswith("'+")

    def test_role_without_export_permission_is_refused(self, w):
        no = make_user("noexp@example.com", make_role("NoExport", ["engagements.view", "findings.view"]))
        assert signed_in(no).get(URL).status_code == 403

    def test_too_many_rows_is_refused(self, w, p1c, monkeypatch):
        monkeypatch.setattr(exports, "MAX_ROWS", 1)
        make(p1c, w.eng_a, title="One")
        make(p1c, w.eng_a, title="Two")
        assert p1c.get(URL).status_code == 409

    def test_empty_result_is_just_the_header(self, w, p1c):
        assert len(table(p1c.get(f"{URL}?severity=info"))) == 1
