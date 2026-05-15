# ABOUTME: Pydantic Settings model — reads secrets from environment variables only.
# ABOUTME: Non-secret runtime config lives in config/*.yml; this handles .env secrets.
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Application
    environment: str = "local"
    secret_key: str
    api_token_secret: str

    # Operator seed (first-boot only)
    seed_operator_email: str = "admin@example.com"
    seed_operator_password: str = ""

    # Storage (S3 / MinIO)
    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_bucket_name: str = "web-scraper"

    # Connectors (Phase 3)
    google_places_api_key: str = ""
    brave_api_key: str = ""

    # AI Assist (Phase 9)
    ai_api_key: str = ""

    # Authentik SSO (Phase 10)
    authentik_client_id: str = ""
    authentik_client_secret: str = ""
    authentik_base_url: str = ""

    # Config directory (non-secret YAML files); override in tests via CONFIG_DIR env var
    config_dir: Path = Path("config")
