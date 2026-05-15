# ABOUTME: Session creation, signing, lookup, and deletion via Redis + itsdangerous.
# ABOUTME: Session IDs are stored in Redis; the cookie holds a signed reference to the ID.
from __future__ import annotations

import json
import secrets
from typing import TypedDict, cast

import itsdangerous
from fastapi import Response
from redis.asyncio import Redis

SESSION_COOKIE = "session_id"
_SESSION_TTL = 86400 * 7  # 7 days


class SessionData(TypedDict):
    user_id: str
    csrf_token: str


def _signer(secret_key: str) -> itsdangerous.URLSafeSerializer:
    return itsdangerous.URLSafeSerializer(secret_key, salt="session")


def sign_session_id(session_id: str, secret_key: str) -> str:
    signed: str = _signer(secret_key).dumps(session_id)
    return signed


def unsign_session_id(signed: str, secret_key: str) -> str | None:
    try:
        result = _signer(secret_key).loads(signed)
        return cast(str, result)
    except itsdangerous.BadSignature:
        return None


async def create_session(redis: Redis, user_id: str) -> tuple[str, str]:
    """Create a new session in Redis. Returns (session_id, csrf_token)."""
    session_id = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    payload = json.dumps({"user_id": user_id, "csrf_token": csrf_token})
    await redis.set(f"session:{session_id}", payload, ex=_SESSION_TTL)
    return session_id, csrf_token


async def get_session(redis: Redis, signed: str, secret_key: str) -> SessionData | None:
    session_id = unsign_session_id(signed, secret_key)
    if not session_id:
        return None
    raw = await redis.get(f"session:{session_id}")
    if not raw:
        return None
    return cast(SessionData, json.loads(raw))


async def delete_session(redis: Redis, signed: str, secret_key: str) -> None:
    session_id = unsign_session_id(signed, secret_key)
    if session_id:
        await redis.delete(f"session:{session_id}")


def set_session_cookie(response: Response, signed: str, secure: bool = False) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        signed,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=_SESSION_TTL,
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, httponly=True, samesite="lax")
