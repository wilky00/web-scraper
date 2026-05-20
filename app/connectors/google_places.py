# ABOUTME: Google Places API v1 connector — Text Search with pagination and tenacity retry.
# ABOUTME: API key is read from GOOGLE_PLACES_API_KEY env var; never from config or logs.
from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from typing import Any

import httpx
import structlog
from pydantic import BaseModel, ConfigDict, Field
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential

from app.config.models import RateLimitConfig, RetryConfig
from app.connectors.base import ConnectorBase, ConnectorResult

logger = structlog.get_logger()

_PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

_FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.websiteUri",
        "places.nationalPhoneNumber",
        "places.types",
        "places.rating",
        "places.userRatingCount",
        "places.businessStatus",
        "nextPageToken",
    ]
)

# Places API v1 hard limit per request
_MAX_PER_PAGE = 20


class GooglePlacesConnectorConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    max_results: int = Field(60, ge=1, le=200)
    rate_limit: RateLimitConfig = Field(
        default_factory=lambda: RateLimitConfig(requests_per_minute=30)
    )
    retry: RetryConfig = Field(default_factory=RetryConfig)
    options: dict[str, Any] = {}


class GooglePlacesConnector(ConnectorBase):
    """Discovers businesses via Google Places API v1 Text Search.

    Reads GOOGLE_PLACES_API_KEY from the environment at discover-time so the
    connector can be registered without requiring the key at startup.
    """

    connector_type = "google_places"

    def __init__(
        self,
        config: dict[str, Any],
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._config = GooglePlacesConnectorConfig.model_validate(config)
        # Injected in tests; None means create-and-close per discover() call.
        self._http_client = http_client

    async def discover(self, job_config: dict[str, Any]) -> AsyncIterator[ConnectorResult]:
        query, location, max_results = self._resolve_query_params(job_config)
        if not query:
            logger.warning("google_places.missing_query")
            return

        if location:
            query = f"{query} {location}"

        api_key = os.environ.get("GOOGLE_PLACES_API_KEY", "")
        if not api_key:
            raise RuntimeError("GOOGLE_PLACES_API_KEY environment variable is not set")
        # Minimum inter-page delay to stay within rate limit
        page_delay = 60.0 / self._config.rate_limit.requests_per_minute

        owns_client = self._http_client is None
        client = self._http_client or httpx.AsyncClient(timeout=60.0)

        try:
            yielded = 0
            next_page_token: str | None = None
            first_page = True

            while yielded < max_results:
                if not first_page:
                    await asyncio.sleep(page_delay)
                first_page = False

                batch_size = min(_MAX_PER_PAGE, max_results - yielded)
                body: dict[str, Any] = {
                    "textQuery": query,
                    "maxResultCount": batch_size,
                    "languageCode": self._config.options.get("language", "en"),
                    "regionCode": self._config.options.get("region", "us"),
                }
                if next_page_token:
                    body["pageToken"] = next_page_token

                data = await self._search_page(client, api_key, body)

                places: list[dict[str, Any]] = data.get("places", [])
                logger.info(
                    "google_places.page_fetched",
                    query=query,
                    count=len(places),
                    yielded_so_far=yielded,
                )

                for place in places:
                    if yielded >= max_results:
                        break
                    yield ConnectorResult(
                        connector_type=self.connector_type,
                        raw_data=place,
                    )
                    yielded += 1

                next_page_token = data.get("nextPageToken")
                if not next_page_token or not places:
                    break

        finally:
            if owns_client:
                await client.aclose()

    def extract_fields(self, raw_data: dict[str, Any]) -> dict[str, str | None]:
        display_name = raw_data.get("displayName") or {}
        name = display_name.get("text") if isinstance(display_name, dict) else None
        return {
            "name": name or None,
            "website": raw_data.get("websiteUri") or None,
            "phone": raw_data.get("nationalPhoneNumber") or None,
            "address": raw_data.get("formattedAddress") or None,
            "email": None,  # Places API does not expose email
            "external_id": raw_data.get("id") or None,
        }

    def extract_metrics(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        metrics: dict[str, Any] = {}
        if "rating" in raw_data:
            metrics["source.rating"] = raw_data["rating"]
        if "userRatingCount" in raw_data:
            metrics["source.review_count"] = raw_data["userRatingCount"]
        if "businessStatus" in raw_data:
            metrics["source.business_status"] = raw_data["businessStatus"]
        if "types" in raw_data:
            metrics["source.types"] = raw_data["types"]
        if "id" in raw_data:
            metrics["source.place_id"] = raw_data["id"]
        return metrics

    def _resolve_query_params(self, job_config: dict[str, Any]) -> tuple[str, str | None, int]:
        """Extract query, location, and max_results from job_config.

        Supports both a flat top-level format (legacy) and the nested
        criteria.source.query_fields format used by the criteria YAML system.
        """
        # Flat top-level keys take precedence (used in unit tests / direct calls)
        flat_query = str(job_config.get("query", "")).strip()
        if flat_query:
            location = job_config.get("location")
            max_results = int(job_config.get("max_results", self._config.max_results))
            return flat_query, location, max_results

        # Build from criteria.source.query_fields
        source = (job_config.get("criteria") or {}).get("source") or {}
        query_fields: list[dict[str, str]] = source.get("query_fields") or []

        query_terms: list[str] = []
        location: str | None = None
        for qf in query_fields:
            field = str(qf.get("field", "")).lower()
            value = str(qf.get("value", "")).strip()
            if not value:
                continue
            if field == "location":
                location = value
            elif field in ("type", "keyword", "query"):
                query_terms.append(value)

        query = " ".join(query_terms)
        max_results = int(source.get("max_results", self._config.max_results))
        return query, location, max_results

    async def _search_page(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        retry_statuses = set(self._config.retry.retry_on_status)

        def _is_retryable(exc: BaseException) -> bool:
            return (
                isinstance(exc, httpx.HTTPStatusError)
                and exc.response.status_code in retry_statuses
            )

        result: dict[str, Any] = {}
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self._config.retry.max_attempts),
            wait=wait_exponential(
                multiplier=self._config.retry.backoff_factor,
                min=1,
                max=30,
            ),
            retry=retry_if_exception(_is_retryable),
            reraise=True,
        ):
            with attempt:
                response = await client.post(
                    _PLACES_SEARCH_URL,
                    json=body,
                    headers={
                        "X-Goog-Api-Key": api_key,
                        "X-Goog-FieldMask": _FIELD_MASK,
                        "Content-Type": "application/json",
                    },
                )
                response.raise_for_status()
                result = response.json()
        return result
