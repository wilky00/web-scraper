# ABOUTME: Redis-backed login rate limiter. Tracks failed attempts per IP address.
# ABOUTME: Allows 10 attempts per 60-second window; subsequent attempts return False.
from __future__ import annotations

from redis.asyncio import Redis

_MAX_ATTEMPTS = 10
_WINDOW_SECONDS = 60


async def check_login_rate_limit(redis: Redis, ip: str) -> bool:
    """Return True if the IP is within the allowed limit, False if it should be blocked."""
    key = f"rate_limit:login:{ip}"
    count = await redis.incr(key)
    if int(count) == 1:
        await redis.expire(key, _WINDOW_SECONDS)
    return int(count) <= _MAX_ATTEMPTS
