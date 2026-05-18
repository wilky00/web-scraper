# ABOUTME: RQ task for async record export to CSV or XLSX.
# ABOUTME: run_export() is the RQ entry point; queries records, generates file, uploads to S3.
from __future__ import annotations

import asyncio
import csv
import io
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.models.audit import Export, RecordAuditLog
from app.models.job import CrawlJob
from app.models.record import BusinessRecord
from app.services import storage
from app.settings import Settings

logger = structlog.get_logger(__name__)

_CSV_HEADERS = [
    "id",
    "name",
    "website",
    "email",
    "phone",
    "address",
    "location_city",
    "location_state",
    "location_country",
    "match_score",
    "status",
    "job_id",
    "created_at",
]


def run_export(export_id_str: str) -> None:
    """RQ entry point — runs a single export task to completion."""
    asyncio.run(_async_export(export_id_str))


async def _async_export(export_id_str: str) -> None:
    log = logger.bind(export_id=export_id_str)
    settings = Settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True, pool_size=2)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            export_id = uuid.UUID(export_id_str)
            export: Export | None = await session.get(Export, export_id)
            if export is None:
                log.error("export_task.not_found")
                return

            export.status = "processing"
            await session.commit()
            log.info("export_task.started", fmt=export.format)

            try:
                records = await _query_records(session, export.filter_params or {})

                if export.format == "xlsx":
                    data = _build_xlsx(records)
                    content_type = (
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                else:
                    data = _build_csv(records)
                    content_type = "text/csv"

                key = storage.generate_export_key(export_id, export.format)
                await asyncio.to_thread(storage.upload_bytes, data, key, content_type, settings)

                export.s3_key = key
                export.status = "ready"
                export.row_count = len(records)

                session.add(
                    RecordAuditLog(
                        user_id=export.user_id,
                        action="export",
                        resource_type="export",
                        resource_id=str(export_id),
                        diff={"format": export.format, "row_count": len(records)},
                    )
                )
                await session.commit()
                log.info("export_task.complete", row_count=len(records))

            except Exception as exc:
                log.exception("export_task.failed")
                export.status = "failed"
                export.error = str(exc)
                await session.commit()
    finally:
        await engine.dispose()


async def _query_records(
    session: AsyncSession,
    filter_params: dict[str, Any],
) -> list[BusinessRecord]:
    query = select(BusinessRecord)

    q = (filter_params.get("q") or "").strip()
    status = (filter_params.get("status") or "").strip()
    score_min_str = (filter_params.get("score_min") or "").strip()
    score_max_str = (filter_params.get("score_max") or "").strip()
    date_from_str = (filter_params.get("date_from") or "").strip()
    date_to_str = (filter_params.get("date_to") or "").strip()
    project_id_str = (filter_params.get("project_id") or "").strip()

    if project_id_str:
        try:
            pid = uuid.UUID(project_id_str)
            query = query.where(
                BusinessRecord.job_id.in_(select(CrawlJob.id).where(CrawlJob.project_id == pid))
            )
        except ValueError:
            pass

    if q:
        query = query.where(BusinessRecord.name.ilike(f"%{q}%"))
    if status:
        query = query.where(BusinessRecord.status == status)
    if score_min_str:
        try:
            query = query.where(BusinessRecord.match_score >= Decimal(score_min_str))
        except InvalidOperation:
            pass
    if score_max_str:
        try:
            query = query.where(BusinessRecord.match_score <= Decimal(score_max_str))
        except InvalidOperation:
            pass
    if date_from_str:
        try:
            dt = datetime.combine(
                date.fromisoformat(date_from_str), datetime.min.time(), tzinfo=UTC
            )
            query = query.where(BusinessRecord.created_at >= dt)
        except ValueError:
            pass
    if date_to_str:
        try:
            dt = datetime.combine(date.fromisoformat(date_to_str), datetime.max.time(), tzinfo=UTC)
            query = query.where(BusinessRecord.created_at <= dt)
        except ValueError:
            pass

    query = query.order_by(BusinessRecord.created_at.desc())
    result = await session.execute(query)
    return list(result.scalars().all())


def _record_row(r: BusinessRecord) -> list[Any]:
    return [
        str(r.id),
        r.name or "",
        r.website or "",
        r.email or "",
        r.phone or "",
        r.address or "",
        r.location_city or "",
        r.location_state or "",
        r.location_country or "",
        float(r.match_score) if r.match_score is not None else "",
        r.status or "",
        str(r.job_id) if r.job_id else "",
        r.created_at.isoformat() if r.created_at else "",
    ]


def _build_csv(records: list[BusinessRecord]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(_CSV_HEADERS)
    for r in records:
        writer.writerow(_record_row(r))
    return buf.getvalue().encode("utf-8")


def _build_xlsx(records: list[BusinessRecord]) -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Records"
    ws.append(_CSV_HEADERS)
    for r in records:
        ws.append(_record_row(r))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
