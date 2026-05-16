# ABOUTME: S3/MinIO storage helpers — upload_bytes(), download_bytes(), and key generators.
# ABOUTME: All functions are synchronous; use asyncio.to_thread() when calling from async code.
from __future__ import annotations

import hashlib
import uuid
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from app.settings import Settings

logger = structlog.get_logger(__name__)


class StorageError(Exception):
    pass


class StorageNotFoundError(StorageError):
    pass


def _make_client(settings: Settings) -> Any:
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
        aws_access_key_id=settings.s3_access_key_id or None,
        aws_secret_access_key=settings.s3_secret_access_key or None,
    )


def upload_bytes(data: bytes, key: str, content_type: str, settings: Settings) -> str:
    """Upload bytes to S3/MinIO. Returns the object key. Raises StorageError on failure."""
    try:
        client = _make_client(settings)
        client.put_object(
            Bucket=settings.s3_bucket_name,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        logger.info("storage.uploaded", key=key, size=len(data))
        return key
    except Exception as exc:
        logger.exception("storage.upload_failed", key=key)
        raise StorageError(f"Upload failed: {exc}") from exc


def download_bytes(key: str, settings: Settings) -> bytes:
    """Download object by key. Raises StorageNotFoundError if key does not exist."""
    from botocore.exceptions import ClientError

    try:
        client = _make_client(settings)
        response = client.get_object(Bucket=settings.s3_bucket_name, Key=key)
        return response["Body"].read()  # type: ignore[no-any-return]
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
            raise StorageNotFoundError(f"Not found: {key}") from exc
        logger.exception("storage.download_failed", key=key)
        raise StorageError(f"Download failed: {exc}") from exc
    except Exception as exc:
        logger.exception("storage.download_failed", key=key)
        raise StorageError(f"Download failed: {exc}") from exc


def generate_export_key(export_id: uuid.UUID, fmt: str) -> str:
    return f"exports/{export_id}.{fmt}"


def generate_html_key(job_id: uuid.UUID, url: str) -> str:
    url_hash = hashlib.sha256(url.encode()).hexdigest()
    return f"html/{job_id}/{url_hash}.html"
