"""Build the RedShadow user and workflow manual (PDF) with WeasyPrint.

Run inside the backend image (WeasyPrint and Python-Markdown live there):

    make manual

Sources: docs/manual/content/*.md (chapters, in file-name order), docs/manual/shots/* (screenshots),
docs/manual/manual.css. Role tables are generated from the live RBAC catalogue and the finding state machine,
so the manual cannot drift from what the application enforces. No network access is used.
"""

import base64
import datetime
import html
import os
import re
import sys
from pathlib import Path

import markdown
from weasyprint import HTML

HERE = Path(__file__).resolve().parent
sys.path.insert(0, os.environ.get("BACKEND_DIR", "/app"))

from apps.findings.lifecycle import RULES  # noqa: E402
from apps.rbac.catalogue import PERMISSIONS, PLATFORM, SYSTEM_ROLES  # noqa: E402

BACKEND = Path(os.environ.get("BACKEND_DIR", "/app"))
FONTS = BACKEND / "apps" / "reports" / "assets" / "fonts"
BRAND = Path(os.environ.get("BRAND_DIR", HERE.parent.parent / "frontend" / "public" / "brand"))
VERSION = os.environ.get("APP_VERSION", "1.1.0")
TODAY = datetime.date.today()
OUT = Path(os.environ.get("MANUAL_OUT", HERE / "RedShadow-User-Manual.pdf"))

TAGLINE = "Offensive Security, under control."
TAGLINE_STYLE = os.environ.get("TAGLINE_STYLE", "title")  # "logo" (small, under the wordmark) or "title" (subtitle)

ROLE_KEYS = ["super_admin", "pentester", "remediation", "external_vendor"]
ROLE_NAMES = {"super_admin": "Super Admin", "pentester": "Pentester", "remediation": "Remediation Owner", "external_vendor": "External Vendor"}
CHIPS = {"SA": ("super_admin", "Super Admin"), "PT": ("pentester", "Pentester"), "RO": ("remediation", "Remediation Owner"), "EV": ("external_vendor", "External Vendor")}
STATUS = {
    "draft": "Draft", "open": "Open", "in_progress": "In progress", "pending_verification": "Pending verification",
    "reopened": "Reopened", "closed": "Closed", "risk_accepted": "Risk accepted", "false_positive": "False positive",
    "duplicate": "Duplicate",
}


def data_uri(path: Path, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def holds(role: str, perms) -> bool:
    return bool(set(perms) & set(SYSTEM_ROLES[role]["grants"]))


def chip(role_key: str, label: str | None = None) -> str:
    return f'<span class="chip chip-{role_key}">{html.escape(label or ROLE_NAMES[role_key])}</span>'


def role_list(perms) -> str:
    who = [chip(k) for k in ROLE_KEYS if holds(k, perms)]
    return " ".join(who) if who else '<span class="muted">nobody by default</span>'


# ------------------------------------------------------------------ generated tables

CAPABILITIES = [
    ("Create and manage users and roles", ["users.create", "roles.manage"], True),
    ("Create organisations, assets and engagements", ["organisations.create", "engagements.create"], True),
    ("Change engagement status, dates and team", ["engagements.update_status", "engagements.manage_members"], False),
    ("See every engagement", None, "all"),
    ("Create findings", ["findings.create"], False),
    ("Edit findings (draft, open, in progress, reopened)", ["findings.update"], False),
    ("Publish findings", ["findings.publish"], False),
    ("See draft findings", ["findings.view_draft"], False),
    ("See only findings assigned to them", None, "assigned"),
    ("See only findings they reported or are assigned", None, "own"),
    ("Upload evidence", ["evidence.upload"], False),
    ("Write technical (team-only) notes", ["finding_notes.technical"], False),
    ("Write remediation notes", ["finding_notes.remediation"], False),
    ("Start work and pause work", ["remediation.update_status"], False),
    ("Submit a fix for verification", ["remediation.submit_verification"], False),
    ("Verify a fix and close", ["findings.verify"], False),
    ("Request retest rounds", ["retests.create"], False),
    ("Record retest results", ["retests.record"], False),
    ("Close, reopen findings", ["findings.close", "findings.reopen"], False),
    ("Accept risk", ["findings.risk_accept"], False),
    ("Delete findings (soft delete)", ["findings.delete"], False),
    ("Import findings from CSV", ["imports.create"], False),
    ("Export CSV", ["exports.csv"], False),
    ("Generate PDF reports", ["reports.generate_pdf"], False),
    ("Manage finding templates and report styles", ["templates.manage", "reports.manage_templates"], False),
    ("Use the audit explorer for all events", ["audit.view_all"], False),
    ("See history of their engagements and findings", ["audit.view_engagement"], False),
    ("Verify and export the audit chain", ["audit.verify_integrity", "audit.export"], False),
    ("Use the calendar", ["calendar.view"], False),
]


def capability_table() -> str:
    rows = []
    for label, perms, kind in CAPABILITIES:
        cells = []
        for k in ROLE_KEYS:
            if perms is None:
                spec = SYSTEM_ROLES[k]
                ok = spec["all_engagements"] if kind == "all" else spec["finding_scope"] == kind
            else:
                ok = all(c in SYSTEM_ROLES[k]["grants"] for c in perms) if kind is True else holds(k, perms)
            cells.append('<td class="yes">Yes</td>' if ok else '<td class="no">-</td>')
        rows.append(f"<tr><td>{html.escape(label)}</td>{''.join(cells)}</tr>")
    head = "".join(f"<th>{ROLE_NAMES[k]}</th>" for k in ROLE_KEYS)
    return f'<table class="matrix"><thead><tr><th>Capability</th>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table>'


def transitions_table() -> str:
    rows = []
    for r in RULES:
        src = ", ".join(STATUS[s] for s in r.sources)
        note = "Required" if r.note == "required" else "No"
        extra = {"expiry": " Expiry date.", "duplicate_of": " Original finding."}
        needs = "".join(extra[n] for n in r.needs)
        rows.append(
            f"<tr><td><strong>{html.escape(r.name.replace('_', ' ').capitalize())}</strong></td><td>{html.escape(src)}</td>"
            f"<td>{STATUS[r.target]}</td><td>{role_list(r.perms)}</td><td>{note}{needs}</td></tr>"
        )
    return (
        '<table class="wide"><thead><tr><th>Move</th><th>From</th><th>To</th><th>Allowed by default for</th>'
        f"<th>Needs</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


def permission_table() -> str:
    rows = []
    for code, (scope, desc) in PERMISSIONS.items():
        cells = "".join(
            '<td class="yes">Yes</td>' if code in SYSTEM_ROLES[k]["grants"] else '<td class="no">-</td>' for k in ROLE_KEYS
        )
        rows.append(
            f'<tr><td class="mono">{code}</td><td>{"Platform" if scope == PLATFORM else "Engagement"}</td>{cells}<td>{html.escape(desc)}</td></tr>'
        )
    head = "".join(f"<th>{n}</th>" for n in ("Super Admin", "Pentester", "Remediation", "Vendor"))
    return (
        f'<table class="perm"><thead><tr><th>Permission</th><th>Scope</th>{head}<th>What it allows</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>'
    )


# ------------------------------------------------------------------ markdown -> html

MD = markdown.Markdown(extensions=["tables", "attr_list", "fenced_code", "sane_lists"])
SHOTS = {p.name: p for p in (HERE / "shots").iterdir() if p.suffix in (".png", ".jpg")}
used_shots: set[str] = set()


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def render_chapter(text: str) -> str:
    text = text.replace("[[VERSION]]", VERSION).replace("[[DATE]]", TODAY.strftime("%-d %B %Y"))
    text = text.replace("[[CAPABILITIES]]", capability_table()).replace("[[TRANSITIONS]]", transitions_table())
    text = text.replace("[[PERMISSIONS]]", permission_table())
    for tag, (key, label) in CHIPS.items():
        text = text.replace("{" + tag + "}", chip(key, label))
    MD.reset()
    body = MD.convert(text).replace("<ol>", '<ol class="steps">')

    def figure(m):
        alt, name = html.unescape(m.group(1)), m.group(2)
        if name not in SHOTS:
            raise SystemExit(f"missing screenshot: {name}")
        used_shots.add(name)
        mime = "image/jpeg" if name.endswith(".jpg") else "image/png"
        cls = "figure phone" if "mobile" in name else "figure"
        return f'<figure class="{cls}"><img src="{data_uri(SHOTS[name], mime)}" alt="{html.escape(alt)}"><figcaption>{html.escape(alt)}</figcaption></figure>'

    body = re.sub(r"<p><img alt=\"([^\"]*)\" src=\"([^\"]+)\"\s*/?></p>", figure, body)

    def callout(m):
        kind = m.group(1).lower()
        return f'<blockquote class="callout {kind}"><p><strong>{m.group(1)}</strong>'

    body = re.sub(r"<blockquote>\s*<p><strong>(Note|Tip|Warning|Important|Example)\b", callout, body)
    return body


def heading_ids(body: str) -> tuple[str, list[tuple[int, str, str]]]:
    toc: list[tuple[int, str, str]] = []

    def repl(m):
        level, attrs, inner = int(m.group(1)), m.group(2) or "", m.group(3)
        plain = html.unescape(re.sub(r"<[^>]+>", "", inner))
        sid = slug(plain)
        if level <= 2:
            toc.append((level, sid, plain))
        return f'<h{level}{attrs} id="{sid}">{inner}</h{level}>'

    return re.sub(r"<h([12])((?:\s[^>]*)?)>(.*?)</h\1>", repl, body, flags=re.S), toc


def numbered_toc(entries: list[tuple[int, str, str, bool]]) -> str:
    out, chapter = [], 0
    for level, sid, title, appendix in entries:
        if level == 1:
            if appendix:
                label = f"Appendix {chr(ord('A') + chapter_app(entries, sid))}"
            else:
                chapter += 1
                label = f"{chapter}"
            out.append(f'<li class="l1"><a href="#{sid}"><span class="n">{label}</span>{html.escape(title)}</a></li>')
        else:
            out.append(f'<li class="l2"><a href="#{sid}">{html.escape(title)}</a></li>')
    return "<ol class='toc'>" + "".join(out) + "</ol>"


def chapter_app(entries, sid) -> int:
    apps = [e[1] for e in entries if e[0] == 1 and e[3]]
    return apps.index(sid)


# ------------------------------------------------------------------ assembly


def build() -> None:
    chapters, entries = [], []
    for path in sorted((HERE / "content").glob("*.md")):
        body = render_chapter(path.read_text())
        body, toc = heading_ids(body)
        appendix = path.name.startswith("9")
        for level, sid, title in toc:
            entries.append((level, sid, title, appendix))
        chapters.append(body)
    css_fonts = "".join(
        f'@font-face{{font-family:"Geist";font-weight:{w};src:url("{(FONTS / f"geist-latin-{w}-normal.woff").as_uri()}")}}'
        f'@font-face{{font-family:"Geist Mono";font-weight:{w};src:url("{(FONTS / f"geist-mono-latin-{w}-normal.woff").as_uri()}")}}'
        for w in (400, 500, 600)
    ) + f'@font-face{{font-family:"Geist";font-weight:700;src:url("{(FONTS / "geist-latin-700-normal.woff").as_uri()}")}}'
    css = css_fonts + (HERE / "manual.css").read_text()

    wordmark = data_uri(BRAND / "redshadow-eclipse-white.svg", "image/svg+xml")
    wolf = data_uri(BRAND / "shadowconn-wolf-white.svg", "image/svg+xml")
    shadowword = data_uri(BRAND / "shadowconn-wordmark-white.svg", "image/svg+xml")
    ink_mark = data_uri(BRAND / "redshadow-eclipse-ink.svg", "image/svg+xml")

    logo_tag = f'<p class="tag-logo">{html.escape(TAGLINE)}</p>' if TAGLINE_STYLE == "logo" else ""
    title_tag = f'<p class="tag-title">{html.escape(TAGLINE)}</p>' if TAGLINE_STYLE == "title" else ""
    cover = f"""
<section class="cover">
  <svg class="cover-o" viewBox="0 0 84 100" aria-hidden="true"><path fill="rgba(255,255,255,.10)" fill-rule="evenodd" d="M27 0H57C71.9 0 84 12.1 84 27V73C84 87.9 71.9 100 57 100H27C12.1 100 0 87.9 0 73V27C0 12.1 12.1 0 27 0ZM26 17C22.7 17 20 19.7 20 23V77C20 80.3 22.7 83 26 83H58C61.3 83 64 80.3 64 77V23C64 19.7 61.3 17 58 17Z"/><path fill="rgba(20,4,8,.28)" d="M60 32V77C60 78.1 59.1 79 58 79H26C24.9 79 24 78.1 24 77V68Z"/></svg>
  <div class="cover-top"><img class="cover-logo" src="{wordmark}" alt="RedShadow">{logo_tag}</div>
  <div class="cover-main">
    <p class="eyebrow">Product documentation</p>
    <h1>User and Workflow Manual</h1>{title_tag}
    <p class="cover-sub">Engagements, findings, verification, retests, audit and reporting for Super Admins, Pentesters, Remediation Owners and External Vendors.</p>
    <div class="cover-rule"></div>
    <dl class="cover-meta">
      <div><dt>Version</dt><dd>{VERSION}</dd></div>
      <div><dt>Issued</dt><dd>{TODAY.strftime("%-d %B %Y")}</dd></div>
      <div><dt>Classification</dt><dd>Internal</dd></div>
      <div><dt>Applies to</dt><dd>RedShadow {VERSION}</dd></div>
    </dl>
  </div>
  <p class="cover-credit">Built by <img src="{wolf}" alt="" class="wolf"><img src="{shadowword}" alt="Shadowconn" class="word"></p>
</section>"""

    role_rows = "".join(
        f"<tr><td>{chip(k)}</td><td>{html.escape(d)}</td><td>{html.escape(ch)}</td></tr>"
        for k, d, ch in [
            ("super_admin", "Runs the platform: users, roles, organisations, engagements, audit, reports.", "1 to 5, 9 to 13, all appendices"),
            ("pentester", "Tests assigned engagements: findings, evidence, imports, verification, retests.", "1 to 4, 6, 9, 11, 13"),
            ("remediation", "Fixes findings assigned to them and submits the fix for verification.", "1 to 4, 7, 9, 13"),
            ("external_vendor", "External tester: uploads and manages only their own findings.", "1 to 4, 8, 9, 13"),
        ]
    )
    control = f"""
<section class="docctl">
  <h2 class="plain">Document control</h2>
  <table class="kv">
    <tr><th>Title</th><td>RedShadow User and Workflow Manual</td></tr>
    <tr><th>Version</th><td>{VERSION}</td></tr>
    <tr><th>Issued</th><td>{TODAY.strftime("%-d %B %Y")}</td></tr>
    <tr><th>Applies to</th><td>RedShadow {VERSION} (Docker Compose deployment)</td></tr>
    <tr><th>Classification</th><td>Internal. Do not publish outside your organisation.</td></tr>
    <tr><th>Author</th><td>Shadowconn</td></tr>
    <tr><th>Source</th><td>docs/manual in the project; build with <span class="mono">make manual</span></td></tr>
  </table>
  <h3>Revision history</h3>
  <table class="wide"><thead><tr><th>Version</th><th>Date</th><th>Change</th><th>Author</th></tr></thead>
  <tbody><tr><td>{VERSION}</td><td>{TODAY.strftime("%-d %b %Y")}</td><td>First edition. All workflows for the four roles, worked example, feature reference.</td><td>Shadowconn</td></tr></tbody></table>
  <h3>Who should read what</h3>
  <table class="wide"><thead><tr><th>Role</th><th>Purpose</th><th>Chapters</th></tr></thead><tbody>{role_rows}</tbody></table>
  <p class="muted small">Role names match the application. "Remediation Owner" is the person holding the Remediation role.
  Screenshots show a fictional organisation, Acme Corp. No real client data appears in this manual.</p>
</section>"""

    all_html = "\n".join(chapters)
    contents = f'<section class="contents"><h2 class="plain">Contents</h2>{numbered_toc(entries)}</section>'
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>RedShadow User and Workflow Manual {VERSION}</title>
<style>{css}</style></head><body>
{cover}
{control}
{contents}
<main>{all_html}</main>
</body></html>"""
    unused = sorted(set(SHOTS) - used_shots)
    if unused:
        print("unused screenshots:", ", ".join(unused))
    HTML(string=doc, base_url=str(HERE)).write_pdf(OUT)
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    build()
