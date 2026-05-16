# ABOUTME: Loads skill Markdown files from config/ai/skills/ into a single string.
# ABOUTME: Only files enabled in AIConfig.skills are included; missing files are skipped.
from __future__ import annotations

from pathlib import Path

import structlog

from app.ai.config import AIConfig

logger = structlog.get_logger(__name__)

_SKILL_FILES: dict[str, str] = {
    "criteria_creation": "criteria_creation.md",
    "criteria_update": "criteria_creation.md",
    "criteria_validation": "criteria_creation.md",
}


def load_skills(config_dir: Path, ai_config: AIConfig) -> str:
    """Return concatenated content of all enabled skill files."""
    skills_dir = config_dir / "ai" / "skills"
    seen: set[str] = set()
    parts: list[str] = []

    skills_cfg = ai_config.skills
    for skill_name, filename in _SKILL_FILES.items():
        if not getattr(skills_cfg, skill_name, False):
            continue
        if filename in seen:
            continue
        seen.add(filename)
        path = skills_dir / filename
        if not path.exists():
            logger.warning("ai.skills.file_not_found", path=str(path))
            continue
        try:
            parts.append(path.read_text(encoding="utf-8"))
        except OSError as exc:
            logger.warning("ai.skills.read_error", path=str(path), error=str(exc))

    return "\n\n".join(parts)
