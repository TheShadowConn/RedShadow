"""Department view and filters, and scanner file import (Nessus, Burp, Nmap)."""

import base64
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.findings.models import Finding
from apps.imports import scans
from apps.imports.models import ImportJob
from apps.imports.parsing import ParseError
from apps.organisations import services as org_services
from apps.organisations.models import Asset
from apps.reports import builder
from tests.conftest import signed_in
from tests.test_findings import API
from tests.world import build_world

NESSUS = b"""<?xml version="1.0" ?>
<NessusClientData_v2><Report name="r">
<ReportHost name="10.0.0.5"><HostProperties><tag name="host-ip">10.0.0.5</tag>
<tag name="host-fqdn">web01.acme.test</tag></HostProperties>
<ReportItem port="443" protocol="tcp" severity="3" pluginID="1" pluginName="Weak TLS">
<description>Old protocols.</description><solution>Disable them.</solution>
<cvss3_vector>CVSS:3.0/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N</cvss3_vector><cwe>327</cwe>
<plugin_output>TLSv1.0 ~~~~ &lt;script&gt;</plugin_output><see_also>https://example.test/a
https://example.test/b</see_also></ReportItem>
<ReportItem port="0" protocol="tcp" severity="0" pluginID="2" pluginName="Host info"/>
</ReportHost></Report></NessusClientData_v2>"""

BURP = (
    b"""<?xml version="1.0"?>
<!DOCTYPE issues [<!ELEMENT issues (issue*)>]>
<issues><issue><name>Reflected XSS</name><host ip="10.0.0.5">https://web01.acme.test</host>
<path>/search</path><severity>High</severity><confidence>Certain</confidence>
<issueBackground>&lt;p&gt;Input is &lt;b&gt;reflected&lt;/b&gt;.&lt;/p&gt;</issueBackground>
<vulnerabilityClassifications>&lt;a&gt;CWE-79: XSS&lt;/a&gt;</vulnerabilityClassifications>
<requestresponse><request base64="true">"""
    + base64.b64encode(b"GET /search?q=x HTTP/1.1")
    + b"""</request></requestresponse></issue></issues>"""
)

NMAP = b"""<?xml version="1.0"?><!DOCTYPE nmaprun><nmaprun>
<host><status state="up"/><address addr="10.0.0.5" addrtype="ipv4"/>
<hostnames><hostname name="web01.acme.test"/></hostnames>
<ports><port protocol="tcp" portid="22"><state state="open"/></port>
<port protocol="tcp" portid="23"><state state="closed"/></port></ports></host>
<host><status state="down"/><address addr="10.0.0.9" addrtype="ipv4"/></host></nmaprun>"""

BOMB = b"""<?xml version="1.0"?><!DOCTYPE issues [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;">]>
<issues><issue><name>&b;</name></issue></issues>"""
XXE = b"""<?xml version="1.0"?><!DOCTYPE issues [<!ENTITY x SYSTEM "file:///etc/passwd">]>
<issues><issue><name>&x;</name></issue></issues>"""


def table(parsed):
    return [dict(zip(parsed.headers, cells, strict=True)) for _, cells in parsed.rows]


class TestParsers:
    def test_nessus(self):
        (row,) = table(scans.parse(NESSUS, "findings", known_cwes={327}))
        assert row["Title"] == "Weak TLS" and row["Severity"] == ""
        assert row["CVSS vector"].startswith("CVSS:3.1/") and row["CWE"] == "CWE-327"
        assert row["Endpoint"] == "web01.acme.test:443/tcp" and row["Asset"] == "10.0.0.5; web01.acme.test"
        assert row["Proof of concept"].count("~~~~") == 2
        assert row["References"] == "https://example.test/a\nhttps://example.test/b"

    def test_informational_results_only_on_request(self):
        assert len(table(scans.parse(NESSUS, "findings", include_info=True))) == 2

    def test_burp(self):
        (row,) = table(scans.parse(BURP, "findings", known_cwes={79}))
        assert (row["Title"], row["Severity"], row["CWE"]) == ("Reflected XSS", "high", "CWE-79")
        assert row["Description"] == "Input is reflected."
        assert "GET /search?q=x" in row["Proof of concept"]
        assert row["Endpoint"] == "https://web01.acme.test/search"

    def test_nmap_hosts(self):
        (row,) = table(scans.parse(NMAP, "assets"))
        assert (row["IP address"], row["Hostname"], row["Open ports"]) == ("10.0.0.5", "web01.acme.test", "22/tcp")

    def test_nmap_is_not_findings(self):
        with pytest.raises(ParseError, match="Import this file as assets"):
            scans.parse(NMAP, "findings")

    @pytest.mark.parametrize("data", [BOMB, XXE])
    def test_entities_are_refused(self, data):
        with pytest.raises(ParseError, match="not allowed"):
            scans.parse(data, "findings")

    @pytest.mark.parametrize("data", [b"<html></html>", b"<issues><issue>"])
    def test_other_or_broken_xml(self, data):
        with pytest.raises(ParseError):
            scans.parse(data, "findings")

    def test_hosts_of_a_nessus_file_as_assets(self):
        (row,) = table(scans.parse(NESSUS, "assets"))
        assert row["Name"] == "web01.acme.test" and row["IP address"] == "10.0.0.5"


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)


@pytest.fixture
def w(admin):
    w = build_world(admin)
    Asset.objects.filter(pk=w.asset_a.pk).update(tags=["IT Help Desk", "PCI"])
    return w


def send(client, data, name, **extra):
    return client.post(
        f"{API}/imports", {"file": SimpleUploadedFile(name, data, "text/xml"), **extra}, format="multipart"
    )


def run(client, job):
    """Accept the suggested columns, then return the checked job."""
    job = client.get(f"{API}/imports/{job['id']}").json()
    body = {"column_map": job["suggested_mapping"], "value_map": {}}
    r = client.post(f"{API}/imports/{job['id']}/mapping", body, format="json")
    assert r.status_code == 202, r.content
    return client.get(f"{API}/imports/{job['id']}").json()


def commit(client, job):
    return client.post(
        f"{API}/imports/{job['id']}/commit", {"mode": "valid_rows_only", "duplicates": "skip"}, format="json"
    )


@pytest.mark.django_db
class TestScanImport:
    def test_burp_becomes_a_draft_once(self, w):
        client = signed_in(w.p1)
        org_services.update_asset(None, w.p1, w.asset_a, {"identifier": "https://web01.acme.test"})
        for expected in (1, 0):
            r = send(client, BURP, "scan.xml", engagement=str(w.eng_a.pk))
            assert r.status_code == 201, r.content
            job = run(client, r.json())
            assert job["counts"]["valid"] == expected, job
            if expected:
                assert commit(client, job).status_code == 202
        (finding,) = Finding.objects.filter(engagement=w.eng_a)
        assert (finding.status, finding.severity, finding.asset_id) == ("draft", "high", w.asset_a.pk)

    def test_include_info_survives_mapping(self, w):
        client = signed_in(w.p1)
        r = send(client, NESSUS, "scan.nessus", engagement=str(w.eng_a.pk), include_info="true")
        job = run(client, r.json())
        assert job["counts"]["total"] == 2
        assert ImportJob.objects.get(pk=job["id"]).mapping["include_info"] is True

    def test_hosts_become_assets_not_onboarded(self, w, admin_client):
        r = send(admin_client, NMAP, "hosts.xml", kind="assets", organisation=str(w.org_a.pk))
        assert r.status_code == 201, r.content
        assert commit(admin_client, run(admin_client, r.json())).status_code == 202
        asset = Asset.objects.get(organisation=w.org_a, name="web01.acme.test")
        assert asset.onboarding_status == "pending"

    def test_bad_xml_fails_the_job(self, w):
        client = signed_in(w.p1)
        job = send(client, XXE, "x.xml", engagement=str(w.eng_a.pk)).json()
        job = client.get(f"{API}/imports/{job['id']}").json()
        assert job["status"] == "failed" and "not allowed" in job["error"]


@pytest.mark.django_db
class TestDepartments:
    def add(self, w, severity="high"):
        r = signed_in(w.p1).post(
            f"{API}/findings",
            {"engagement": str(w.eng_a.pk), "title": "T", "severity": severity, "asset": str(w.asset_a.pk)},
            format="json",
        )
        assert r.status_code == 201, r.content
        Finding.objects.filter(pk=r.json()["id"]).update(status="open", due_date=w.today - timedelta(days=1))

    def test_counts_per_tag_and_total_once(self, w, admin_client):
        self.add(w)
        data = admin_client.get(f"{API}/assets/departments").json()
        rows = {r["tag"]: r for r in data["rows"]}
        assert rows["IT Help Desk"]["open"] == rows["PCI"]["open"] == data["total"]["open"] == 1
        assert rows["PCI"]["overdue"] == 1 and rows["PCI"]["open_by_severity"]["high"] == 1
        assert rows[None]["assets"] == 1 and rows[None]["open"] == 0

    def test_a_user_sees_only_their_engagements(self, w):
        self.add(w)
        data = signed_in(w.p2).get(f"{API}/assets/departments").json()
        assert data["total"]["open"] == 0 and "PCI" not in {r["tag"] for r in data["rows"]}

    def test_findings_filter(self, w, admin_client):
        self.add(w)
        count = lambda q: admin_client.get(f"{API}/findings?{q}").json()["count"]  # noqa: E731
        assert count("tag=pci") == 1
        assert count("tag=nope") == 0
        assert count("untagged=true") == 0

    def test_report_filter(self, w):
        assert builder.normalise_filters({"tags": [" PCI "]})["tags"] == ["PCI"]
        assert "tags" not in builder.normalise_filters({})
