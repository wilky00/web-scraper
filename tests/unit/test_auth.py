# ABOUTME: Unit tests for auth primitives: hashing, session signing, CSRF, and rate limiting.
# ABOUTME: No DB or network required — all external calls use AsyncMock.
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.auth.csrf import generate_form_csrf, verify_form_csrf
from app.auth.hashing import hash_password, verify_password
from app.auth.rate_limit import check_login_rate_limit
from app.auth.session import sign_session_id, unsign_session_id

_KEY = "test-secret-key-for-unit-tests!!"


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


class TestPasswordHashing:
    def test_hash_returns_bcrypt_prefix(self) -> None:
        h = hash_password("mysecret")
        assert h.startswith("$2b$")

    def test_verify_correct_password(self) -> None:
        h = hash_password("correct")
        assert verify_password("correct", h) is True

    def test_verify_wrong_password(self) -> None:
        h = hash_password("correct")
        assert verify_password("wrong", h) is False

    def test_two_hashes_of_same_password_differ(self) -> None:
        # bcrypt salts are random
        assert hash_password("same") != hash_password("same")


# ---------------------------------------------------------------------------
# Session signing
# ---------------------------------------------------------------------------


class TestSessionSigning:
    def test_sign_unsign_roundtrip(self) -> None:
        session_id = "abc123xyz"
        signed = sign_session_id(session_id, _KEY)
        assert unsign_session_id(signed, _KEY) == session_id

    def test_unsign_tampered_value_returns_none(self) -> None:
        signed = sign_session_id("legit", _KEY)
        tampered = signed[:-4] + "xxxx"
        assert unsign_session_id(tampered, _KEY) is None

    def test_unsign_wrong_key_returns_none(self) -> None:
        signed = sign_session_id("legit", _KEY)
        assert unsign_session_id(signed, "different-key") is None

    def test_signed_value_differs_from_session_id(self) -> None:
        session_id = "raw-session-id"
        assert sign_session_id(session_id, _KEY) != session_id


# ---------------------------------------------------------------------------
# CSRF tokens
# ---------------------------------------------------------------------------


class TestCSRF:
    def test_generate_returns_two_distinct_strings(self) -> None:
        token, cookie = generate_form_csrf(_KEY)
        assert isinstance(token, str)
        assert isinstance(cookie, str)
        assert token != cookie

    def test_verify_valid_pair_returns_true(self) -> None:
        token, cookie = generate_form_csrf(_KEY)
        assert verify_form_csrf(token, cookie, _KEY) is True

    def test_verify_wrong_token_returns_false(self) -> None:
        _, cookie = generate_form_csrf(_KEY)
        assert verify_form_csrf("wrong-token", cookie, _KEY) is False

    def test_verify_tampered_cookie_returns_false(self) -> None:
        token, cookie = generate_form_csrf(_KEY)
        assert verify_form_csrf(token, cookie[:-4] + "xxxx", _KEY) is False

    def test_verify_wrong_key_returns_false(self) -> None:
        token, cookie = generate_form_csrf(_KEY)
        assert verify_form_csrf(token, cookie, "different-key") is False

    def test_each_call_generates_unique_pair(self) -> None:
        token1, _ = generate_form_csrf(_KEY)
        token2, _ = generate_form_csrf(_KEY)
        assert token1 != token2


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


class TestRateLimit:
    @pytest.mark.asyncio
    async def test_first_attempt_allowed(self) -> None:
        redis = AsyncMock()
        redis.incr = AsyncMock(return_value=1)
        redis.expire = AsyncMock(return_value=True)
        assert await check_login_rate_limit(redis, "1.2.3.4") is True

    @pytest.mark.asyncio
    async def test_tenth_attempt_allowed(self) -> None:
        redis = AsyncMock()
        redis.incr = AsyncMock(return_value=10)
        redis.expire = AsyncMock(return_value=True)
        assert await check_login_rate_limit(redis, "1.2.3.4") is True

    @pytest.mark.asyncio
    async def test_eleventh_attempt_blocked(self) -> None:
        redis = AsyncMock()
        redis.incr = AsyncMock(return_value=11)
        redis.expire = AsyncMock(return_value=True)
        assert await check_login_rate_limit(redis, "1.2.3.4") is False

    @pytest.mark.asyncio
    async def test_expire_called_on_first_attempt(self) -> None:
        redis = AsyncMock()
        redis.incr = AsyncMock(return_value=1)
        redis.expire = AsyncMock(return_value=True)
        await check_login_rate_limit(redis, "1.2.3.4")
        redis.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_expire_not_called_on_subsequent_attempts(self) -> None:
        redis = AsyncMock()
        redis.incr = AsyncMock(return_value=5)
        redis.expire = AsyncMock(return_value=True)
        await check_login_rate_limit(redis, "1.2.3.4")
        redis.expire.assert_not_called()
