# ABOUTME: Fetches model pricing data from LiteLLM's public pricing database.
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
_CACHE_KEY = "litellm:model_pricing"
_CACHE_TTL = 86400  # 24 hours


def _litellm_key(provider: str, model: str) -> list[str]:
    """Return candidate LiteLLM pricing-dict keys to try for a given provider+model."""
    if provider in ("anthropic", "openai"):
        return [f"{provider}/{model}", model]
    if provider == "openrouter":
        return [f"openrouter/{model}", model]
    # litellm proxy or unknown — try bare model name and provider-prefixed
    return [f"{provider}/{model}", model]


async def fetch_model_pricing(
    redis: Any,
    ai_config: AIConfig,
) -> list[dict[str, Any]]:
    """Return pricing rows for all configured AI models.

    Each row: {model, input_per_1m, output_per_1m, context_window} or None fields
    when the model isn't found in LiteLLM's pricing database.
    """
    # Pull from cache or fetch fresh
    all_pricing: dict[str, Any] = {}
    try:
        cached = await redis.get(_CACHE_KEY)
        if cached:
            all_pricing = json.loads(cached)
        else:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(_LITELLM_PRICING_URL)
                resp.raise_for_status()
                all_pricing = resp.json()
            await redis.set(_CACHE_KEY, json.dumps(all_pricing), ex=_CACHE_TTL)
    except Exception as exc:
        logger.warning("ai.pricing.fetch_failed", error=str(exc))
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
