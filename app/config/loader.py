# ABOUTME: YAML config file loaders for all four runtime config files.
# ABOUTME: All loaders raise ConfigLoadError on failure — intended as a hard boot-time fail.
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from app.config.models import AppConfig, ConnectorsConfig, CrawlConfig, RetentionConfig


class ConfigLoadError(RuntimeError):
    """Raised when a required config file is missing, unparseable, or fails validation."""


def _load_yaml_file(path: Path) -> dict[str, Any]:
    """Read and parse a single YAML file into a dict."""
    if not path.exists():
        raise ConfigLoadError(f"Required config file not found: {path}")
    try:
        with path.open() as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise ConfigLoadError(f"YAML syntax error in {path}: {exc}") from exc
    return data or {}


def _format_validation_errors(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"])
        parts.append(f"{loc}: {err['msg']}" if loc else err["msg"])
    return "; ".join(parts)


def load_app_config(config_dir: Path) -> AppConfig:
    data = _load_yaml_file(config_dir / "app.yml")
    try:
        return AppConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigLoadError(f"Invalid app.yml — {_format_validation_errors(exc)}") from exc


def load_connectors_config(config_dir: Path) -> ConnectorsConfig:
    data = _load_yaml_file(config_dir / "connectors.yml")
    try:
        return ConnectorsConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigLoadError(f"Invalid connectors.yml — {_format_validation_errors(exc)}") from exc


def load_crawl_config(config_dir: Path) -> CrawlConfig:
    data = _load_yaml_file(config_dir / "crawl.yml")
    try:
        return CrawlConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigLoadError(f"Invalid crawl.yml — {_format_validation_errors(exc)}") from exc


def load_retention_config(config_dir: Path) -> RetentionConfig:
    data = _load_yaml_file(config_dir / "retention.yml")
    try:
        return RetentionConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigLoadError(f"Invalid retention.yml — {_format_validation_errors(exc)}") from exc


@dataclass
class AppConfigs:
    """Container for all loaded runtime configs, stored on app.state.config."""

    app: AppConfig
    connectors: ConnectorsConfig
    crawl: CrawlConfig
    retention: RetentionConfig


def load_all_configs(config_dir: Path) -> AppConfigs:
    """Load and validate all four runtime config files. Raises ConfigLoadError on any failure."""
    return AppConfigs(
        app=load_app_config(config_dir),
        connectors=load_connectors_config(config_dir),
        crawl=load_crawl_config(config_dir),
        retention=load_retention_config(config_dir),
    )
