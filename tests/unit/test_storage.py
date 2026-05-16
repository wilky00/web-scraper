# ABOUTME: Unit tests for app/services/storage.py — upload, download, and key-generation helpers.
# ABOUTME: All boto3 calls are mocked; no real S3/MinIO connection required.
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.services.storage import (
    StorageError,
    StorageNotFoundError,
    download_bytes,
    generate_export_key,
    generate_html_key,
    upload_bytes,
)
from app.settings import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings()


# ── Key generation ────────────────────────────────────────────────────────────


def test_generate_export_key_csv() -> None:
    eid = uuid.UUID("00000000-0000-0000-0000-000000000001")
    assert generate_export_key(eid, "csv") == f"exports/{eid}.csv"


def test_generate_export_key_xlsx() -> None:
    eid = uuid.UUID("00000000-0000-0000-0000-000000000002")
    assert generate_export_key(eid, "xlsx") == f"exports/{eid}.xlsx"


def test_generate_html_key_format() -> None:
    jid = uuid.UUID("00000000-0000-0000-0000-000000000003")
    key = generate_html_key(jid, "https://example.com/page")
    assert key.startswith(f"html/{jid}/")
    assert key.endswith(".html")


def test_generate_html_key_deterministic() -> None:
    jid = uuid.UUID("00000000-0000-0000-0000-000000000004")
    url = "https://example.com/page"
    assert generate_html_key(jid, url) == generate_html_key(jid, url)


def test_generate_html_key_different_urls_produce_different_keys() -> None:
    jid = uuid.UUID("00000000-0000-0000-0000-000000000005")
    assert generate_html_key(jid, "https://a.com") != generate_html_key(jid, "https://b.com")


# ── upload_bytes ──────────────────────────────────────────────────────────────


def test_upload_bytes_success(settings: Settings) -> None:
    mock_client = MagicMock()
    with patch("app.services.storage._make_client", return_value=mock_client):
        result = upload_bytes(b"hello", "some/key.csv", "text/csv", settings)

    assert result == "some/key.csv"
    mock_client.put_object.assert_called_once_with(
        Bucket=settings.s3_bucket_name,
        Key="some/key.csv",
        Body=b"hello",
        ContentType="text/csv",
    )


def test_upload_bytes_raises_storage_error_on_failure(settings: Settings) -> None:
    mock_client = MagicMock()
    mock_client.put_object.side_effect = Exception("connection refused")
    with patch("app.services.storage._make_client", return_value=mock_client):
        with pytest.raises(StorageError, match="Upload failed"):
            upload_bytes(b"data", "key", "text/csv", settings)


# ── download_bytes ────────────────────────────────────────────────────────────


def test_download_bytes_success(settings: Settings) -> None:
    mock_client = MagicMock()
    mock_body = MagicMock()
    mock_body.read.return_value = b"file content"
    mock_client.get_object.return_value = {"Body": mock_body}

    with patch("app.services.storage._make_client", return_value=mock_client):
        data = download_bytes("some/key.csv", settings)

    assert data == b"file content"
    mock_client.get_object.assert_called_once_with(
        Bucket=settings.s3_bucket_name,
        Key="some/key.csv",
    )


def test_download_bytes_raises_not_found_on_no_such_key(settings: Settings) -> None:
    from botocore.exceptions import ClientError

    mock_client = MagicMock()
    error = ClientError({"Error": {"Code": "NoSuchKey", "Message": "Not found"}}, "GetObject")
    mock_client.get_object.side_effect = error

    with patch("app.services.storage._make_client", return_value=mock_client):
        with pytest.raises(StorageNotFoundError):
            download_bytes("missing/key.csv", settings)


def test_download_bytes_raises_storage_error_on_other_failure(settings: Settings) -> None:
    mock_client = MagicMock()
    mock_client.get_object.side_effect = Exception("network error")

    with patch("app.services.storage._make_client", return_value=mock_client):
        with pytest.raises(StorageError, match="Download failed"):
            download_bytes("key", settings)
