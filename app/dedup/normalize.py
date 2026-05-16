# ABOUTME: Pure normalization functions for deduplication key generation.
# ABOUTME: No I/O, no state — all functions take a raw string and return a canonical form.
from __future__ import annotations

import re
from urllib.parse import urlparse


def normalize_domain(url: str | None) -> str:
    """Strip scheme, www., trailing slash. Returns '' for None/empty.

    Examples:
        "https://www.example.com/" -> "example.com"
        "www.example.com"         -> "example.com"
        None or ""                -> ""
    """
    if not url:
        return ""
    url = url.strip()
    if not url:
        return ""

    # If the string has a scheme, use urlparse; otherwise treat as bare host.
    if "://" in url:
        parsed = urlparse(url)
        host = parsed.netloc
    else:
        # Bare domain or domain with path — take the part before any slash.
        host = url.split("/")[0]

    host = host.lower()
    # Strip port if present
    host = host.split(":")[0]
    # Strip www. prefix only (preserve other subdomains)
    if host.startswith("www."):
        host = host[4:]
    return host


def normalize_name(name: str | None) -> str:
    """Lowercase, strip non-alphanumeric (keep spaces), collapse whitespace.

    Examples:
        "Joe's Bakery, LLC"       -> "joes bakery llc"
        "  Green Valley   Roofing  " -> "green valley roofing"
        "A&B Services"            -> "ab services"
        None or ""                -> ""
    """
    if not name:
        return ""
    name = name.lower()
    # Keep letters, digits, and spaces; drop everything else
    name = re.sub(r"[^a-z0-9 ]", "", name)
    # Collapse internal whitespace
    name = " ".join(name.split())
    return name


def normalize_phone(phone: str | None) -> str:
    """Strip non-digits. Drop leading 1 from 11-digit numbers. Returns 10 digits or ''.

    Examples:
        "615-555-0101"   -> "6155550101"
        "(615) 555-0101" -> "6155550101"
        "1-615-555-0101" -> "6155550101"
        "16155550101"    -> "6155550101"
        "555-0101"       -> ""   (< 10 digits)
        None             -> ""
    """
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        return ""
    return digits


def normalize_email(email: str | None) -> str:
    """Lowercase and strip whitespace. Returns '' for None/empty.

    Examples:
        "HELLO@Example.COM"       -> "hello@example.com"
        "  hello@example.com  "   -> "hello@example.com"
        None                      -> ""
    """
    if not email:
        return ""
    return email.strip().lower()
