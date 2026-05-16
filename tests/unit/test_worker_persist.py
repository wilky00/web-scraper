# ABOUTME: Unit tests for persist_crawl_page() and log_crawl_event() DB helpers.
# ABOUTME: Uses a mock AsyncSession to verify ORM object construction and flush behavior.
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

from app.models.crawl import CrawlPage
from app.models.job import CrawlJobEvent
from app.worker.fetcher import FetchResult
from app.worker.persist import log_crawl_event, persist_crawl_page


def make_result(**kwargs: object) -> FetchResult:
    defaults: dict[str, object] = {
        "url": "https://example.com/page",
        "canonical_url": "https://example.com/page",
        "status_code": 200,
        "html": "<html>ok</html>",
        "content_type": "text/html",
        "depth": 0,
        "error": None,
    }
    defaults.update(kwargs)
    return FetchResult(**defaults)  # type: ignore[arg-type]


def make_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


class TestPersistCrawlPage:
    async def test_returns_crawl_page_instance(self) -> None:
        session = make_session()
        job_id = uuid.uuid4()
        page = await persist_crawl_page(session, job_id, make_result())
        assert isinstance(page, CrawlPage)

    async def test_sets_url_and_canonical(self) -> None:
        session = make_session()
        result = make_result(
            url="https://example.com/page", canonical_url="https://example.com/page"
        )
        page = await persist_crawl_page(session, uuid.uuid4(), result)
        assert page.url == "https://example.com/page"
        assert page.canonical_url == "https://example.com/page"

    async def test_sets_status_code(self) -> None:
        session = make_session()
        page = await persist_crawl_page(session, uuid.uuid4(), make_result(status_code=404))
        assert page.status_code == 404

    async def test_sets_crawl_depth(self) -> None:
        session = make_session()
        page = await persist_crawl_page(session, uuid.uuid4(), make_result(depth=2))
        assert page.crawl_depth == 2

    async def test_raw_html_path_is_none(self) -> None:
        session = make_session()
        page = await persist_crawl_page(session, uuid.uuid4(), make_result())
        assert page.raw_html_path is None

    async def test_sets_error_on_failed_result(self) -> None:
        session = make_session()
        result = make_result(status_code=None, html="", error="timeout after 10s")
        page = await persist_crawl_page(session, uuid.uuid4(), result)
        assert page.error == "timeout after 10s"

    async def test_error_is_none_on_success(self) -> None:
        session = make_session()
        page = await persist_crawl_page(session, uuid.uuid4(), make_result())
        assert page.error is None

    async def test_adds_to_session_and_flushes(self) -> None:
        session = make_session()
        job_id = uuid.uuid4()
        page = await persist_crawl_page(session, job_id, make_result())
        session.add.assert_called_once_with(page)
        session.flush.assert_awaited_once()

    async def test_sets_job_id(self) -> None:
        session = make_session()
        job_id = uuid.uuid4()
        page = await persist_crawl_page(session, job_id, make_result())
        assert page.job_id == job_id


class TestLogCrawlEvent:
    async def test_returns_crawl_job_event_instance(self) -> None:
        session = make_session()
        event = await log_crawl_event(session, uuid.uuid4(), "page_fetched", "Fetched ok")
        assert isinstance(event, CrawlJobEvent)

    async def test_sets_event_type_and_message(self) -> None:
        session = make_session()
        event = await log_crawl_event(session, uuid.uuid4(), "fetch_error", "Connection refused")
        assert event.event_type == "fetch_error"
        assert event.message == "Connection refused"

    async def test_sets_job_id(self) -> None:
        session = make_session()
        job_id = uuid.uuid4()
        event = await log_crawl_event(session, job_id, "page_fetched", "ok")
        assert event.job_id == job_id

    async def test_event_data_defaults_to_empty_dict(self) -> None:
        session = make_session()
        event = await log_crawl_event(session, uuid.uuid4(), "page_fetched", "ok")
        assert event.event_data == {}

    async def test_event_data_passed_through(self) -> None:
        session = make_session()
        data = {"url": "https://example.com/", "status": 200}
        event = await log_crawl_event(session, uuid.uuid4(), "page_fetched", "ok", data=data)
        assert event.event_data == {"url": "https://example.com/", "status": 200}

    async def test_adds_to_session_and_flushes(self) -> None:
        session = make_session()
        event = await log_crawl_event(session, uuid.uuid4(), "page_fetched", "ok")
        session.add.assert_called_once_with(event)
        session.flush.assert_awaited_once()
