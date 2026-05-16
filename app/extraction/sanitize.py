# ABOUTME: HTML sanitization using bleach allowlist to strip unsafe tags and attributes.
# ABOUTME: Safe to call before rendering extracted page content in the browser.
from __future__ import annotations

import bleach
from bs4 import BeautifulSoup

_ALLOWED_TAGS: frozenset[str] = frozenset(
    {
        "p",
        "br",
        "ul",
        "ol",
        "li",
        "b",
        "strong",
        "i",
        "em",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "a",
        "span",
        "div",
        "table",
        "thead",
        "tbody",
        "tr",
        "th",
        "td",
        "blockquote",
        "pre",
        "code",
    }
)

_ALLOWED_ATTRS: dict[str, list[str]] = {
    "a": ["href", "title"],
    "*": ["class"],
}


def sanitize_html(html: str) -> str:
    # Strip script/style tags and their content before passing to bleach,
    # because bleach with strip=True removes the tag wrapper but preserves the text.
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    cleaned = str(soup)
    return bleach.clean(
        cleaned,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        strip=True,
        strip_comments=True,
    )
