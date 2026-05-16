# ABOUTME: Connectors API — lists enabled connectors from the database.
# ABOUTME: Session-authenticated; consumed by the job creation form in the web UI.
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import require_operator
from app.models.connector import Connector
from app.models.user import User

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.get("/api/connectors")
async def list_connectors(
    request: Request,
    user: User = Depends(require_operator),
) -> JSONResponse:
    async with AsyncSession(request.app.state.engine) as db:
        result = await db.execute(
            select(Connector).where(Connector.enabled.is_(True)).order_by(Connector.name.asc())
        )
        connectors = list(result.scalars().all())

    return JSONResponse(
        {
            "connectors": [
                {
                    "id": str(c.id),
                    "name": c.name,
                    "connector_type": c.connector_type,
                    "enabled": c.enabled,
                }
                for c in connectors
            ]
        }
    )
