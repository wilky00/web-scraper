# ABOUTME: Pure helpers for building AI chat messages and extracting YAML from responses.
# ABOUTME: No I/O — build_messages() and extract_yaml_block() are fully unit-testable.
from __future__ import annotations

import re

_MAX_HISTORY_TURNS = 10
_MAX_MESSAGE_LENGTH = 4096

_SYSTEM_PROMPT_TEMPLATE = """\
You are an AI assistant for a configurable web scraper. Your job is to help \
operators create and edit YAML-based scraping criteria.

## Criteria YAML Reference
{skill_content}

## Current Criteria Being Edited
{current_yaml}

## Projects
The app organizes work into Projects. Criteria templates can be scoped to a \
project by adding `metadata.project: <project-name>` (optional). Templates with \
no project tag are available to all projects (treated as Default). When creating \
a job, only project-matching templates and Default templates appear in the \
template browser.

## Web Crawling
Scrapy uses Playwright (headless Chromium) to fetch website pages. Set \
`crawl.enabled: true` and configure `max_depth` and `max_pages_per_domain`. \
Screenshots are automatically captured for each crawled page and stored in S3. \
The `USER_AGENT` and request delays are set in `config/crawl.yml`.

## Instructions
- When you generate or modify criteria YAML, wrap it in a ```yaml code block.
- Include only one YAML block per response.
- If asked to modify existing criteria, output the complete updated YAML.
- Be concise — explain your key choices briefly, then show the YAML.
- Never include secrets, API keys, or credentials in YAML.
"""

_YAML_BLOCK_RE = re.compile(r"```yaml\s*\n(.*?)```", re.DOTALL)


def build_messages(
    user_message: str,
    current_yaml: str | None,
    history: list[dict[str, str]],
    skill_content: str,
) -> list[dict[str, str]]:
    """Build the messages list for an OpenAI-compat chat completion request."""
    yaml_context = (
        current_yaml.strip()
        if current_yaml and current_yaml.strip()
        else ("No criteria loaded yet.")
    )

    system_content = _SYSTEM_PROMPT_TEMPLATE.format(
        skill_content=skill_content or "(no skill content loaded)",
        current_yaml=yaml_context,
    )

    messages: list[dict[str, str]] = [{"role": "system", "content": system_content}]

    # Include last N turns of history
    trimmed = history[-_MAX_HISTORY_TURNS:]
    for turn in trimmed:
        role = turn.get("role", "")
        content = turn.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})

    safe_message = user_message[:_MAX_MESSAGE_LENGTH].replace("\x00", "")
    messages.append({"role": "user", "content": safe_message})
    return messages


def extract_yaml_block(text: str) -> str | None:
    """Extract the first ```yaml ... ``` block from text. Returns None if absent."""
    match = _YAML_BLOCK_RE.search(text)
    if match:
        content = match.group(1).strip()
        return content if content else None
    return None
