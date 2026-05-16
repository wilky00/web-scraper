# ABOUTME: Unit tests for AIConfig Pydantic model and load_ai_config() soft-fail loader.
# ABOUTME: No external services — all tests use tmp_path fixtures.
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from app.ai.config import AIConfig, AISkillsConfig, load_ai_config


def _write_ai_yaml(tmp_path: Path, data: dict) -> Path:
    ai_dir = tmp_path / "ai"
    ai_dir.mkdir(parents=True, exist_ok=True)
    path = ai_dir / "ai_base.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    return tmp_path


class TestAIConfig:
    def test_defaults(self) -> None:
        cfg = AIConfig()
        assert cfg.provider == "openrouter"
        assert cfg.base_url == "https://openrouter.ai/api/v1"
        assert cfg.model == "anthropic/claude-3-5-sonnet"
        assert cfg.max_tokens == 4096
        assert cfg.temperature == 0.3
        assert cfg.skills.criteria_creation is True

    def test_custom_values(self) -> None:
        cfg = AIConfig(provider="anthropic", model="claude-opus-4-7", max_tokens=8192)
        assert cfg.provider == "anthropic"
        assert cfg.model == "claude-opus-4-7"
        assert cfg.max_tokens == 8192

    def test_max_tokens_bounds(self) -> None:
        with pytest.raises(ValidationError):
            AIConfig(max_tokens=100)  # below min 256
        with pytest.raises(ValidationError):
            AIConfig(max_tokens=999999)  # above max 32000

    def test_temperature_bounds(self) -> None:
        with pytest.raises(ValidationError):
            AIConfig(temperature=-0.1)
        with pytest.raises(ValidationError):
            AIConfig(temperature=2.1)

    def test_skills_config_defaults(self) -> None:
        skills = AISkillsConfig()
        assert skills.criteria_creation is True
        assert skills.criteria_update is True
        assert skills.criteria_validation is True

    def test_skills_config_partial_disable(self) -> None:
        skills = AISkillsConfig(criteria_creation=False)
        assert skills.criteria_creation is False
        assert skills.criteria_update is True


class TestLoadAIConfig:
    def test_returns_none_when_file_missing(self, tmp_path: Path) -> None:
        result = load_ai_config(tmp_path)
        assert result is None

    def test_loads_valid_config(self, tmp_path: Path) -> None:
        _write_ai_yaml(tmp_path, {"provider": "anthropic", "model": "claude-opus-4-7"})
        result = load_ai_config(tmp_path)
        assert result is not None
        assert result.provider == "anthropic"
        assert result.model == "claude-opus-4-7"

    def test_returns_defaults_for_empty_yaml(self, tmp_path: Path) -> None:
        _write_ai_yaml(tmp_path, {})
        result = load_ai_config(tmp_path)
        assert result is not None
        assert result.provider == "openrouter"

    def test_returns_none_on_invalid_yaml(self, tmp_path: Path) -> None:
        ai_dir = tmp_path / "ai"
        ai_dir.mkdir(parents=True)
        (ai_dir / "ai_base.yaml").write_text("invalid: yaml: :\n  bad:", encoding="utf-8")
        result = load_ai_config(tmp_path)
        assert result is None

    def test_returns_none_on_validation_error(self, tmp_path: Path) -> None:
        _write_ai_yaml(tmp_path, {"max_tokens": 10})  # below min 256
        result = load_ai_config(tmp_path)
        assert result is None

    def test_returns_none_when_yaml_is_not_mapping(self, tmp_path: Path) -> None:
        ai_dir = tmp_path / "ai"
        ai_dir.mkdir(parents=True)
        (ai_dir / "ai_base.yaml").write_text("- just a list\n", encoding="utf-8")
        result = load_ai_config(tmp_path)
        assert result is None

    def test_skills_loaded_from_yaml(self, tmp_path: Path) -> None:
        _write_ai_yaml(
            tmp_path,
            {"skills": {"criteria_creation": False, "criteria_update": True}},
        )
        result = load_ai_config(tmp_path)
        assert result is not None
        assert result.skills.criteria_creation is False
        assert result.skills.criteria_update is True
