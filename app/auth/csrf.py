# ABOUTME: CSRF token generation and validation for the login form (pre-session).
# ABOUTME: Uses a double-submit signed cookie: signed value in cookie, plain token in form field.
from __future__ import annotations

import secrets

import itsdangerous


def _signer(secret_key: str) -> itsdangerous.URLSafeTimedSerializer:
    return itsdangerous.URLSafeTimedSerializer(secret_key, salt="csrf-login")


def generate_form_csrf(secret_key: str) -> tuple[str, str]:
    """Return (plain_token, signed_cookie_value) for the login form.

    plain_token goes in the hidden form field; signed_cookie_value goes in the cookie.
    """
    token = secrets.token_urlsafe(32)
    signed: str = _signer(secret_key).dumps(token)
    return token, signed


def verify_form_csrf(form_token: str, cookie_value: str, secret_key: str) -> bool:
    """Return True if the form token matches the signed cookie (max age 1 hour)."""
    try:
        expected = _signer(secret_key).loads(cookie_value, max_age=3600)
        return secrets.compare_digest(str(expected), form_token)
    except itsdangerous.BadData:
        return False
