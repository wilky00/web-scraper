# ABOUTME: Pydantic v2 models for the four non-criteria YAML config files.
# ABOUTME: app.yml, connectors.yml, crawl.yml, retention.yml — all non-secret runtime config.
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class FeaturesConfig(BaseModel):
    ai_assist: bool = False
    brave_connector: bool = False
    api_docs: bool = True
    sso_enabled: bool = False


class AppConfig(BaseModel):
    app_name: str = "Web Scraper"
    base_url: str
    environment: Literal["local", "staging", "production"] = "local"
    default_page_size: int = Field(25, ge=1, le=1000)
    max_page_size: int = Field(100, ge=1, le=1000)
    roles: list[str] = ["operator"]
    features: FeaturesConfig = FeaturesConfig()


class RateLimitConfig(BaseModel):
    requests_per_minute: int = Field(ge=1)


class RetryConfig(BaseModel):
    max_attempts: int = Field(3, ge=1, le=10)
    backoff_factor: float = Field(2.0, ge=0.0)
    retry_on_status: list[int] = [429, 500, 502, 503, 504]


class ConnectorsConfig(BaseModel):
    # Keyed by connector name; detailed per-connector validation happens in Phase 3.
    connectors: dict[str, Any] = {}


class CrawlConfig(BaseModel):
    user_agent: str = "WebScraper/1.0 (internal; not-indexing)"
    max_pages_per_job: int = Field(500, ge=1)
    max_pages_per_domain: int = Field(50, ge=1)
    max_depth: int = Field(3, ge=0, le=10)
    timeout_seconds: int = Field(30, ge=1, le=300)
    delay_between_requests_ms: int = Field(1000, ge=0)
    blocked_path_patterns: list[str] = []
    blocked_content_types: list[str] = []


class RetentionDays(BaseModel):
    job_events: int = Field(90, ge=0)
    raw_responses: int = Field(30, ge=0)
    raw_html: int = Field(7, ge=0)
    screenshots: int = Field(7, ge=0)
    artifacts: int = Field(30, ge=0)
    exports: int = Field(90, ge=0)
    # Keep long for compliance; 0 means keep indefinitely
    audit_log: int = Field(365, ge=0)


class RetentionConfig(BaseModel):
    retention_days: RetentionDays = RetentionDays()
