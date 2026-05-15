# ABOUTME: In-memory page limit tracker for per-job and per-domain crawl budgets.
# ABOUTME: One instance per crawl job; thread-safe for single-threaded async use.
from __future__ import annotations

from urllib.parse import urlparse


class PageLimitTracker:
    """Tracks pages crawled per job and per domain against configured limits.

    Call ``is_within_limits(url)`` before fetching a page, then
    ``record_crawled(url)`` after successfully fetching it.
    """

    def __init__(self, max_pages_per_job: int, max_pages_per_domain: int) -> None:
        self._max_per_job = max_pages_per_job
        self._max_per_domain = max_pages_per_domain
        self._job_count: int = 0
        self._domain_counts: dict[str, int] = {}

    @property
    def job_count(self) -> int:
        return self._job_count

    def domain_count(self, domain: str) -> int:
        return self._domain_counts.get(domain.lower(), 0)

    def is_within_limits(self, url: str) -> bool:
        """Return True if crawling this URL would be within both limits."""
        if self._job_count >= self._max_per_job:
            return False
        domain = _extract_domain(url)
        return self._domain_counts.get(domain, 0) < self._max_per_domain

    def record_crawled(self, url: str) -> None:
        """Increment counters after successfully fetching a page."""
        self._job_count += 1
        domain = _extract_domain(url)
        self._domain_counts[domain] = self._domain_counts.get(domain, 0) + 1


def _extract_domain(url: str) -> str:
    return urlparse(url).netloc.lower()
