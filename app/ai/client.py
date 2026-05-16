# ABOUTME: Async httpx client for OpenAI-compatible /v1/chat/completions endpoint.
# ABOUTME: Raises AIClientError on HTTP errors; never logs the API key.
from __future__ import annotations

import httpx
import structlog

from app.ai.config import AIConfig

logger = structlog.get_logger(__name__)

_REQUEST_TIMEOUT = 60.0


class AIClientError(RuntimeError):
    """Raised when the AI API returns an error or is unreachable."""


async def chat_complete(
    messages: list[dict[str, str]],
    ai_config: AIConfig,
    api_key: str,
) -> str:
    """Call the OpenAI-compatible chat completions endpoint and return the reply text."""
    url = ai_config.base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": ai_config.model,
        "messages": messages,
        "max_tokens": ai_config.max_tokens,
        "temperature": ai_config.temperature,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            response = await client.post(url, json=payload, headers=headers)
    except httpx.TimeoutException as exc:
        raise AIClientError("AI API request timed out") from exc
    except httpx.RequestError as exc:
        raise AIClientError(f"AI API request failed: {exc}") from exc

    if response.status_code != 200:
        logger.warning(
            "ai.client.http_error",
            status=response.status_code,
            model=ai_config.model,
        )
        raise AIClientError(f"AI API returned HTTP {response.status_code}")

    try:
        data = response.json()
        content: str = data["choices"][0]["message"]["content"]
        return content
    except (KeyError, IndexError, ValueError) as exc:
        raise AIClientError(f"Unexpected AI API response format: {exc}") from exc
