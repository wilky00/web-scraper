# ABOUTME: First-boot operator seeding. Creates one operator user if the users table is empty.
# ABOUTME: Called from the FastAPI lifespan; safe to run on every startup (idempotent).
from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.auth.hashing import hash_password
from app.models.user import User

logger = structlog.get_logger()


async def seed_operator(engine: AsyncEngine, email: str, password: str) -> None:
    """Create the seed operator if no users exist. Does nothing if any user already exists."""
    if not password:
        logger.warning("auth.seed.skipped", reason="SEED_OPERATOR_PASSWORD not set")
        return

    async with AsyncSession(engine) as db:
        result = await db.execute(select(User).limit(1))
        if result.scalar_one_or_none() is not None:
            return

        user = User(
            email=email.lower().strip(),
            hashed_password=hash_password(password),
            role="operator",
            is_active=True,
        )
        db.add(user)
        await db.commit()
        logger.info("auth.seed.operator_created", email=email)
