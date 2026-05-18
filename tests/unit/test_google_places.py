# ABOUTME: Unit tests for GooglePlacesConnector and ConnectorRegistry google_places integration.
# ABOUTME: All HTTP calls are mocked via injected httpx.AsyncClient — no live API required.
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.connectors.base import ConnectorResult
from app.connectors.google_places import GooglePlacesConnector, GooglePlacesConnectorConfig
from app.connectors.registry import ConnectorRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_CONFIG: dict[str, Any] = {
    "enabled": True,
    "max_results": 20,
    "rate_limit": {"requests_per_minute": 60},
    "retry": {"max_attempts": 2, "backoff_factor": 0.01, "retry_on_status": [429, 500]},
    "options": {"language": "en", "region": "us"},
}

_SAMPLE_PLACE: dict[str, Any] = {
    "id": "ChIJN1t_tDeuEmsRUsoyG83frY4",
    "displayName": {"text": "Acme Roofing Co.", "languageCode": "en"},
    "formattedAddress": "123 Main St, Austin, TX 78701",
    "websiteUri": "https://acmeroofing.example.com",
    "nationalPhoneNumber": "+1 512-555-0101",
    "types": ["roofing_contractor", "establishment"],
    "rating": 4.7,
    "userRatingCount": 214,
    "businessStatus": "OPERATIONAL",
}


def _make_mock_client(responses: list[dict[str, Any]]) -> AsyncMock:
    """Return a mock AsyncClient whose .post() returns each response in sequence."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    call_index = 0

    async def _post(*args: Any, **kwargs: Any) -> MagicMock:
        nonlocal call_index
        data = responses[call_index % len(responses)]
        call_index += 1

        mock_response = MagicMock()
        mock_response.status_code = data.get("_status", 200)
        mock_response.json.return_value = {k: v for k, v in data.items() if not k.startswith("_")}

        if mock_response.status_code >= 400:
            exc = httpx.HTTPStatusError(
                f"HTTP {mock_response.status_code}",
                request=MagicMock(),
                response=mock_response,
            )
            mock_response.raise_for_status.side_effect = exc
        else:
            mock_response.raise_for_status.return_value = None

        return mock_response

    mock_client.post = _post  # type: ignore[method-assign]
    return mock_client


async def _collect(
    connector: GooglePlacesConnector, job_config: dict[str, Any]
) -> list[ConnectorResult]:
    results = []
    async for result in connector.discover(job_config):
        results.append(result)
    return results


# ---------------------------------------------------------------------------
# GooglePlacesConnectorConfig
# ---------------------------------------------------------------------------


class TestGooglePlacesConnectorConfig:
    def test_defaults_applied(self) -> None:
        cfg = GooglePlacesConnectorConfig.model_validate({"enabled": True})
        assert cfg.max_results == 60
        assert cfg.rate_limit.requests_per_minute == 30
        assert cfg.retry.max_attempts == 3

    def test_custom_values(self) -> None:
        cfg = GooglePlacesConnectorConfig.model_validate(_BASE_CONFIG)
        assert cfg.max_results == 20
        assert cfg.rate_limit.requests_per_minute == 60
        assert cfg.retry.backoff_factor == pytest.approx(0.01)

    def test_extra_fields_ignored(self) -> None:
        cfg = GooglePlacesConnectorConfig.model_validate(
            {**_BASE_CONFIG, "fixture_dir": "should/be/ignored"}
        )
        assert cfg.max_results == 20

    def test_max_results_bounds(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            GooglePlacesConnectorConfig.model_validate({**_BASE_CONFIG, "max_results": 0})
        with pytest.raises(ValidationError):
            GooglePlacesConnectorConfig.model_validate({**_BASE_CONFIG, "max_results": 201})


# ---------------------------------------------------------------------------
# GooglePlacesConnector — discover
# ---------------------------------------------------------------------------


class TestGooglePlacesConnectorDiscover:
    @pytest.mark.asyncio
    async def test_yields_single_page_results(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
        client = _make_mock_client([{"places": [_SAMPLE_PLACE]}])
        connector = GooglePlacesConnector(_BASE_CONFIG, http_client=client)
        results = await _collect(connector, {"query": "roofing contractor"})

        assert len(results) == 1
        assert results[0].connector_type == "google_places"
        assert results[0].raw_data["id"] == _SAMPLE_PLACE["id"]

    @pytest.mark.asyncio
    async def test_raw_data_matches_places_api_shape(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
        client = _make_mock_client([{"places": [_SAMPLE_PLACE]}])
        connector = GooglePlacesConnector(_BASE_CONFIG, http_client=client)
        results = await _collect(connector, {"query": "roofers"})

        assert results[0].raw_data["displayName"]["text"] == "Acme Roofing Co."
        assert results[0].raw_data["rating"] == pytest.approx(4.7)

    @pytest.mark.asyncio
    async def test_empty_places_list_yields_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
        client = _make_mock_client([{"places": []}])
        connector = GooglePlacesConnector(_BASE_CONFIG, http_client=client)
        results = await _collect(connector, {"query": "roofers"})

        assert results == []

    @pytest.mark.asyncio
    async def test_missing_places_key_yields_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
        client = _make_mock_client([{}])
        connector = GooglePlacesConnector(_BASE_CONFIG, http_client=client)
        results = await _collect(connector, {"query": "roofers"})

        assert results == []

    @pytest.mark.asyncio
    async def test_missing_query_yields_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
        client = _make_mock_client([{"places": [_SAMPLE_PLACE]}])
        connector = GooglePlacesConnector(_BASE_CONFIG, http_client=client)
        results = await _collect(connector, {})

        assert results == []

    @pytest.mark.asyncio
    async def test_empty_query_string_yields_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
        client = _make_mock_client([{"places": [_SAMPLE_PLACE]}])
        connector = GooglePlacesConnector(_BASE_CONFIG, http_client=client)
        results = await _collect(connector, {"query": "   "})

        assert results == []

    @pytest.mark.asyncio
    async def test_missing_api_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
        client = _make_mock_client([{"places": [_SAMPLE_PLACE]}])
        connector = GooglePlacesConnector(_BASE_CONFIG, http_client=client)

        with pytest.raises(RuntimeError, match="GOOGLE_PLACES_API_KEY"):
            await _collect(connector, {"query": "roofers"})

    @pytest.mark.asyncio
    async def test_location_appended_to_query(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
        captured_bodies: list[dict[str, Any]] = []

        mock_client = AsyncMock(spec=httpx.AsyncClient)

        async def _post(*args: Any, **kwargs: Any) -> MagicMock:
            captured_bodies.append(kwargs.get("json", {}))
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"places": []}
            mock_response.raise_for_status.return_value = None
            return mock_response

        mock_client.post = _post  # type: ignore[method-assign]
        connector = GooglePlacesConnector(_BASE_CONFIG, http_client=mock_client)
        await _collect(connector, {"query": "roofers", "location": "Austin TX"})

        assert captured_bodies[0]["textQuery"] == "roofers Austin TX"

    @pytest.mark.asyncio
    async def test_job_config_max_results_overrides_config(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
        # Config has max_results=20 but job_config overrides to 1
        two_places = [_SAMPLE_PLACE, {**_SAMPLE_PLACE, "id": "second"}]
        client = _make_mock_client([{"places": two_places}])
        connector = GooglePlacesConnector(_BASE_CONFIG, http_client=client)
        results = await _collect(connector, {"query": "roofers", "max_results": 1})

        assert len(results) == 1


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


class TestGooglePlacesConnectorPagination:
    @pytest.mark.asyncio
    async def test_follows_next_page_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")

        page1 = {"places": [_SAMPLE_PLACE], "nextPageToken": "page2-token"}
        page2 = {"places": [{**_SAMPLE_PLACE, "id": "second"}]}
        client = _make_mock_client([page1, page2])

        cfg = {**_BASE_CONFIG, "max_results": 40}
        connector = GooglePlacesConnector(cfg, http_client=client)

        with patch("asyncio.sleep", new=AsyncMock()):
            results = await _collect(connector, {"query": "roofers"})

        assert len(results) == 2
        assert results[0].raw_data["id"] == _SAMPLE_PLACE["id"]
        assert results[1].raw_data["id"] == "second"

    @pytest.mark.asyncio
    async def test_stops_at_max_results(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")

        three_places = [{**_SAMPLE_PLACE, "id": f"place-{i}"} for i in range(3)]
        page1 = {"places": three_places, "nextPageToken": "page2-token"}
        page2 = {"places": [{**_SAMPLE_PLACE, "id": "place-3"}]}
        client = _make_mock_client([page1, page2])

        cfg = {**_BASE_CONFIG, "max_results": 2}
        connector = GooglePlacesConnector(cfg, http_client=client)

        with patch("asyncio.sleep", new=AsyncMock()):
            results = await _collect(connector, {"query": "roofers"})

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_stops_when_no_next_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
        # Only one page — no nextPageToken
        client = _make_mock_client([{"places": [_SAMPLE_PLACE]}])
        cfg = {**_BASE_CONFIG, "max_results": 40}
        connector = GooglePlacesConnector(cfg, http_client=client)
        results = await _collect(connector, {"query": "roofers"})

        assert len(results) == 1


# ---------------------------------------------------------------------------
# Retry
# ---------------------------------------------------------------------------


class TestGooglePlacesConnectorRetry:
    @pytest.mark.asyncio
    async def test_retries_on_429_then_succeeds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")

        responses = [
            {"_status": 429},  # first call → rate limited
            {"places": [_SAMPLE_PLACE]},  # second call → success
        ]
        client = _make_mock_client(responses)
        connector = GooglePlacesConnector(_BASE_CONFIG, http_client=client)
        results = await _collect(connector, {"query": "roofers"})

        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_non_retryable_error_propagates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
        # 403 is not in retry_on_status → should raise immediately
        client = _make_mock_client([{"_status": 403}])
        connector = GooglePlacesConnector(_BASE_CONFIG, http_client=client)

        with pytest.raises(httpx.HTTPStatusError):
            await _collect(connector, {"query": "roofers"})

    @pytest.mark.asyncio
    async def test_exhausted_retries_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
        # max_attempts=2, both calls fail with 500
        client = _make_mock_client([{"_status": 500}, {"_status": 500}])
        connector = GooglePlacesConnector(_BASE_CONFIG, http_client=client)

        with pytest.raises(httpx.HTTPStatusError):
            await _collect(connector, {"query": "roofers"})


# ---------------------------------------------------------------------------
# ConnectorRegistry integration
# ---------------------------------------------------------------------------


class TestConnectorRegistryGooglePlaces:
    def test_google_places_registered(self) -> None:
        config = {
            "google_places": {
                "enabled": True,
                "connector_type": "google_places",
                "max_results": 40,
                "rate_limit": {"requests_per_minute": 30},
            }
        }
        registry = ConnectorRegistry(config)
        assert "google_places" in registry.available()

    def test_get_returns_google_places_connector(self) -> None:
        config = {
            "google_places": {
                "enabled": True,
                "connector_type": "google_places",
            }
        }
        registry = ConnectorRegistry(config)
        connector = registry.get("google_places")
        assert isinstance(connector, GooglePlacesConnector)

    def test_disabled_google_places_not_registered(self) -> None:
        config = {
            "google_places": {
                "enabled": False,
                "connector_type": "google_places",
            }
        }
        registry = ConnectorRegistry(config)
        assert "google_places" not in registry.available()

    def test_both_connectors_registered(self) -> None:
        from pathlib import Path

        fixture_dir = str(Path(__file__).parent.parent / "fixtures" / "connector_responses")
        config = {
            "fixture": {"enabled": True, "connector_type": "fixture", "fixture_dir": fixture_dir},
            "google_places": {"enabled": True, "connector_type": "google_places"},
        }
        registry = ConnectorRegistry(config)
        assert set(registry.available()) == {"fixture", "google_places"}


# ---------------------------------------------------------------------------
# extract_fields
# ---------------------------------------------------------------------------


class TestExtractFields:
    def _connector(self) -> GooglePlacesConnector:
        return GooglePlacesConnector({"enabled": True})

    def test_full_record(self) -> None:
        raw = {
            "id": "ChIJabc123",
            "displayName": {"text": "Nashville Cuts", "languageCode": "en"},
            "formattedAddress": "123 Broadway, Nashville, TN 37201, USA",
            "websiteUri": "https://nashvillecuts.com",
            "nationalPhoneNumber": "(615) 555-1234",
        }
        fields = self._connector().extract_fields(raw)
        assert fields["name"] == "Nashville Cuts"
        assert fields["website"] == "https://nashvillecuts.com"
        assert fields["phone"] == "(615) 555-1234"
        assert fields["address"] == "123 Broadway, Nashville, TN 37201, USA"
        assert fields["email"] is None

    def test_missing_optional_fields(self) -> None:
        raw = {"displayName": {"text": "Bare Minimum Shop"}}
        fields = self._connector().extract_fields(raw)
        assert fields["name"] == "Bare Minimum Shop"
        assert fields["website"] is None
        assert fields["phone"] is None
        assert fields["address"] is None

    def test_empty_raw(self) -> None:
        fields = self._connector().extract_fields({})
        assert fields["name"] is None
        assert fields["website"] is None
