# ABOUTME: URL canonicalization for deduplication — normalizes scheme/host, strips
# ABOUTME: fragments, resolves path segments, and sorts query parameters.
from __future__ import annotations

from posixpath import normpath
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


def canonicalize(url: str) -> str:
    """Return a normalized URL suitable for deduplication.

    Transformations applied:
    - Lowercases scheme and host
    - Removes default ports (80 for http, 443 for https)
    - Resolves . and .. path segments
    - Removes URL fragment
    - Sorts query parameters; last value wins on duplicate keys
    """
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return url

    if not parsed.scheme or not parsed.netloc:
        return url

    scheme = parsed.scheme.lower()

    netloc = parsed.netloc.lower()
    if ":" in netloc:
        host, _, port = netloc.rpartition(":")
        if (scheme == "http" and port == "80") or (scheme == "https" and port == "443"):
            netloc = host

    raw_path = parsed.path
    if raw_path:
        path = normpath(raw_path)
        # normpath collapses // and resolves . / .. but returns "." for empty input
        if path == ".":
            path = "/"
    else:
        path = "/"

    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    deduped: dict[str, str] = {}
    for k, v in pairs:
        deduped[k] = v
    query = urlencode(sorted(deduped.items()))

    return urlunparse((scheme, netloc, path, parsed.params, query, ""))
