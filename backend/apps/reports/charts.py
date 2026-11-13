"""Charts for the PDF as inline SVG built here (no plotting library). Every bar carries its number and name, so
the chart still reads in greyscale print. All inserted text is escaped."""

from django.utils.html import escape
from django.utils.safestring import mark_safe

SEVERITY_COLOURS = {
    "critical": "#b3261e",
    "high": "#b83a0c",
    "medium": "#8a5a00",
    "low": "#1d4ed8",
    "info": "#475569",
}
SEVERITY_LABELS = {"critical": "Critical", "high": "High", "medium": "Medium", "low": "Low", "info": "Info"}
SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]

STATUS_COLOURS = {
    "open": "#b3261e",
    "reopened": "#b83a0c",
    "in_progress": "#1d4ed8",
    "pending_verification": "#6d28d9",
    "closed": "#15803d",
    "risk_accepted": "#8a5a00",
    "false_positive": "#64748b",
    "duplicate": "#94a3b8",
}


def severity_bars(counts: dict[str, int]) -> str:
    """One horizontal bar per severity, drawn from the largest bar. Pattern stripes separate the greys."""
    width, row, left, right = 520, 34, 78, 46
    peak = max(counts.values(), default=0) or 1
    height = row * len(SEVERITY_ORDER) + 6
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" '
        'aria-label="Findings by severity">'
    ]
    for i, key in enumerate(SEVERITY_ORDER):
        y = i * row + 4
        n = counts.get(key, 0)
        bar = max((width - left - right) * n / peak, 3 if n else 0)
        colour = SEVERITY_COLOURS[key]
        parts.append(
            f'<text x="0" y="{y + 19}" font-size="12.5" font-weight="600" fill="#1f3038">'
            f"{escape(SEVERITY_LABELS[key])}</text>"
            f'<rect x="{left}" y="{y + 4}" width="{width - left - right}" height="20" rx="4" fill="#eef1f3"/>'
            f'<rect x="{left}" y="{y + 4}" width="{bar:.1f}" height="20" rx="4" fill="{colour}"/>'
            f'<text x="{width}" y="{y + 19}" font-size="13" font-weight="700" fill="#1f3038" '
            f'text-anchor="end">{n}</text>'
        )
    parts.append("</svg>")
    return mark_safe("".join(parts))  # noqa: S308  # nosec B703 B308 - every value above is a number, a constant or escaped


def status_strip(counts: dict[str, int], labels: dict[str, str]) -> str:
    """A single stacked bar of findings by status with a labelled legend underneath."""
    total = sum(counts.values())
    width = 520
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} 78" role="img" aria-label="Findings by status">'
    ]
    if total == 0:
        parts.append(f'<rect x="0" y="4" width="{width}" height="18" rx="4" fill="#eef1f3"/>')
    else:
        x = 0.0
        for key, n in counts.items():
            if not n:
                continue
            w = width * n / total
            parts.append(
                f'<rect x="{x:.1f}" y="4" width="{w:.1f}" height="18" fill="{STATUS_COLOURS.get(key, "#64748b")}"/>'
            )
            x += w
    lx, ly = 0, 44
    for key, n in counts.items():
        if not n:
            continue
        text = f"{labels.get(key, key)} {n}"
        parts.append(
            f'<rect x="{lx}" y="{ly - 9}" width="10" height="10" rx="2" fill="{STATUS_COLOURS.get(key, "#64748b")}"/>'
            f'<text x="{lx + 15}" y="{ly}" font-size="11" fill="#1f3038">{escape(text)}</text>'
        )
        lx += 22 + len(text) * 6.4
        if lx > width - 110:
            lx, ly = 0, ly + 18
    parts.append("</svg>")
    return mark_safe("".join(parts))  # noqa: S308 - see above
