# ABOUTME: Unit tests for PageLimitTracker — per-job and per-domain crawl budget
# ABOUTME: enforcement with record-and-check semantics.
from __future__ import annotations

from app.crawl.limits import PageLimitTracker


class TestIsWithinLimits:
    def test_initially_within_limits(self) -> None:
        tracker = PageLimitTracker(max_pages_per_job=10, max_pages_per_domain=5)
        assert tracker.is_within_limits("https://example.com/page") is True

    def test_job_limit_exactly_at_cap_blocks(self) -> None:
        tracker = PageLimitTracker(max_pages_per_job=2, max_pages_per_domain=10)
        tracker.record_crawled("https://example.com/page1")
        tracker.record_crawled("https://example.com/page2")
        assert tracker.is_within_limits("https://example.com/page3") is False

    def test_job_limit_one_below_cap_allows(self) -> None:
        tracker = PageLimitTracker(max_pages_per_job=3, max_pages_per_domain=10)
        tracker.record_crawled("https://example.com/page1")
        tracker.record_crawled("https://example.com/page2")
        assert tracker.is_within_limits("https://example.com/page3") is True

    def test_domain_limit_exactly_at_cap_blocks(self) -> None:
        tracker = PageLimitTracker(max_pages_per_job=100, max_pages_per_domain=2)
        tracker.record_crawled("https://example.com/page1")
        tracker.record_crawled("https://example.com/page2")
        assert tracker.is_within_limits("https://example.com/page3") is False

    def test_domain_limit_does_not_block_other_domain(self) -> None:
        tracker = PageLimitTracker(max_pages_per_job=100, max_pages_per_domain=2)
        tracker.record_crawled("https://example.com/page1")
        tracker.record_crawled("https://example.com/page2")
        # other.com has not hit its limit
        assert tracker.is_within_limits("https://other.com/page") is True

    def test_job_limit_of_one(self) -> None:
        tracker = PageLimitTracker(max_pages_per_job=1, max_pages_per_domain=100)
        tracker.record_crawled("https://example.com/page1")
        assert tracker.is_within_limits("https://example.com/page2") is False

    def test_domain_limit_of_one(self) -> None:
        tracker = PageLimitTracker(max_pages_per_job=100, max_pages_per_domain=1)
        tracker.record_crawled("https://example.com/page1")
        assert tracker.is_within_limits("https://example.com/page2") is False


class TestRecordCrawled:
    def test_increments_job_count(self) -> None:
        tracker = PageLimitTracker(max_pages_per_job=10, max_pages_per_domain=10)
        assert tracker.job_count == 0
        tracker.record_crawled("https://example.com/page")
        assert tracker.job_count == 1

    def test_increments_domain_count(self) -> None:
        tracker = PageLimitTracker(max_pages_per_job=10, max_pages_per_domain=10)
        assert tracker.domain_count("example.com") == 0
        tracker.record_crawled("https://example.com/page")
        assert tracker.domain_count("example.com") == 1

    def test_tracks_multiple_domains_independently(self) -> None:
        tracker = PageLimitTracker(max_pages_per_job=10, max_pages_per_domain=10)
        tracker.record_crawled("https://example.com/p1")
        tracker.record_crawled("https://example.com/p2")
        tracker.record_crawled("https://other.com/p1")

        assert tracker.domain_count("example.com") == 2
        assert tracker.domain_count("other.com") == 1
        assert tracker.job_count == 3

    def test_domain_count_case_insensitive(self) -> None:
        tracker = PageLimitTracker(max_pages_per_job=10, max_pages_per_domain=10)
        tracker.record_crawled("https://Example.COM/page")
        assert tracker.domain_count("example.com") == 1

    def test_unknown_domain_count_is_zero(self) -> None:
        tracker = PageLimitTracker(max_pages_per_job=10, max_pages_per_domain=10)
        assert tracker.domain_count("nevervisited.com") == 0


class TestCombinedLimits:
    def test_job_limit_reached_before_domain_limit(self) -> None:
        tracker = PageLimitTracker(max_pages_per_job=1, max_pages_per_domain=5)
        tracker.record_crawled("https://example.com/p1")
        assert tracker.is_within_limits("https://other.com/p1") is False

    def test_many_pages_across_many_domains(self) -> None:
        tracker = PageLimitTracker(max_pages_per_job=100, max_pages_per_domain=2)
        domains = [f"site{i}.com" for i in range(10)]
        for domain in domains:
            tracker.record_crawled(f"https://{domain}/page1")
            tracker.record_crawled(f"https://{domain}/page2")

        assert tracker.job_count == 20
        for domain in domains:
            assert tracker.domain_count(domain) == 2
            assert tracker.is_within_limits(f"https://{domain}/page3") is False
