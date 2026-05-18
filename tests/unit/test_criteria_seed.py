# ABOUTME: Unit tests for criteria example template seeding — idempotency and template count.
# ABOUTME: Mocks the AsyncSession; never touches a real database.
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.criteria.seed import _TEMPLATES, seed_example_criteria


@pytest.mark.asyncio
async def test_seed_skips_when_all_templates_already_exist() -> None:
    # Per-name existence check returns a group → all 5 templates already present
    existing_group = MagicMock()
    existing_result = MagicMock()
    existing_result.scalar_one_or_none.return_value = existing_group

    commit_calls: list[None] = []

    class _AlreadyExistsSession:
        def __init__(self, engine: object) -> None:
            self._db: AsyncMock = AsyncMock()
            self._db.__aenter__ = AsyncMock(return_value=self._db)
            self._db.__aexit__ = AsyncMock(return_value=None)
            self._db.execute = AsyncMock(return_value=existing_result)
            self._db.add = MagicMock()
            self._db.flush = AsyncMock()

            async def _commit() -> None:
                commit_calls.append(None)

            self._db.commit = _commit

        async def __aenter__(self) -> AsyncMock:
            return self._db

        async def __aexit__(self, *_: object) -> None:
            pass

    engine = MagicMock()
    with patch("app.criteria.seed.AsyncSession", _AlreadyExistsSession):
        await seed_example_criteria(engine, uuid.uuid4())

    # commit should never be called — every template was already present
    assert len(commit_calls) == 0


@pytest.mark.asyncio
async def test_seed_creates_five_templates() -> None:
    # First call (existence check): returns None → table is empty
    empty_result = MagicMock()
    empty_result.scalar_one_or_none.return_value = None

    call_count = {"n": 0}

    def _make_db_mock() -> AsyncMock:
        db: AsyncMock = AsyncMock()
        db.__aenter__ = AsyncMock(return_value=db)
        db.__aexit__ = AsyncMock(return_value=None)
        db.execute = AsyncMock(return_value=empty_result)
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        return db

    created_groups: list[str] = []

    original_session = __import__(
        "sqlalchemy.ext.asyncio", fromlist=["AsyncSession"]
    ).AsyncSession

    class _FakeSession:
        def __init__(self, engine: object) -> None:
            self._db = _make_db_mock()
            # Track group names via add()
            original_add = self._db.add

            def _add(obj: object) -> None:
                from app.models.criteria import CriteriaGroup

                if isinstance(obj, CriteriaGroup):
                    created_groups.append(obj.name)
                original_add(obj)

            self._db.add = _add

        async def __aenter__(self) -> AsyncMock:
            return self._db

        async def __aexit__(self, *_: object) -> None:
            pass

    engine = MagicMock()

    with patch("app.criteria.seed.AsyncSession", _FakeSession):
        await seed_example_criteria(engine, uuid.uuid4())

    assert len(created_groups) == len(_TEMPLATES), (
        f"Expected {len(_TEMPLATES)} CriteriaGroup inserts, got {len(created_groups)}"
    )
    # All names must be unique
    assert len(set(created_groups)) == len(created_groups)
