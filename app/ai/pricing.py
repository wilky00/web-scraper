# ABOUTME: Fetches model pricing data from LiteLLM's proxy or public pricing database.
# ABOUTME: Results are cached in Redis for 24h; errors soft-fail (returns empty list).
from __future__ import annotations

import json
from typing import Any

import httpx
import structlog

from app.ai.config import AIConfig

logger = structlog.get_logger(__name__)

_LITELLM_PRICING_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
)
_CACHE_KEY_GITHUB = "litellm:model_pricing:github"
_CACHE_KEY_PROXY = "litellm:model_pricing:proxy"
_CACHE_TTL = 86400  # 24 hours


def _litellm_key(provider: str, model: str) -> list[str]:
    """Return candidate LiteLLM pricing-dict keys to try for a given provider+model."""
    if provider == "openrouter":
        return [f"openrouter/{model}", model]
    if provider in ("anthropic", "openai"):
        return [f"{provider}/{model}", model]
    # litellm proxy or unknown — bare model name is most likely
    return [model, f"{provider}/{model}"]


async def _from_proxy(
    redis: Any,
    ai_config: AIConfig,
    api_key: str,
) -> list[dict[str, Any]] | None:
    """Fetch pricing from a running LiteLLM proxy via its /model/info endpoint.

    Returns None on any failure so the caller can fall back to GitHub.
    """
    cache_key = f"{_CACHE_KEY_PROXY}:{ai_config.base_url}"
    try:
        cached = await redis.get(cache_key)
        if cached:
            data: list[dict[str, Any]] = json.loads(cached)
        else:
            # /model/info lives at the root, not under /v1
            root = ai_config.base_url.rstrip("/").removesuffix("/v1")
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{root}/model/info",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                resp.raise_for_status()
                data = resp.json().get("data", [])
            await redis.set(cache_key, json.dumps(data), ex=_CACHE_TTL)
    except Exception as exc:
        logger.warning("ai.pricing.proxy_failed", error=str(exc))
        return None

    model_info = {entry["model_name"]: entry.get("model_info", {}) for entry in data}
    models = ai_config.models if ai_config.models else [ai_config.model]
    rows: list[dict[str, Any]] = []
    for model in models:
        info = model_info.get(model, {})
        input_cost = info.get("input_cost_per_token")
        output_cost = info.get("output_cost_per_token")
        context = info.get("max_input_tokens") or info.get("max_tokens")
        rows.append(
            {
                "model": model,
                "input_per_1m": (
                    round(input_cost * 1_000_000, 4) if input_cost is not None else None
                ),
                "output_per_1m": (
                    round(output_cost * 1_000_000, 4) if output_cost is not None else None
                ),
                "context_window": context,
            }
        )
    return rows


async def fetch_model_pricing(
    redis: Any,
    ai_config: AIConfig,
    api_key: str = "",
) -> list[dict[str, Any]]:
    """Return pricing rows for all configured AI models.

    When provider is 'litellm', queries the proxy's /model/info endpoint directly
    (most accurate — reflects the proxy's actual backend routing).
    All other providers fall back to LiteLLM's public pricing database on GitHub.

    Each row: {model, input_per_1m, output_per_1m, context_window} — fields are
    None when pricing is not found.
    """
    if ai_config.provider == "litellm" and api_key:
        result = await _from_proxy(redis, ai_config, api_key)
        if result is not None:
            return result
        # Proxy unreachable — fall through to GitHub pricing

    all_pricing: dict[str, Any] = {}
    try:
        cached = await redis.get(_CACHE_KEY_GITHUB)
        if cached:
            all_pricing = json.loads(cached)
        else:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(_LITELLM_PRICING_URL)
                resp.raise_for_status()
                all_pricing = resp.json()
            await redis.set(_CACHE_KEY_GITHUB, json.dumps(all_pricing), ex=_CACHE_TTL)
    except Exception as exc:
        logger.warning("ai.pricing.github_fetch_failed", error=str(exc))
        return []

    models = ai_config.models if ai_config.models else [ai_config.model]
    rows: list[dict[str, Any]] = []
    for model in models:
        pricing: dict[str, Any] | None = None
        for key in _litellm_key(ai_config.provider, model):
            pricing = all_pricing.get(key)
            if pricing:
                break

        input_cost = pricing.get("input_cost_per_token") if pricing else None
        output_cost = pricing.get("output_cost_per_token") if pricing else None
        context = (
            (pricing.get("max_input_tokens") or pricing.get("max_tokens")) if pricing else None
        )
        rows.append(
            {
                "model": model,
                "input_per_1m": (
                    round(input_cost * 1_000_000, 4) if input_cost is not None else None
                ),
                "output_per_1m": (
                    round(output_cost * 1_000_000, 4) if output_cost is not None else None
                ),
                "context_window": context,
            }
        )
    return rows
