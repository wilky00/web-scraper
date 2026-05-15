# ABOUTME: Unit tests for ConnectorBase, FixtureConnector, and ConnectorRegistry.
# ABOUTME: No external services required — all tests use local fixture files or tmp dirs.
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.connectors.base import ConnectorBase, ConnectorResult
from app.connectors.fixture import FixtureConnector
from app.connectors.registry import ConnectorRegistry, UnknownConnectorError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _collect(
    connector: FixtureConnector, job_config: dict | None = None
) -> list[ConnectorResult]:
    results = []
    async for result in connector.discover(job_config or {}):
        results.append(result)
    return results


FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "connector_responses"


# ---------------------------------------------------------------------------
# ConnectorResult
# ---------------------------------------------------------------------------


class TestConnectorResult:
    def test_basic_construction(self) -> None:
        r = ConnectorResult(connector_type="fixture", raw_data={"name": "Acme"})
        assert r.connector_type == "fixture"
        assert r.raw_data == {"name": "Acme"}

    def test_raw_data_preserved(self) -> None:
        data = {"a": 1, "nested": {"b": [1, 2, 3]}}
        r = ConnectorResult(connector_type="test", raw_data=data)
        assert r.raw_data == data


# ---------------------------------------------------------------------------
# ConnectorBase — abstract enforcement
# ---------------------------------------------------------------------------


class TestConnectorBase:
    def test_cannot_instantiate_directly(self) -> None:
        with pytest.raises(TypeError):
            ConnectorBase()  # type: ignore[abstract]

    def test_concrete_subclass_requires_discover(self) -> None:
        class Incomplete(ConnectorBase):
            connector_type = "incomplete"
            # missing discover()

        with pytest.raises(TypeError):
            Incomplete()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# FixtureConnector — valid results
# ---------------------------------------------------------------------------


class TestFixtureConnectorValidResults:
    @pytest.mark.asyncio
    async def test_yields_all_results_from_valid_file(self) -> None:
        connector = FixtureConnector(FIXTURE_DIR)
        results = await _collect(connector)
        # valid_results.json has 3, partial_data.json has 2; empty_results.json has 0
        # sorted order: empty_results, partial_data, valid_results
        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_all_results_have_correct_connector_type(self) -> None:
        connector = FixtureConnector(FIXTURE_DIR)
        results = await _collect(connector)
        assert all(r.connector_type == "fixture" for r in results)

    @pytest.mark.asyncio
    async def test_raw_data_is_dict(self) -> None:
        connector = FixtureConnector(FIXTURE_DIR)
        results = await _collect(connector)
        assert all(isinstance(r.raw_data, dict) for r in results)

    @pytest.mark.asyncio
    async def test_valid_results_contain_expected_fields(self) -> None:
        connector = FixtureConnector(FIXTURE_DIR)
        results = await _collect(connector)
        # First two from sorted order are from empty_results (0) and partial_data (2)
        # Third onwards from valid_results
        names = {r.raw_data["name"] for r in results}
        assert "Acme Roofing Co." in names
        assert "Summit Storm Repair" in names
        assert "Lone Star Exteriors" in names


# ---------------------------------------------------------------------------
# FixtureConnector — isolated single-file tests via tmp_path
# ---------------------------------------------------------------------------


class TestFixtureConnectorIsolated:
    @pytest.mark.asyncio
    async def test_empty_array_yields_nothing(self, tmp_path: Path) -> None:
        (tmp_path / "results.json").write_text("[]")
        connector = FixtureConnector(tmp_path)
        results = await _collect(connector)
        assert results == []

    @pytest.mark.asyncio
    async def test_single_object_file_is_wrapped(self, tmp_path: Path) -> None:
        record = {"place_id": "abc123", "name": "Solo Corp"}
        (tmp_path / "solo.json").write_text(json.dumps(record))
        connector = FixtureConnector(tmp_path)
        results = await _collect(connector)
        assert len(results) == 1
        assert results[0].raw_data["name"] == "Solo Corp"

    @pytest.mark.asyncio
    async def test_multiple_files_combined(self, tmp_path: Path) -> None:
        (tmp_path / "a.json").write_text('[{"name": "A1"}, {"name": "A2"}]')
        (tmp_path / "b.json").write_text('[{"name": "B1"}]')
        connector = FixtureConnector(tmp_path)
        results = await _collect(connector)
        names = [r.raw_data["name"] for r in results]
        assert names == ["A1", "A2", "B1"]  # sorted filename order

    @pytest.mark.asyncio
    async def test_partial_data_records_are_still_yielded(self, tmp_path: Path) -> None:
        records = [{"name": "Minimal", "place_id": "xyz"}]
        (tmp_path / "partial.json").write_text(json.dumps(records))
        connector = FixtureConnector(tmp_path)
        results = await _collect(connector)
        assert len(results) == 1
        assert results[0].raw_data["name"] == "Minimal"

    @pytest.mark.asyncio
    async def test_invalid_json_file_is_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "good.json").write_text('[{"name": "Good"}]')
        (tmp_path / "bad.json").write_text("not valid json {{{")
        connector = FixtureConnector(tmp_path)
        results = await _collect(connector)
        assert len(results) == 1
        assert results[0].raw_data["name"] == "Good"

    @pytest.mark.asyncio
    async def test_non_dict_records_are_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "mixed.json").write_text('[{"name": "Valid"}, "a string", 42]')
        connector = FixtureConnector(tmp_path)
        results = await _collect(connector)
        assert len(results) == 1
        assert results[0].raw_data["name"] == "Valid"

    @pytest.mark.asyncio
    async def test_missing_directory_yields_nothing(self, tmp_path: Path) -> None:
        connector = FixtureConnector(tmp_path / "does_not_exist")
        results = await _collect(connector)
        assert results == []

    @pytest.mark.asyncio
    async def test_empty_directory_yields_nothing(self, tmp_path: Path) -> None:
        connector = FixtureConnector(tmp_path)
        results = await _collect(connector)
        assert results == []

    @pytest.mark.asyncio
    async def test_job_config_is_accepted_and_ignored(self, tmp_path: Path) -> None:
        (tmp_path / "r.json").write_text('[{"name": "R"}]')
        connector = FixtureConnector(tmp_path)
        results = await _collect(connector, {"query": "roofers", "location": "Austin TX"})
        assert len(results) == 1


# ---------------------------------------------------------------------------
# ConnectorRegistry
# ---------------------------------------------------------------------------


class TestConnectorRegistry:
    def test_fixture_connector_registered(self) -> None:
        config = {
            "fixture": {
                "enabled": True,
                "connector_type": "fixture",
                "fixture_dir": str(FIXTURE_DIR),
            }
        }
        registry = ConnectorRegistry(config)
        assert "fixture" in registry.available()

    def test_get_returns_fixture_connector(self) -> None:
        config = {
            "fixture": {
                "enabled": True,
                "connector_type": "fixture",
                "fixture_dir": str(FIXTURE_DIR),
            }
        }
        registry = ConnectorRegistry(config)
        connector = registry.get("fixture")
        assert isinstance(connector, FixtureConnector)

    def test_disabled_connector_not_registered(self) -> None:
        config = {
            "fixture": {
                "enabled": False,
                "connector_type": "fixture",
                "fixture_dir": str(FIXTURE_DIR),
            }
        }
        registry = ConnectorRegistry(config)
        assert "fixture" not in registry.available()

    def test_get_unknown_raises(self) -> None:
        registry = ConnectorRegistry({})
        with pytest.raises(UnknownConnectorError):
            registry.get("nonexistent")

    def test_available_returns_list(self) -> None:
        config = {
            "fixture": {
                "enabled": True,
                "connector_type": "fixture",
                "fixture_dir": str(FIXTURE_DIR),
            }
        }
        registry = ConnectorRegistry(config)
        result = registry.available()
        assert isinstance(result, list)
        assert "fixture" in result

    def test_connector_type_defaults_to_name(self) -> None:
        # When connector_type is omitted, the name itself is used as type.
        # "fixture" name → FixtureConnector
        config = {
            "fixture": {
                "enabled": True,
                "fixture_dir": str(FIXTURE_DIR),
            }
        }
        registry = ConnectorRegistry(config)
        assert isinstance(registry.get("fixture"), FixtureConnector)

    def test_unknown_connector_type_not_registered(self) -> None:
        config = {
            "google_places": {
                "enabled": True,
                "connector_type": "google_places",
            }
        }
        registry = ConnectorRegistry(config)
        # google_places not yet implemented in Phase 3.1
        assert "google_places" not in registry.available()

    def test_empty_config_empty_registry(self) -> None:
        registry = ConnectorRegistry({})
        assert registry.available() == []

    @pytest.mark.asyncio
    async def test_fixture_connector_from_registry_yields_results(self) -> None:
        config = {
            "fixture": {
                "enabled": True,
                "connector_type": "fixture",
                "fixture_dir": str(FIXTURE_DIR),
            }
        }
        registry = ConnectorRegistry(config)
        connector = registry.get("fixture")
        results = await _collect(connector)  # type: ignore[arg-type]
        assert len(results) > 0
