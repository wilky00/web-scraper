# ABOUTME: Unit tests for ORM model structure — column names, types, relationships, defaults.
# ABOUTME: No database connection required; tests inspect SQLAlchemy metadata only.
from __future__ import annotations

import pytest
from sqlalchemy import inspect as sa_inspect

from app.models import (
    Base,
    BusinessRecord,
    Connector,
    CrawlJob,
    CrawlJobEvent,
    CrawlPage,
    CriteriaGroup,
    CriteriaVersion,
    Export,
    RawSearchResult,
    RecordAuditLog,
    RecordSource,
    User,
)

ALL_MODELS = [
    User,
    CriteriaGroup,
    CriteriaVersion,
    Connector,
    CrawlJob,
    CrawlJobEvent,
    RawSearchResult,
    CrawlPage,
    BusinessRecord,
    RecordSource,
    RecordAuditLog,
    Export,
]

EXPECTED_TABLE_NAMES = {
    "users",
    "criteria_groups",
    "criteria_versions",
    "connectors",
    "crawl_jobs",
    "crawl_job_events",
    "raw_search_results",
    "crawl_pages",
    "business_records",
    "record_sources",
    "record_audit_log",
    "exports",
}


def test_all_twelve_tables_registered() -> None:
    tables = set(Base.metadata.tables.keys())
    assert tables == EXPECTED_TABLE_NAMES, (
        f"Missing: {EXPECTED_TABLE_NAMES - tables}  Extra: {tables - EXPECTED_TABLE_NAMES}"
    )


@pytest.mark.parametrize("model", ALL_MODELS)
def test_model_has_uuid_primary_key(model: type) -> None:
    mapper = sa_inspect(model)
    pk_cols = [c for c in mapper.columns if c.primary_key]
    assert len(pk_cols) == 1, f"{model.__name__} should have exactly one PK"
    assert pk_cols[0].name == "id"


@pytest.mark.parametrize(
    "model",
    [m for m in ALL_MODELS if m not in (CrawlJobEvent, RecordAuditLog)],
)
def test_timestamped_models_have_created_and_updated_at(model: type) -> None:
    mapper = sa_inspect(model)
    col_names = {c.name for c in mapper.columns}
    assert "created_at" in col_names, f"{model.__name__} missing created_at"
    assert "updated_at" in col_names, f"{model.__name__} missing updated_at"


@pytest.mark.parametrize("model", [CrawlJobEvent, RecordAuditLog])
def test_append_only_models_have_only_created_at(model: type) -> None:
    mapper = sa_inspect(model)
    col_names = {c.name for c in mapper.columns}
    assert "created_at" in col_names, f"{model.__name__} missing created_at"
    assert "updated_at" not in col_names, (
        f"{model.__name__} should not have updated_at (append-only)"
    )


def test_user_columns() -> None:
    mapper = sa_inspect(User)
    col_names = {c.name for c in mapper.columns}
    assert {"email", "hashed_password", "role", "is_active", "sso_sub"} <= col_names


def test_user_email_is_unique() -> None:
    col = sa_inspect(User).columns["email"]
    table = Base.metadata.tables["users"]
    unique_cols = {
        col.name
        for constraint in table.constraints
        if hasattr(constraint, "columns")
        for col in constraint.columns
        if any(c.name == col.name for c in constraint.columns)
        and constraint.__class__.__name__ == "UniqueConstraint"
    }
    # email index is created with unique=True
    assert col.unique or "email" in unique_cols


def test_criteria_version_has_config_snapshot() -> None:
    col_names = {c.name for c in sa_inspect(CriteriaVersion).columns}
    assert "config_snapshot" in col_names
    assert "group_id" in col_names
    assert "version" in col_names
    assert "is_active" in col_names


def test_crawl_job_has_status_and_snapshot() -> None:
    col_names = {c.name for c in sa_inspect(CrawlJob).columns}
    assert {"status", "config_snapshot", "criteria_version_id", "connector_id"} <= col_names


def test_crawl_job_has_events_relationship() -> None:
    mapper = sa_inspect(CrawlJob)
    rel_names = {r.key for r in mapper.relationships}
    assert "events" in rel_names


def test_crawl_job_event_renamed_metadata_column() -> None:
    # `metadata` was renamed to `event_data` to avoid collision with DeclarativeBase.metadata
    col_names = {c.name for c in sa_inspect(CrawlJobEvent).columns}
    assert "event_data" in col_names
    assert "metadata" not in col_names


def test_business_record_has_score_and_sources() -> None:
    col_names = {c.name for c in sa_inspect(BusinessRecord).columns}
    assert {"match_score", "rule_results", "status", "extra_fields"} <= col_names
    rel_names = {r.key for r in sa_inspect(BusinessRecord).relationships}
    assert "sources" in rel_names


def test_business_record_renamed_metadata_column() -> None:
    col_names = {c.name for c in sa_inspect(BusinessRecord).columns}
    assert "extra_fields" in col_names
    assert "metadata" not in col_names


def test_record_audit_log_has_action_and_diff() -> None:
    col_names = {c.name for c in sa_inspect(RecordAuditLog).columns}
    assert {"action", "resource_type", "resource_id", "diff", "user_id"} <= col_names


def test_export_has_format_and_status() -> None:
    col_names = {c.name for c in sa_inspect(Export).columns}
    assert {"format", "filter_params", "s3_key", "status", "row_count"} <= col_names


def test_uuid_primary_key_has_callable_default() -> None:
    """UUIDPrimaryKeyMixin id column must have a callable default (uuid.uuid4)."""
    mapper = sa_inspect(User)
    id_col = mapper.columns["id"]
    assert id_col.default is not None, "id column must have a default"
    # The default should be a callable-based ColumnDefault wrapping uuid.uuid4
    assert id_col.default.is_callable, "id default must be a callable (not a scalar)"
