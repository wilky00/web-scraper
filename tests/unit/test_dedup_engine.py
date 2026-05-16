# ABOUTME: Unit tests for DeduplicationEngine — find_duplicates and merge_duplicates.
# ABOUTME: Covers all three matching passes, transitive grouping, status filtering, and merges.
from __future__ import annotations

from app.dedup.engine import DeduplicationEngine, RecordData, SourceData


def _make_record(
    id: str,
    name: str | None = None,
    website: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    city: str | None = None,
    state: str | None = None,
    status: str = "active",
    sources: list[SourceData] | None = None,
) -> RecordData:
    return RecordData(
        id=id,
        name=name,
        website=website,
        email=email,
        phone=phone,
        location_city=city,
        location_state=state,
        status=status,
        sources=sources if sources is not None else [],
    )


engine = DeduplicationEngine()


# ── Pass 1: domain ────────────────────────────────────────────────────────────


def test_pass1_domain_match() -> None:
    a = _make_record("1", name="Alpha Co", website="https://www.example.com")
    b = _make_record("2", name="Beta Co", website="https://example.com/")
    groups = engine.find_duplicates([a, b])
    assert len(groups) == 1
    assert len(groups[0]) == 2


def test_pass1_domain_no_match() -> None:
    a = _make_record("1", website="https://foo.com")
    b = _make_record("2", website="https://bar.com")
    groups = engine.find_duplicates([a, b])
    assert groups == []


def test_pass1_skip_empty_website() -> None:
    a = _make_record("1", website=None)
    b = _make_record("2", website=None)
    groups = engine.find_duplicates([a, b])
    assert groups == []


# ── Pass 2: name + location ───────────────────────────────────────────────────


def test_pass2_same_name_same_city() -> None:
    a = _make_record("1", name="Green Valley Roofing", city="Austin", state="TX")
    b = _make_record("2", name="Green Valley Roofing", city="Austin", state="TX")
    groups = engine.find_duplicates([a, b])
    assert len(groups) == 1


def test_pass2_wildcard_city_one_missing() -> None:
    a = _make_record("1", name="Green Valley Roofing", city="Austin", state="TX")
    b = _make_record("2", name="Green Valley Roofing", city=None, state=None)
    groups = engine.find_duplicates([a, b])
    assert len(groups) == 1


def test_pass2_wildcard_both_missing() -> None:
    a = _make_record("1", name="Green Valley Roofing", city=None, state=None)
    b = _make_record("2", name="Green Valley Roofing", city=None, state=None)
    groups = engine.find_duplicates([a, b])
    assert len(groups) == 1


def test_pass2_different_name_no_match() -> None:
    a = _make_record("1", name="Green Valley Roofing", city="Austin")
    b = _make_record("2", name="Blue Ridge Electric", city="Austin")
    groups = engine.find_duplicates([a, b])
    assert groups == []


def test_pass2_city_conflict_no_match() -> None:
    a = _make_record("1", name="Green Valley Roofing", city="Austin")
    b = _make_record("2", name="Green Valley Roofing", city="Dallas")
    groups = engine.find_duplicates([a, b])
    assert groups == []


# ── Pass 3: contact ───────────────────────────────────────────────────────────


def test_pass3_phone_match() -> None:
    a = _make_record("1", name="Alpha", phone="615-555-0101")
    b = _make_record("2", name="Beta", phone="6155550101")
    groups = engine.find_duplicates([a, b])
    assert len(groups) == 1


def test_pass3_email_match() -> None:
    a = _make_record("1", name="Alpha", email="HELLO@example.com")
    b = _make_record("2", name="Beta", email="hello@example.com")
    groups = engine.find_duplicates([a, b])
    assert len(groups) == 1


def test_pass3_no_match_different_contacts() -> None:
    a = _make_record("1", phone="615-555-1111", email="a@a.com")
    b = _make_record("2", phone="615-555-2222", email="b@b.com")
    groups = engine.find_duplicates([a, b])
    assert groups == []


# ── Transitive grouping ───────────────────────────────────────────────────────


def test_transitive_three_records_one_group() -> None:
    # A-B linked via domain, B-C linked via phone → all three in one group
    a = _make_record("1", name="A", website="https://www.example.com", phone="615-000-0001")
    b = _make_record("2", name="B", website="https://example.com/", phone="615-555-0101")
    c = _make_record("3", name="C", website="https://other.com", phone="6155550101")
    groups = engine.find_duplicates([a, b, c])
    assert len(groups) == 1
    assert len(groups[0]) == 3


# ── Status filtering ──────────────────────────────────────────────────────────


def test_inactive_records_skipped() -> None:
    a = _make_record("1", website="https://example.com", status="active")
    b = _make_record("2", website="https://example.com", status="duplicate")
    groups = engine.find_duplicates([a, b])
    assert groups == []


# ── Edge cases ────────────────────────────────────────────────────────────────


def test_no_duplicates_returns_empty() -> None:
    a = _make_record(
        "1",
        name="Sunrise Landscaping",
        website="https://sunrise.com",
        phone="615-100-0001",
        email="a@a.com",
    )
    b = _make_record(
        "2",
        name="Blue Ridge Electric",
        website="https://blueridge.com",
        phone="615-100-0002",
        email="b@b.com",
    )
    c = _make_record(
        "3",
        name="Coastal HVAC",
        website="https://coastal.com",
        phone="615-100-0003",
        email="c@c.com",
    )
    groups = engine.find_duplicates([a, b, c])
    assert groups == []


def test_single_record_returns_empty() -> None:
    a = _make_record("1", website="https://example.com")
    groups = engine.find_duplicates([a])
    assert groups == []


# ── merge_duplicates ──────────────────────────────────────────────────────────


def test_merge_winner_stays_active() -> None:
    winner = _make_record("1", status="active")
    loser = _make_record("2", status="active")
    engine.merge_duplicates([[winner, loser]])
    assert winner.status == "active"


def test_merge_loser_marked_duplicate() -> None:
    winner = _make_record("1")
    loser = _make_record("2")
    engine.merge_duplicates([[winner, loser]])
    assert loser.status == "duplicate"


def test_merge_loser_canonical_set_to_winner_id() -> None:
    winner = _make_record("w1")
    loser = _make_record("l1")
    engine.merge_duplicates([[winner, loser]])
    assert loser.canonical_record_id == "w1"


def test_merge_sources_transferred_to_winner() -> None:
    src = SourceData(
        record_id="l1",
        field="phone",
        source_url=None,
        source_type="crawl",
        raw_value="555-1234",
    )
    winner = _make_record("w1")
    loser = _make_record("l1", sources=[src])
    engine.merge_duplicates([[winner, loser]])
    assert src in winner.sources
    assert src.record_id == "w1"


def test_merge_loser_sources_cleared() -> None:
    src = SourceData(
        record_id="l1",
        field="email",
        source_url=None,
        source_type="crawl",
        raw_value="x@x.com",
    )
    winner = _make_record("w1")
    loser = _make_record("l1", sources=[src])
    engine.merge_duplicates([[winner, loser]])
    assert loser.sources == []


def test_merge_multiple_groups_independent() -> None:
    w1 = _make_record("w1")
    l1 = _make_record("l1")
    w2 = _make_record("w2")
    l2 = _make_record("l2")
    engine.merge_duplicates([[w1, l1], [w2, l2]])
    assert l1.status == "duplicate"
    assert l1.canonical_record_id == "w1"
    assert l2.status == "duplicate"
    assert l2.canonical_record_id == "w2"
    assert w1.status == "active"
    assert w2.status == "active"
