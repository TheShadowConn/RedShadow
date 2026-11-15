"""Turns the collected data into a PDF or CSV file.

The PDF engine (WeasyPrint) is given a fetcher that serves only ``data:`` URIs and the bundled font files. A report
therefore cannot read a local file or call a server, whatever the finding text says.
"""

import base64
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

from django.template.loader import render_to_string
from weasyprint.urls import URLFetcher

from apps.core.csvout import write_csv

from .models import SECTIONS

ASSETS = Path(__file__).resolve().parent / "assets"
FONT_DIR = (ASSETS / "fonts").resolve()
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
FONT_STACKS = {
    "geist": '"Geist", "DejaVu Sans", sans-serif',
    "serif": '"DejaVu Serif", serif',
}


class SafeFetcher(URLFetcher):
    """Serves ``data:`` URIs and ``.woff`` files inside the bundled font folder. Everything else is refused, so a
    report cannot read a local file or call another server."""

    def __init__(self):
        super().__init__(allowed_protocols={"data", "file"}, allow_redirects=False)

    def fetch(self, url, headers=None):
        if not url.startswith("data:"):
            parsed = urlparse(url)
            path = Path(unquote(parsed.path)).resolve() if parsed.scheme == "file" else None
            if path is None or FONT_DIR not in path.parents or path.suffix != ".woff":
                raise ValueError("Blocked resource in a report")
        return super().fetch(url, headers)


safe_fetcher = SafeFetcher()


def _data_uri(path: Path, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def _css_string(text: str) -> str:
    """A CSS string literal for text we did not write (footer, reference)."""
    cleaned = "".join(ch for ch in text if ch.isprintable())
    return '"' + cleaned.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _font_face(family: str, weight: int, file: str) -> str:
    uri = (FONT_DIR / file).as_uri()
    return f'@font-face{{font-family:"{family}";font-weight:{weight};src:url("{uri}")}}'


DEFAULT_ACCENT = "#ef233c"  # Racing Red, the application and manual colour


def _shade(hex_colour: str, factor: float) -> str:
    """Darken (factor < 1) a #rrggbb colour. The cover gradient and heading tones derive from the accent."""
    r, g, b = (int(hex_colour[i : i + 2], 16) for i in (1, 3, 5))
    return "#{:02x}{:02x}{:02x}".format(*(round(c * factor) for c in (r, g, b)))


def _css(accent: str, font: str, footer: str, ref: str) -> str:
    css = (ASSETS / "report.css").read_text()
    faces = [_font_face("Geist", w, f"geist-latin-{w}-normal.woff") for w in (400, 500, 600, 700)]
    faces += [_font_face("Geist Mono", w, f"geist-mono-latin-{w}-normal.woff") for w in (400, 500, 600)]
    colour = accent if HEX.match(accent or "") else DEFAULT_ACCENT
    if len(colour) == 4:  # #rgb
        colour = "#" + "".join(ch * 2 for ch in colour[1:])
    stack = FONT_STACKS.get(font, FONT_STACKS["geist"])
    root = (
        f":root{{--accent:{colour};--accent-deep:{_shade(colour, 0.74)};--accent-dark:{_shade(colour, 0.32)};"
        f"--font:{stack}}}"
    )
    running = (
        f"@page{{@bottom-left{{content:{_css_string(footer or ref)}}}"
        "@top-right{font:500 7.5pt var(--font);color:#6b7882;letter-spacing:.08em;text-transform:uppercase;"
        f"content:{_css_string(ref)}}}}}"
    )
    return "".join(faces) + root + running + css


def build_html(ctx: dict, template) -> str:
    sections = [s for s in (template.sections if template else None) or [] if s != "cover"]
    if "findings" not in sections:
        sections.append("findings")
    names = dict(SECTIONS)
    ctx = {
        **ctx,
        "sections": sections,
        "toc": [(key, names[key]) for key in sections],
        "css": _css(
            template.accent if template else "",
            template.font if template else "geist",
            (template.footer_text if template else "") or "",
            ctx["engagement"].ref,
        ),
        "wordmark_white": _data_uri(ASSETS / "wordmark-white.svg", "image/svg+xml"),
        "wordmark_light": _data_uri(ASSETS / "wordmark-light.svg", "image/svg+xml"),
        "wordmark_dark": _data_uri(ASSETS / "wordmark-dark.svg", "image/svg+xml"),
        "custom_logo": ctx.get("custom_logo", ""),
    }
    return render_to_string("reports/report.html", ctx)


def render_pdf(ctx: dict, template) -> tuple[bytes, int]:
    """Returns the PDF bytes and the number of pages."""
    from weasyprint import HTML

    document = HTML(string=build_html(ctx, template), url_fetcher=safe_fetcher).render()
    return document.write_pdf(), len(document.pages)


CSV_COLUMNS = [
    "reference", "title", "severity", "cvss_score", "cvss_vector", "cwe", "status", "asset", "endpoint",
    "assigned_pentester", "remediation_owner", "discovered_at", "due_date", "resolved_at", "verified_at",
    "closed_at", "overdue", "description", "recommendation", "references",
]  # fmt: skip
CSV_INTERNAL_COLUMNS = ["technical_details", "poc"]


def render_csv(ctx: dict) -> tuple[bytes, int]:
    """CSV of the report's findings. Text is exported as stored (not rendered), so it uses the source rows."""
    internal = ctx["internal"]
    header = CSV_COLUMNS + (CSV_INTERNAL_COLUMNS if internal else [])
    by_ref = {f.ref: f for f in ctx["raw_findings"]}
    rows = []
    for f in ctx["findings"]:
        src = by_ref[f["ref"]]
        row = [
            f["ref"],
            f["title"],
            f["severity"],
            f["cvss_score"] if f["cvss_score"] is not None else "",
            f["cvss_vector"],
            f["cwe"],
            f["status"],
            f["asset"],
            f["endpoint"],
            f["assigned_pentester"],
            f["remediation_owner"],
            f["discovered_at"],
            f["due_date"] or "",
            f["resolved_at"] or "",
            f["verified_at"] or "",
            f["closed_at"] or "",
            "yes" if f["overdue"] else "no",
            src.description,
            src.recommendation,
            "\n".join(f"{r['label']} {r['url']}".strip() for r in f["references"]),
        ]
        if internal:
            row += [src.technical_details, src.poc]
        rows.append(row)
    handle, _digest, count = write_csv(header, rows)
    try:
        return handle.read(), count
    finally:
        handle.close()
