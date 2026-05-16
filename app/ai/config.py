# ABOUTME: Pydantic model for config/ai/ai_base.yaml and soft-fail loader.
# ABOUTME: load_ai_config() returns None (never raises) when the file is absent or invalid.
from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
import yaml
from pydantic import BaseModel, Field, ValidationError

logger = structlog.get_logger(__name__)

_AI_CONFIG_PATH = "ai/ai_base.yaml"


class AISkillsConfig(BaseModel):
    criteria_creation: bool = True
    criteria_update: bool = True
    criteria_validation: bool = True


class AIConfig(BaseModel):
    provider: str = "openrouter"
    base_url: str = "https://openrouter.ai/api/v1"
    model: str = "anthropic/claude-3-5-sonnet"
    max_tokens: int = Field(4096, ge=256, le=32000)
    temperature: float = Field(0.3, ge=0.0, le=2.0)
    skills: AISkillsConfig = Field(default_factory=AISkillsConfig)


def load_ai_config(config_dir: Path) -> AIConfig | None:
    """Load config/ai/ai_base.yaml. Returns None on any error — AI Assist is optional."""
    path = config_dir / _AI_CONFIG_PATH
    if not path.exists():
        logger.info("ai.config.not_found", path=str(path))
        return None

    try:
        with path.open() as fh:
            data: Any = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        logger.warning("ai.config.yaml_error", path=str(path), error=str(exc))
        return None

    if not isinstance(data, dict):
        logger.warning("ai.config.invalid_type", path=str(path))
        return None

    try:
        return AIConfig.model_validate(data)
    except ValidationError as exc:
        logger.warning("ai.config.validation_error", path=str(path), error=str(exc))
        return None
