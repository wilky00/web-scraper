# ABOUTME: API + web integration tests for criteria management endpoints.
# ABOUTME: Overrides require_operator via dependency_overrides to isolate criteria logic from auth.
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.permissions import require_operator
from app.auth.session import SESSION_COOKIE, sign_session_id
from app.main import app
from app.models.criteria import CriteriaGroup, CriteriaVersion
from app.models.user import User
from app.settings import Settings

_SECRET = Settings().secret_key
_SESSION_CSRF = "test-csrf-for-criteria"
_SESSION_ID = "test-session-id-criteria"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_user() -> MagicMock:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.email = "operator@test.com"
    user.role = "operator"
    user.is_active = True
    user.deleted_at = None
    return user


@pytest.fixture
def mock_redis_criteria() -> AsyncMock:
    client: AsyncMock = AsyncMock()
    client.get = AsyncMock(
        return_value=json.dumps({"user_id": str(uuid.uuid4()), "csrf_token": _SESSION_CSRF})
    )
    client.set = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=1)
    return client


@pytest.fixture
def signed_session() -> str:
    return sign_session_id(_SESSION_ID, _SECRET)


def _make_criteria_db_mock(
    group: MagicMock | None = None,
    versions: list[MagicMock] | None = None,
    groups: list[MagicMock] | None = None,
    version_count: int = 0,
) -> AsyncMock:
    """Build a mock AsyncSession that handles criteria queries."""
    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.return_value = group
    scalar_result.scalar.return_value = version_count

    scalars_result = MagicMock()
    scalars_result.scalars.return_value.all.return_value = versions or []

    groups_scalars = MagicMock()
    groups_scalars.scalars.return_value.all.return_value = groups or []

    # Each execute call returns different mocks based on call sequence
    call_count = {"n": 0}

    async def _execute(*args: object, **kwargs: object) -> MagicMock:
        call_count["n"] += 1
        n = call_count["n"]
        if n == 1 and groups is not None:
            return groups_scalars
        if n == 2 and groups is not None:
            # Second execute for version counts
            counts_result = MagicMock()
            counts_result.__iter__ = MagicMock(return_value=iter([]))
            return counts_result
        if versions is not None:
            return scalars_result
        return scalar_result

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.execute = _execute
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    return session


def _set_state(mock_redis: AsyncMock) -> None:
    app.state.engine = MagicMock()
    app.state.redis = mock_redis
    app.state.settings = Settings()


def _clear_state() -> None:
    for attr in ("engine", "redis", "settings"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)


VALID_YAML = """\
metadata:
  name: test-criteria
  display_name: Test Criteria
  description: For testing
  tags: [test]
source:
  connector: fixture
  max_results: 10
"""

INVALID_YAML = """\
metadata:
  name: missing-source
"""


# ---------------------------------------------------------------------------
# POST /api/criteria/validate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_valid_yaml_returns_success(
    mock_user: MagicMock, mock_redis_criteria: AsyncMock
) -> None:
    _set_state(mock_redis_criteria)
    app.dependency_overrides[require_operator] = lambda: mock_user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/api/criteria/validate", data={"yaml_text": VALID_YAML})
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 200
    assert "Valid YAML" in resp.text
    assert "green" in resp.text


@pytest.mark.asyncio
async def test_validate_invalid_yaml_returns_errors(
    mock_user: MagicMock, mock_redis_criteria: AsyncMock
) -> None:
    _set_state(mock_redis_criteria)
    app.dependency_overrides[require_operator] = lambda: mock_user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/api/criteria/validate", data={"yaml_text": INVALID_YAML})
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 200
    assert "Validation errors" in resp.text
    assert "red" in resp.text


@pytest.mark.asyncio
async def test_validate_requires_auth(mock_redis_criteria: AsyncMock) -> None:
    _set_state(mock_redis_criteria)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=False,
        ) as c:
            resp = await c.post("/api/criteria/validate", data={"yaml_text": VALID_YAML})
    finally:
        _clear_state()

    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


# ---------------------------------------------------------------------------
# POST /api/criteria  (create)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_criteria_redirects_on_success(
    mock_user: MagicMock,
    mock_redis_criteria: AsyncMock,
    signed_session: str,
) -> None:
    _set_state(mock_redis_criteria)
    app.dependency_overrides[require_operator] = lambda: mock_user
    db_mock = _make_criteria_db_mock()

    try:
        with patch("app.api.criteria.AsyncSession", return_value=db_mock):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                follow_redirects=False,
            ) as c:
                resp = await c.post(
                    "/api/criteria",
                    data={"yaml_text": VALID_YAML, "csrf_token": _SESSION_CSRF},
                    cookies={SESSION_COOKIE: signed_session},
                )
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/criteria/")


@pytest.mark.asyncio
async def test_create_criteria_csrf_failure_returns_400(
    mock_user: MagicMock,
    mock_redis_criteria: AsyncMock,
    signed_session: str,
) -> None:
    _set_state(mock_redis_criteria)
    app.dependency_overrides[require_operator] = lambda: mock_user
    db_mock = _make_criteria_db_mock()

    try:
        with patch("app.api.criteria.AsyncSession", return_value=db_mock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(
                    "/api/criteria",
                    data={"yaml_text": VALID_YAML, "csrf_token": "wrong-token"},
                    cookies={SESSION_COOKIE: signed_session},
                )
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 400
    assert "Invalid form submission" in resp.text


@pytest.mark.asyncio
async def test_create_criteria_invalid_yaml_returns_422(
    mock_user: MagicMock,
    mock_redis_criteria: AsyncMock,
    signed_session: str,
) -> None:
    _set_state(mock_redis_criteria)
    app.dependency_overrides[require_operator] = lambda: mock_user
    db_mock = _make_criteria_db_mock()

    try:
        with patch("app.api.criteria.AsyncSession", return_value=db_mock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(
                    "/api/criteria",
                    data={"yaml_text": INVALID_YAML, "csrf_token": _SESSION_CSRF},
                    cookies={SESSION_COOKIE: signed_session},
                )
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 422
    assert "Criteria Editor" in resp.text or "editor" in resp.text.lower()


@pytest.mark.asyncio
async def test_create_criteria_duplicate_name_returns_409(
    mock_user: MagicMock,
    mock_redis_criteria: AsyncMock,
    signed_session: str,
) -> None:
    """Duplicate criteria name must return 409 in-page error, not a raw 500."""
    from sqlalchemy.exc import IntegrityError as SAIntegrityError

    _set_state(mock_redis_criteria)
    app.dependency_overrides[require_operator] = lambda: mock_user

    db_mock = _make_criteria_db_mock()
    db_mock.commit = AsyncMock(side_effect=SAIntegrityError("mock", {}, Exception()))

    try:
        with patch("app.api.criteria.AsyncSession", return_value=db_mock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(
                    "/api/criteria",
                    data={"yaml_text": VALID_YAML, "csrf_token": _SESSION_CSRF},
                    cookies={SESSION_COOKIE: signed_session},
                )
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 409
    assert "already exists" in resp.text


# ---------------------------------------------------------------------------
# POST /api/criteria/{group_id}/versions  (save new version)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_group() -> MagicMock:
    group = MagicMock(spec=CriteriaGroup)
    group.id = uuid.uuid4()
    group.name = "test-criteria"
    group.display_name = "Test Criteria"
    group.description = ""
    group.tags = []
    group.is_active = True
    return group


@pytest.mark.asyncio
async def test_save_version_redirects_on_success(
    mock_user: MagicMock,
    mock_redis_criteria: AsyncMock,
    signed_session: str,
    mock_group: MagicMock,
) -> None:
    _set_state(mock_redis_criteria)
    app.dependency_overrides[require_operator] = lambda: mock_user

    group_id = mock_group.id
    # First call: group lookup. Second: validation YAML error load. Third: version count + save.
    call_n = {"n": 0}

    scalar_group = MagicMock()
    scalar_group.scalar_one_or_none.return_value = mock_group
    scalar_count = MagicMock()
    scalar_count.scalar.return_value = 1

    async def _execute(*args: object, **kw: object) -> MagicMock:
        call_n["n"] += 1
        if call_n["n"] == 1:
            return scalar_group
        return scalar_count

    db_mock: AsyncMock = AsyncMock()
    db_mock.__aenter__ = AsyncMock(return_value=db_mock)
    db_mock.__aexit__ = AsyncMock(return_value=None)
    db_mock.execute = _execute
    db_mock.add = MagicMock()
    db_mock.flush = AsyncMock()
    db_mock.commit = AsyncMock()

    try:
        with patch("app.api.criteria.AsyncSession", return_value=db_mock):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                follow_redirects=False,
            ) as c:
                resp = await c.post(
                    f"/api/criteria/{group_id}/versions",
                    data={"yaml_text": VALID_YAML, "csrf_token": _SESSION_CSRF},
                    cookies={SESSION_COOKIE: signed_session},
                )
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 303
    assert str(group_id) in resp.headers["location"]


@pytest.mark.asyncio
async def test_save_version_group_not_found_returns_404(
    mock_user: MagicMock,
    mock_redis_criteria: AsyncMock,
    signed_session: str,
) -> None:
    _set_state(mock_redis_criteria)
    app.dependency_overrides[require_operator] = lambda: mock_user
    db_mock = _make_criteria_db_mock(group=None)

    try:
        with patch("app.api.criteria.AsyncSession", return_value=db_mock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(
                    f"/api/criteria/{uuid.uuid4()}/versions",
                    data={"yaml_text": VALID_YAML, "csrf_token": _SESSION_CSRF},
                    cookies={SESSION_COOKIE: signed_session},
                )
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 404
    assert "not found" in resp.text.lower()


# ---------------------------------------------------------------------------
# GET /criteria  (list page)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_criteria_list_renders(mock_user: MagicMock, mock_redis_criteria: AsyncMock) -> None:
    _set_state(mock_redis_criteria)
    app.dependency_overrides[require_operator] = lambda: mock_user
    db_mock = _make_criteria_db_mock(groups=[])

    try:
        with patch("app.web.criteria.AsyncSession", return_value=db_mock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get("/criteria")
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 200
    assert "Criteria" in resp.text
    assert "New Criteria" in resp.text


@pytest.mark.asyncio
async def test_criteria_list_requires_auth(mock_redis_criteria: AsyncMock) -> None:
    _set_state(mock_redis_criteria)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=False,
        ) as c:
            resp = await c.get("/criteria")
    finally:
        _clear_state()

    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


# ---------------------------------------------------------------------------
# GET /criteria/new  (blank editor)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_criteria_new_renders_editor(
    mock_user: MagicMock, mock_redis_criteria: AsyncMock
) -> None:
    _set_state(mock_redis_criteria)
    app.dependency_overrides[require_operator] = lambda: mock_user

    templates_result = MagicMock()
    templates_result.scalars.return_value.all.return_value = []

    db_mock: AsyncMock = AsyncMock()
    db_mock.__aenter__ = AsyncMock(return_value=db_mock)
    db_mock.__aexit__ = AsyncMock(return_value=None)
    db_mock.execute = AsyncMock(return_value=templates_result)

    try:
        with patch("app.web.criteria.AsyncSession", return_value=db_mock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get("/criteria/new")
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 200
    assert "textarea" in resp.text.lower()
    assert "New Criteria" in resp.text


# ---------------------------------------------------------------------------
# GET /criteria/{group_id}  (editor with existing criteria)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_criteria_editor_renders_existing(
    mock_user: MagicMock,
    mock_redis_criteria: AsyncMock,
    mock_group: MagicMock,
) -> None:
    _set_state(mock_redis_criteria)
    app.dependency_overrides[require_operator] = lambda: mock_user

    version = MagicMock(spec=CriteriaVersion)
    version.id = uuid.uuid4()
    version.version = 1
    version.created_at = datetime(2026, 5, 15, 10, 0, 0, tzinfo=UTC)
    version.config_snapshot = {
        "metadata": {"name": "test", "display_name": "Test", "description": "", "tags": []},
        "source": {"connector": "fixture", "max_results": 10, "query_fields": []},
    }

    call_n = {"n": 0}
    group_result = MagicMock()
    group_result.scalar_one_or_none.return_value = mock_group
    versions_result = MagicMock()
    versions_result.scalars.return_value.all.return_value = [version]
    templates_result = MagicMock()
    templates_result.scalars.return_value.all.return_value = []

    async def _execute(*args: object, **kw: object) -> MagicMock:
        call_n["n"] += 1
        if call_n["n"] == 1:
            return group_result
        if call_n["n"] == 2:
            return versions_result
        return templates_result

    db_mock: AsyncMock = AsyncMock()
    db_mock.__aenter__ = AsyncMock(return_value=db_mock)
    db_mock.__aexit__ = AsyncMock(return_value=None)
    db_mock.execute = _execute

    try:
        with patch("app.web.criteria.AsyncSession", return_value=db_mock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get(f"/criteria/{mock_group.id}")
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 200
    assert "Test Criteria" in resp.text
    assert "v1" in resp.text
    assert "textarea" in resp.text.lower()


@pytest.mark.asyncio
async def test_criteria_editor_unknown_group_redirects(
    mock_user: MagicMock, mock_redis_criteria: AsyncMock
) -> None:
    _set_state(mock_redis_criteria)
    app.dependency_overrides[require_operator] = lambda: mock_user

    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.return_value = None
    scalars_result = MagicMock()
    scalars_result.scalars.return_value.all.return_value = []

    call_n = {"n": 0}

    async def _execute(*args: object, **kw: object) -> MagicMock:
        call_n["n"] += 1
        return scalar_result if call_n["n"] == 1 else scalars_result

    db_mock: AsyncMock = AsyncMock()
    db_mock.__aenter__ = AsyncMock(return_value=db_mock)
    db_mock.__aexit__ = AsyncMock(return_value=None)
    db_mock.execute = _execute

    try:
        with patch("app.web.criteria.AsyncSession", return_value=db_mock):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                follow_redirects=False,
            ) as c:
                resp = await c.get(f"/criteria/{uuid.uuid4()}")
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 303
    assert resp.headers["location"] == "/criteria"


# ---------------------------------------------------------------------------
# GET /api/criteria/{group_id}/yaml
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_criteria_yaml_returns_yaml(
    mock_user: MagicMock, mock_redis_criteria: AsyncMock
) -> None:
    _set_state(mock_redis_criteria)
    app.dependency_overrides[require_operator] = lambda: mock_user

    version_mock = MagicMock(spec=CriteriaVersion)
    version_mock.config_snapshot = {
        "metadata": {"name": "test", "display_name": "Test", "description": "", "tags": []},
        "source": {"connector": "fixture", "max_results": 10, "query_fields": []},
    }

    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.return_value = version_mock

    db_mock: AsyncMock = AsyncMock()
    db_mock.__aenter__ = AsyncMock(return_value=db_mock)
    db_mock.__aexit__ = AsyncMock(return_value=None)
    db_mock.execute = AsyncMock(return_value=scalar_result)

    gid = uuid.uuid4()
    try:
        with patch("app.api.criteria.AsyncSession", return_value=db_mock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get(f"/api/criteria/{gid}/yaml")
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 200
    body = resp.json()
    assert "yaml" in body
    assert "name: test" in body["yaml"]


@pytest.mark.asyncio
async def test_get_criteria_yaml_returns_404_when_not_found(
    mock_user: MagicMock, mock_redis_criteria: AsyncMock
) -> None:
    _set_state(mock_redis_criteria)
    app.dependency_overrides[require_operator] = lambda: mock_user

    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.return_value = None

    db_mock: AsyncMock = AsyncMock()
    db_mock.__aenter__ = AsyncMock(return_value=db_mock)
    db_mock.__aexit__ = AsyncMock(return_value=None)
    db_mock.execute = AsyncMock(return_value=scalar_result)

    try:
        with patch("app.api.criteria.AsyncSession", return_value=db_mock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get(f"/api/criteria/{uuid.uuid4()}/yaml")
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/criteria/{group_id}/delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_criteria_soft_deletes(
    mock_user: MagicMock,
    mock_redis_criteria: AsyncMock,
    signed_session: str,
    mock_group: MagicMock,
) -> None:
    mock_group.is_template = False
    _set_state(mock_redis_criteria)
    app.dependency_overrides[require_operator] = lambda: mock_user
    db_mock = _make_criteria_db_mock(group=mock_group)

    try:
        with patch("app.api.criteria.AsyncSession", return_value=db_mock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(
                    f"/api/criteria/{mock_group.id}/delete",
                    data={"csrf_token": _SESSION_CSRF},
                    cookies={SESSION_COOKIE: signed_session},
                )
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 200
    assert resp.json().get("ok") is True
    assert mock_group.is_active is False


@pytest.mark.asyncio
async def test_delete_template_blocked(
    mock_user: MagicMock,
    mock_redis_criteria: AsyncMock,
    signed_session: str,
    mock_group: MagicMock,
) -> None:
    mock_group.is_template = True
    _set_state(mock_redis_criteria)
    app.dependency_overrides[require_operator] = lambda: mock_user
    db_mock = _make_criteria_db_mock(group=mock_group)

    try:
        with patch("app.api.criteria.AsyncSession", return_value=db_mock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(
                    f"/api/criteria/{mock_group.id}/delete",
                    data={"csrf_token": _SESSION_CSRF},
                    cookies={SESSION_COOKIE: signed_session},
                )
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 422
    assert "template" in resp.json()["error"].lower()


# ---------------------------------------------------------------------------
# POST /api/criteria/{group_id}/clone
# ---------------------------------------------------------------------------


def _make_clone_db_mock(
    group: MagicMock,
    version: MagicMock,
    commit_side_effect: list[Exception | None] | None = None,
) -> AsyncMock:
    """Mock that handles load (group + version) then clone insert."""
    group_result = MagicMock()
    group_result.scalar_one_or_none.return_value = group

    version_result = MagicMock()
    version_result.scalar_one_or_none.return_value = version

    call_n = {"n": 0}

    async def _execute(*args: object, **kw: object) -> MagicMock:
        call_n["n"] += 1
        if call_n["n"] == 1:
            return group_result
        return version_result

    db_mock: AsyncMock = AsyncMock()
    db_mock.__aenter__ = AsyncMock(return_value=db_mock)
    db_mock.__aexit__ = AsyncMock(return_value=None)
    db_mock.execute = _execute
    db_mock.add = MagicMock()
    db_mock.flush = AsyncMock()

    if commit_side_effect:
        commit_call_n = {"n": 0}
        effects = commit_side_effect

        async def _commit() -> None:
            i = commit_call_n["n"]
            commit_call_n["n"] += 1
            exc = effects[i] if i < len(effects) else None
            if exc is not None:
                raise exc

        db_mock.commit = _commit
    else:
        db_mock.commit = AsyncMock()

    return db_mock


@pytest.fixture
def mock_version() -> MagicMock:
    v = MagicMock(spec=CriteriaVersion)
    v.id = uuid.uuid4()
    v.version = 1
    v.config_snapshot = {
        "metadata": {"name": "test-criteria", "display_name": "Test Criteria", "tags": []},
        "source": {"connector": "fixture", "max_results": 10},
    }
    return v


@pytest.mark.asyncio
async def test_clone_criteria_creates_copy(
    mock_user: MagicMock,
    mock_redis_criteria: AsyncMock,
    signed_session: str,
    mock_group: MagicMock,
    mock_version: MagicMock,
) -> None:
    mock_group.is_template = False
    _set_state(mock_redis_criteria)
    app.dependency_overrides[require_operator] = lambda: mock_user
    db_mock = _make_clone_db_mock(mock_group, mock_version)

    try:
        with patch("app.api.criteria.AsyncSession", return_value=db_mock):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                follow_redirects=False,
            ) as c:
                resp = await c.post(
                    f"/api/criteria/{mock_group.id}/clone",
                    data={"csrf_token": _SESSION_CSRF},
                    cookies={SESSION_COOKIE: signed_session},
                )
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 200
    assert "HX-Redirect" in resp.headers
    assert "/criteria/" in resp.headers["HX-Redirect"]


@pytest.mark.asyncio
async def test_clone_name_collision_increments_suffix(
    mock_user: MagicMock,
    mock_redis_criteria: AsyncMock,
    signed_session: str,
    mock_group: MagicMock,
    mock_version: MagicMock,
) -> None:
    from sqlalchemy.exc import IntegrityError as SAIntegrityError

    mock_group.is_template = False
    _set_state(mock_redis_criteria)
    app.dependency_overrides[require_operator] = lambda: mock_user
    # First commit raises IntegrityError (name collision), second succeeds
    db_mock = _make_clone_db_mock(
        mock_group,
        mock_version,
        commit_side_effect=[SAIntegrityError("mock", {}, Exception()), None],
    )

    try:
        with patch("app.api.criteria.AsyncSession", return_value=db_mock):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                follow_redirects=False,
            ) as c:
                resp = await c.post(
                    f"/api/criteria/{mock_group.id}/clone",
                    data={"csrf_token": _SESSION_CSRF},
                    cookies={SESSION_COOKIE: signed_session},
                )
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 200
    assert "HX-Redirect" in resp.headers
