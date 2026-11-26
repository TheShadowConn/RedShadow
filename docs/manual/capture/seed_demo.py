"""Seed a fictional Acme Corp for the manual's screenshots. Run from backend/ with the test settings:

    MEDIA_ROOT=/tmp/rs-demo-media python manage.py shell < ../docs/manual/capture/seed_demo.py

Set MEDIA_ROOT to the same folder for the server you screenshot, so the scenario pictures can be served.

Creates users (see USERS below), one organisation, one engagement in testing with scenarios and pictures,
findings in every severity, an import with gaps, and cost lines. Prints the MFA secret of the admin.
"""

import io
from datetime import date, timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, ImageDraw, ImageFont

from apps.accounts import crypto
from apps.engagements import scenarios as scen
from apps.engagements import services as eng
from apps.engagements.models import EngagementMembership
from apps.findings import services as fs
from apps.findings.models import Finding
from apps.organisations import services as orgs
from apps.rbac.models import Role
from tests.conftest import PASSWORD, make_user, signed_in

SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"
today = date.today()
admin = make_user("admin@redshadow.demo", "super_admin", display_name="Admin", mfa_enabled=True,
                  mfa_secret_enc=crypto.encrypt(SECRET))  # fmt: skip
priya = make_user("priya@redshadow.demo", "pentester", display_name="Priya Pentester")
ravi = make_user("ravi@redshadow.demo", "remediation", display_name="Ravi Remediation")
vera = make_user("vera@redshadow.demo", Role.objects.get(system_key="external_vendor"), display_name="Vera Vendor")

acme = orgs.create_organisation(None, admin, {"name": "Acme Corp", "industry": "Retail"})
shop = orgs.create_asset(None, admin, acme, {"name": "Acme shop", "type": "web_app", "identifier": "https://shop.acme.test"})
api_asset = orgs.create_asset(None, admin, acme, {"name": "Acme API", "type": "api", "identifier": "https://api.acme.test"})
build = orgs.create_asset(None, admin, acme, {"name": "Build server", "type": "host", "identifier": "10.0.0.8"})

MD = {
    "scope": "- **shop.acme.test** and **api.acme.test** (production)\n- The customer login and checkout flow\n- Mobile API v2 endpoints listed in the [test plan](https://acme.test/plan)",
    "out_of_scope": "- Denial of service\n- The third-party payment provider\n- The build server `10.0.0.8`",
    "objectives": "1. Find vulnerabilities that expose customer data\n2. Check authentication and session handling\n3. Confirm last quarter's fixes hold",
    "methodology": "Black-box testing following the [OWASP WSTG](https://owasp.org/www-project-web-security-testing-guide/):\n\n- Reconnaissance and mapping\n- Authentication and authorisation tests\n- Input handling and business logic",
    "rules_of_engagement": "- Test only between 08:00 and 18:00 UTC\n- Stop and call the client contact if you reach customer data\n- No social engineering",
}
e = eng.create_engagement(None, admin, {"type": "web", "start_date": today - timedelta(days=18), "end_date": today + timedelta(days=14),
                                        "organisation": acme, "name": "Acme web test Q4", "lead": priya, **MD})  # fmt: skip
EngagementMembership.objects.create(engagement=e, user=ravi, added_by=admin)
EngagementMembership.objects.create(engagement=e, user=vera, added_by=admin)
eng.link_asset(None, admin, e, shop, True, "")
eng.link_asset(None, admin, e, api_asset, True, "")
eng.link_asset(None, admin, e, build, False, "Not part of this test")
for cur, cat, amt, d in (("EUR", "labour", 18200, "Labour, 14 days"), ("EUR", "tools", 3400, "Scanner licences"), ("USD", "travel", 1250, "Site visit")):
    eng.add_cost(None, admin, e, {"amount": amt, "currency": cur, "category": cat, "description": d, "incurred_on": today})

# an earlier engagement with its own costs, so the Costs page has a timeline across engagements and years
old = eng.create_engagement(None, admin, {"type": "mobile", "start_date": date(2026, 2, 2), "end_date": date(2026, 6, 26),
                                          "organisation": acme, "name": "Acme mobile app test Q2", "lead": priya})  # fmt: skip
for cur, cat, amt, d, text in (("EUR", "labour", 5200, date(2025, 12, 12), "Scoping workshop"), ("EUR", "labour", 7800, date(2026, 3, 9), "Labour, 10 days"),
                               ("USD", "travel", 900, date(2026, 3, 11), "Travel to client site"), ("EUR", "tools", 1200, date(2026, 6, 5), "Mobile testing licences")):
    eng.add_cost(None, admin, old, {"amount": amt, "currency": cur, "category": cat, "description": text, "incurred_on": d})

# scenarios (the first one starting moves the engagement into testing)
adm = signed_in(admin)
API = "/api/v1"


def shot(w, h, title, lines, accent):
    im = Image.new("RGB", (w, h), "#1b2230")
    d = ImageDraw.Draw(im)
    big, small = ImageFont.load_default(size=22), ImageFont.load_default(size=19)
    d.rectangle([0, 0, w, 48], fill=accent)
    d.text((16, 12), title, fill="white", font=big)
    for i, line in enumerate(lines):
        d.text((20, 78 + i * 38), line, fill="#c9d4e5", font=small)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


names = ["Login and session handling", "Checkout and payment flow", "Admin portal access control", "File upload"]
made = {n: scen.add_scenario(None, admin, e, {"name": n, "description": d}) for n, d in zip(names, [
    "- Brute force and lockout\n- Session fixation\n- Password reset flow: [OWASP guide](https://owasp.org/www-project-web-security-testing-guide/)",
    "Price tampering and replay of payment requests.",
    "Check that **customer** accounts cannot reach `/admin`.",
    "Content-type and size checks on avatar upload.",
], strict=True)}
login = made[names[0]]
for fname, title, lines, accent in (
    ("burp-intruder.png", "Burp Suite - Intruder results", ["POST /login   attempts 1 to 500", "401 x 497    429 after attempt 10", "Lockout works: locked for 15 min"], "#8a1f11"),
    ("session-cookie.png", "Browser - cookie inspector", ["rs_session  HttpOnly  Secure", "SameSite=Lax", "ID changes after login", "Old session rejected: 401"], "#17604a"),
):
    r = adm.post(f"{API}/engagements/{e.pk}/scenarios/{login.pk}/images", {"file": SimpleUploadedFile(fname, shot(520, 300, title, lines, accent), "image/png")}, format="multipart")
    assert r.status_code == 201, r.content
adm.post(f"{API}/engagements/{e.pk}/scenarios/{login.pk}/status", {"status": "in_progress"}, format="json")
pay = made[names[1]]
adm.post(f"{API}/engagements/{e.pk}/scenarios/{pay.pk}/status", {"status": "in_progress"}, format="json")
adm.post(f"{API}/engagements/{e.pk}/scenarios/{made[names[2]].pk}/status", {"status": "tested"}, format="json")

# findings
rows = [
    ("SQL injection in search", "critical", shop, "/search", 89), ("Stored XSS in product reviews", "high", shop, "/reviews", 79),
    ("Broken access control on /admin", "high", shop, "/admin", 284), ("IDOR on order details", "high", api_asset, "/orders/{id}", 639),
    ("Weak password policy", "medium", shop, "/register", 521), ("Missing rate limiting on login", "medium", shop, "/login", 307),
    ("Verbose error messages", "medium", api_asset, "/v2/cart", 209), ("Outdated jQuery", "low", shop, "/", 1104),
    ("Missing security headers", "low", shop, "/", 693), ("Directory listing enabled", "low", api_asset, "/static/", 548),
    ("Server version disclosed", "info", api_asset, "/", 200), ("CORS allows any origin", "medium", api_asset, "/v2/", 942),
]
made_f = []
for i, (title, sev, asset, ep, cwe) in enumerate(rows):
    f = fs.create_finding(None, priya, e, {"title": title, "severity": sev, "asset": asset, "endpoint": ep, "cwe_id": cwe,
                                           "description": f"{title}.\n\n- Found on `{ep}`\n- Reproducible in production",
                                           "recommendation": "Fix as described in the OWASP cheat sheet.", "assigned_pentester": priya,
                                           "remediation_owner": ravi if i % 2 == 0 else None, "discovered_at": today - timedelta(days=i % 9)})  # fmt: skip
    made_f.append(f)
for f in made_f[:9]:
    fs.publish_finding(None, priya, Finding.objects.get(pk=f.pk), Finding.objects.get(pk=f.pk).version)

# findings reported by the external vendor, for the vendor dashboard
for title, sev, ep in (("Weak TLS configuration", "medium", "/"), ("Exposed admin login page", "low", "/admin"), ("Reflected XSS in search", "high", "/search"), ("Debug mode enabled", "medium", "/debug")):
    vf = fs.create_finding(None, vera, e, {"title": title, "severity": sev, "asset": shop, "endpoint": ep, "description": f"{title}.", "recommendation": "Apply the vendor guidance."})
    if sev != "medium":
        fs.publish_finding(None, vera, Finding.objects.get(pk=vf.pk), Finding.objects.get(pk=vf.pk).version)

# an import with gaps (everything mode)
pen = signed_in(priya)
csv_text = ("Title,Severity,Description,Recommendation,Asset,CWE,Date,Endpoint,References\r\n"
            "Open redirect on /go,medium,Redirects to any URL.,Allow-list targets.,Acme shop,CWE-601,2026-11-20,/go,\r\n"
            ",high,Scanner row with no title.,,Acme API,CWE-89,2026-11-20,/v2/search,\r\n"
            "Clickjacking possible,,No frame protection.,Send X-Frame-Options.,Unknown host,CWE-1021,2026-11-20,/,not a link\r\n"
            "TLS 1.0 enabled,low,Old protocol enabled.,Disable TLS 1.0.,Acme shop,CWE-326,2026-11-21,/,\r\n")
r = pen.post(f"{API}/imports", {"engagement": str(e.pk), "file": SimpleUploadedFile("Scanner_Export_Q4.csv", csv_text.encode(), "text/csv")}, format="multipart")
job = r.json()
cm = {"title": "Title", "severity": "Severity", "description": "Description", "recommendation": "Recommendation", "asset": "Asset", "cwe": "CWE", "discovered_at": "Date", "endpoint": "Endpoint", "references": "References"}
pen.post(f"{API}/imports/{job['id']}/mapping", {"column_map": cm, "value_map": {}}, format="json")
# a recorded backup, as scripts/backup.sh does after a run (shown on the About page to Super Admins)
from django.core.management import call_command  # noqa: E402

call_command("record_backup", name="20261126-020000", bytes=48234496)

# the seed signed in with a code from the current 30 s window; let the screenshots sign in straight away
from apps.accounts.models import User  # noqa: E402

User.objects.filter(pk=admin.pk).update(mfa_last_step=0)
print("IMPORT_JOB", job["id"])
print("MFA_SECRET", SECRET, "PASSWORD", PASSWORD)
print("ENGAGEMENT", e.pk, e.ref)
