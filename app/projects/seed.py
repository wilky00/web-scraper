# ABOUTME: Seeds the "Default" project on every startup if it doesn't already exist.
# ABOUTME: The Default project is permanent; unscoped criteria/connectors belong to it implicitly.
from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.models.project import Project

logger = structlog.get_logger()


async def seed_default_project(engine: AsyncEngine) -> None:
    """Create the Default project if it doesn't exist. Idempotent."""
    async with AsyncSession(engine) as db:
        existing = (
            await db.execute(select(Project).where(Project.name == "Default").limit(1))
        ).scalar_one_or_none()

        if existing is not None:
            return

        db.add(
            Project(
                name="Default",
                description="Global project — unscoped criteria and connectors belong here.",
                created_by=None,
            )
        )
        await db.commit()

    logger.info("project.seed.complete", name="Default")
