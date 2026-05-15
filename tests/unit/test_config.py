# ABOUTME: Unit tests for runtime config Pydantic models: app, connectors, crawl, retention.
# ABOUTME: Covers YAML loader error paths using pytest's tmp_path fixture.
from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config.loader import (
    ConfigLoadError,
    load_all_configs,
    load_app_config,
    load_crawl_config,
    load_retention_config,
)
from app.config.models import (
    AppConfig,
    ConnectorsConfig,
    CrawlConfig,
    FeaturesConfig,
    RetentionConfig,
    RetentionDays,
)

# ---------------------------------------------------------------------------
# AppConfig
# ---------------------------------------------------------------------------


class TestAppConfig:
    def test_valid_minimal(self) -> None:
        config = AppConfig(base_url="http://localhost:8000")
        assert config.environment == "local"
        assert config.default_page_size == 25
        assert config.max_page_size == 100
        assert config.roles == ["operator"]

    def test_valid_full(self) -> None:
        config = AppConfig(
            app_name="My Scraper",
            base_url="https://example.com",
            environment="staging",
            default_page_size=50,
            max_page_size=200,
            roles=["operator", "viewer"],
        )
        assert config.app_name == "My Scraper"
        assert config.environment == "staging"
        assert config.roles == ["operator", "viewer"]

    def test_missing_base_url_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            AppConfig()  # type: ignore[call-arg]
        assert "base_url" in str(exc_info.value)

    def test_invalid_environment_raises(self) -> None:
        with pytest.raises(ValidationError):
            AppConfig(base_url="http://localhost", environment="dev")  # type: ignore[arg-type]

    def test_all_valid_environments(self) -> None:
        for env in ("local", "staging", "production"):
            config = AppConfig(base_url="http://localhost", environment=env)  # type: ignore[arg-type]
            assert config.environment == env

    def test_features_defaults(self) -> None:
        config = AppConfig(base_url="http://localhost")
        assert config.features.ai_assist is False
        assert config.features.brave_connector is False
        assert config.features.api_docs is True

    def test_features_override(self) -> None:
        config = AppConfig(
            base_url="http://localhost",
            features=FeaturesConfig(ai_assist=True, api_docs=False),
        )
        assert config.features.ai_assist is True
        assert config.features.api_docs is False

    def test_page_size_bounds(self) -> None:
        with pytest.raises(ValidationError):
            AppConfig(base_url="http://localhost", default_page_size=0)
        with pytest.raises(ValidationError):
            AppConfig(base_url="http://localhost", max_page_size=1001)


# ---------------------------------------------------------------------------
# CrawlConfig
# ---------------------------------------------------------------------------


class TestCrawlConfig:
    def test_defaults(self) -> None:
        config = CrawlConfig()
        assert config.max_pages_per_job == 500
        assert config.max_pages_per_domain == 50
        assert config.max_depth == 3
        assert config.timeout_seconds == 30
        assert config.delay_between_requests_ms == 1000
        assert config.blocked_path_patterns == []

    def test_blocked_paths_populated(self) -> None:
        config = CrawlConfig(blocked_path_patterns=["/admin", "/login"])
        assert "/admin" in config.blocked_path_patterns

    def test_negative_max_depth_raises(self) -> None:
        with pytest.raises(ValidationError):
            CrawlConfig(max_depth=-1)

    def test_max_depth_above_limit_raises(self) -> None:
        with pytest.raises(ValidationError):
            CrawlConfig(max_depth=11)

    def test_zero_delay_allowed(self) -> None:
        config = CrawlConfig(delay_between_requests_ms=0)
        assert config.delay_between_requests_ms == 0

    def test_timeout_bounds(self) -> None:
        with pytest.raises(ValidationError):
            CrawlConfig(timeout_seconds=0)
        with pytest.raises(ValidationError):
            CrawlConfig(timeout_seconds=301)


# ---------------------------------------------------------------------------
# RetentionConfig
# ---------------------------------------------------------------------------


class TestRetentionConfig:
    def test_defaults(self) -> None:
        config = RetentionConfig()
        assert config.retention_days.audit_log == 365
        assert config.retention_days.raw_html == 7
        assert config.retention_days.exports == 90

    def test_zero_means_keep_indefinitely(self) -> None:
        config = RetentionConfig(retention_days=RetentionDays(job_events=0, raw_html=0))
        assert config.retention_days.job_events == 0
        assert config.retention_days.raw_html == 0

    def test_negative_value_raises(self) -> None:
        with pytest.raises(ValidationError):
            RetentionDays(audit_log=-1)

    def test_from_dict(self) -> None:
        config = RetentionConfig.model_validate(
            {"retention_days": {"job_events": 60, "audit_log": 730}}
        )
        assert config.retention_days.job_events == 60
        assert config.retention_days.audit_log == 730
        # Others fall back to defaults
        assert config.retention_days.raw_html == 7


# ---------------------------------------------------------------------------
# ConnectorsConfig
# ---------------------------------------------------------------------------


class TestConnectorsConfig:
    def test_empty_connectors(self) -> None:
        config = ConnectorsConfig()
        assert config.connectors == {}

    def test_with_connector_data(self) -> None:
        config = ConnectorsConfig(
            connectors={
                "google_places": {"enabled": True, "max_results": 60},
                "fixture": {"enabled": True},
            }
        )
        assert "google_places" in config.connectors
        assert config.connectors["fixture"]["enabled"] is True

    def test_from_dict(self) -> None:
        config = ConnectorsConfig.model_validate(
            {"connectors": {"brave_search": {"enabled": False}}}
        )
        assert config.connectors["brave_search"]["enabled"] is False


# ---------------------------------------------------------------------------
# Loader — load_app_config
# ---------------------------------------------------------------------------


class TestLoadAppConfig:
    def test_loads_valid_file(self, tmp_path: Path) -> None:
        (tmp_path / "app.yml").write_text("base_url: http://localhost:8000\nenvironment: local\n")
        config = load_app_config(tmp_path)
        assert config.base_url == "http://localhost:8000"
        assert config.environment == "local"

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigLoadError, match="not found"):
            load_app_config(tmp_path)

    def test_yaml_syntax_error_raises(self, tmp_path: Path) -> None:
        (tmp_path / "app.yml").write_text("bad: [unclosed\n")
        with pytest.raises(ConfigLoadError, match="syntax"):
            load_app_config(tmp_path)

    def test_validation_error_raises(self, tmp_path: Path) -> None:
        # Invalid environment value — missing base_url too
        (tmp_path / "app.yml").write_text("environment: invalid_env\n")
        with pytest.raises(ConfigLoadError):
            load_app_config(tmp_path)

    def test_empty_file_uses_defaults_where_possible(self, tmp_path: Path) -> None:
        # base_url is required so empty file should fail
        (tmp_path / "app.yml").write_text("")
        with pytest.raises(ConfigLoadError):
            load_app_config(tmp_path)


# ---------------------------------------------------------------------------
# Loader — load_crawl_config
# ---------------------------------------------------------------------------


class TestLoadCrawlConfig:
    def test_loads_valid_file(self, tmp_path: Path) -> None:
        (tmp_path / "crawl.yml").write_text("user_agent: TestBot/1.0\nmax_pages_per_job: 100\n")
        config = load_crawl_config(tmp_path)
        assert config.user_agent == "TestBot/1.0"
        assert config.max_pages_per_job == 100

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigLoadError, match="not found"):
            load_crawl_config(tmp_path)

    def test_empty_file_returns_defaults(self, tmp_path: Path) -> None:
        (tmp_path / "crawl.yml").write_text("")
        config = load_crawl_config(tmp_path)
        assert config.max_pages_per_job == 500


# ---------------------------------------------------------------------------
# Loader — load_retention_config
# ---------------------------------------------------------------------------


class TestLoadRetentionConfig:
    def test_loads_valid_file(self, tmp_path: Path) -> None:
        (tmp_path / "retention.yml").write_text(
            "retention_days:\n  audit_log: 730\n  exports: 60\n"
        )
        config = load_retention_config(tmp_path)
        assert config.retention_days.audit_log == 730
        assert config.retention_days.exports == 60

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigLoadError, match="not found"):
            load_retention_config(tmp_path)


# ---------------------------------------------------------------------------
# Loader — load_all_configs
# ---------------------------------------------------------------------------


def _write_minimal_configs(d: Path) -> None:
    """Write the minimum valid YAML for all four config files into directory d."""
    (d / "app.yml").write_text("base_url: http://localhost:8000\n")
    (d / "connectors.yml").write_text("connectors: {}\n")
    (d / "crawl.yml").write_text("")
    (d / "retention.yml").write_text("")


class TestLoadAllConfigs:
    def test_loads_all_four_configs(self, tmp_path: Path) -> None:
        _write_minimal_configs(tmp_path)
        configs = load_all_configs(tmp_path)
        assert configs.app.base_url == "http://localhost:8000"
        assert configs.crawl.max_pages_per_job == 500
        assert configs.retention.retention_days.audit_log == 365
        assert configs.connectors.connectors == {}

    def test_fails_fast_if_any_file_missing(self, tmp_path: Path) -> None:
        # Only write three of the four files
        (tmp_path / "app.yml").write_text("base_url: http://localhost\n")
        (tmp_path / "connectors.yml").write_text("connectors: {}\n")
        (tmp_path / "crawl.yml").write_text("")
        # retention.yml intentionally omitted
        with pytest.raises(ConfigLoadError, match="not found"):
            load_all_configs(tmp_path)
