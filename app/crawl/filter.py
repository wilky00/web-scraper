# ABOUTME: URL and content-type filtering — blocked path patterns and binary
# ABOUTME: content-type detection from crawl.yml configuration.
from __future__ import annotations

from fnmatch import fnmatch
from urllib.parse import urlparse

_GLOB_CHARS = frozenset("*?[")


def is_path_blocked(url: str, blocked_patterns: list[str]) -> bool:
    """Return True if the URL path matches any blocked pattern.

    Patterns without glob characters are treated as path-prefix matches:
    ``/admin`` blocks ``/admin``, ``/admin/``, ``/admin/users`` but not
    ``/administrator``.  Patterns containing ``*``, ``?``, or ``[`` are
    matched with fnmatch.
    """
    path = urlparse(url).path
    for pattern in blocked_patterns:
        if _GLOB_CHARS.intersection(pattern):
            if fnmatch(path, pattern):
                return True
        else:
            prefix = pattern.rstrip("/")
            if path == prefix or path.startswith(prefix + "/"):
                return True
    return False


def is_content_type_blocked(content_type: str, blocked_prefixes: list[str]) -> bool:
    """Return True if the content type matches any blocked prefix.

    Parameters (e.g. ``; charset=utf-8``) are stripped before comparison.
    """
    ct = content_type.split(";")[0].strip().lower()
    return any(ct.startswith(prefix.lower()) for prefix in blocked_prefixes)
