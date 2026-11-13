"""Markdown to safe HTML for server-rendered output (PDF reports, previews).

User text is rendered with Python-Markdown, then everything outside a small allow-list is removed
by nh3 (raw HTML, scripts, event handlers, images and non-http(s) links are dropped).
The stored value is never changed: this runs only when rendering.
"""

import markdown
import nh3

ALLOWED_TAGS = {
    "p", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6", "strong", "em", "b", "i", "code", "pre", "blockquote",
    "ul", "ol", "li", "a", "table", "thead", "tbody", "tr", "th", "td", "del",
}  # fmt: skip
ALLOWED_ATTRIBUTES = {"a": {"href", "title"}}
ALLOWED_SCHEMES = {"http", "https", "mailto"}


def render_markdown(text: str) -> str:
    html = markdown.markdown(text or "", extensions=["fenced_code", "tables", "sane_lists"])
    return nh3.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=ALLOWED_SCHEMES,
        link_rel="noopener noreferrer nofollow",
        strip_comments=True,
    )
