# ABOUTME: DeduplicationEngine — finds and merges duplicate BusinessRecord-like data objects.
# ABOUTME: Operates on plain dataclasses (RecordData/SourceData); no DB I/O.
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.dedup.normalize import (
    normalize_domain,
    normalize_email,
    normalize_name,
    normalize_phone,
)


@dataclass
class SourceData:
    record_id: Any  # mirrors the type of RecordData.id (UUID, int, …)
    field: str
    source_url: str | None
    source_type: str
    raw_value: str | None


@dataclass
class RecordData:
    id: Any  # hashable — UUID, int, str, …
    name: str | None
    website: str | None
    email: str | None
    phone: str | None
    location_city: str | None
    location_state: str | None
    status: str = "active"
    canonical_record_id: Any = None
    sources: list[SourceData] = field(default_factory=list)


class DeduplicationEngine:
    # ── Union-find helpers ────────────────────────────────────────────────────

    @staticmethod
    def _find(parent: dict[int, int], x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]  # path compression
            x = parent[x]
        return x

    @staticmethod
    def _union(parent: dict[int, int], x: int, y: int) -> None:
        rx, ry = DeduplicationEngine._find(parent, x), DeduplicationEngine._find(parent, y)
        if rx != ry:
            parent[ry] = rx  # merge ry into rx

    # ── Public API ────────────────────────────────────────────────────────────

    def find_duplicates(self, records: list[RecordData]) -> list[list[RecordData]]:
        """Return groups of 2+ records that are likely duplicates.

        Only active records are considered. Three passes:
          1. Domain match
          2. Normalised name + location match
          3. Phone or e-mail match
        Union-find merges transitive links so A-B + B-C → one group {A,B,C}.
        """
        active = [r for r in records if r.status == "active"]
        n = len(active)
        if n < 2:
            return []

        # Map index → parent index (union-find)
        parent: dict[int, int] = {i: i for i in range(n)}

        # ── Pass 1: domain match ──────────────────────────────────────────────
        domains = [normalize_domain(r.website) for r in active]
        for i in range(n):
            if not domains[i]:
                continue
            for j in range(i + 1, n):
                if not domains[j]:
                    continue
                if domains[i] == domains[j]:
                    self._union(parent, i, j)

        # ── Pass 2: name + location match ────────────────────────────────────
        names = [normalize_name(r.name) for r in active]
        for i in range(n):
            if not names[i]:
                continue
            for j in range(i + 1, n):
                if not names[j]:
                    continue
                if names[i] != names[j]:
                    continue
                # Location match: missing value on either side is a wildcard
                a, b = active[i], active[j]
                city_a = (a.location_city or "").strip().lower()
                city_b = (b.location_city or "").strip().lower()
                state_a = (a.location_state or "").strip().lower()
                state_b = (b.location_state or "").strip().lower()

                city_ok = (not city_a or not city_b or city_a == city_b)
                state_ok = (not state_a or not state_b or state_a == state_b)

                if city_ok and state_ok:
                    self._union(parent, i, j)

        # ── Pass 3: phone or e-mail match ────────────────────────────────────
        phones = [normalize_phone(r.phone) for r in active]
        emails = [normalize_email(r.email) for r in active]
        for i in range(n):
            for j in range(i + 1, n):
                phone_match = phones[i] and phones[j] and phones[i] == phones[j]
                email_match = emails[i] and emails[j] and emails[i] == emails[j]
                if phone_match or email_match:
                    self._union(parent, i, j)

        # ── Collect groups ────────────────────────────────────────────────────
        groups: dict[int, list[RecordData]] = {}
        for i in range(n):
            root = self._find(parent, i)
            groups.setdefault(root, []).append(active[i])

        return [g for g in groups.values() if len(g) >= 2]

    def merge_duplicates(self, groups: list[list[RecordData]]) -> None:
        """Mutate records in-place.

        For each group index 0 is the winner; the rest are losers.
        Losers are marked 'duplicate', their canonical_record_id is set to
        winner.id, and their sources are transferred to the winner.
        """
        for group in groups:
            winner = group[0]
            for loser in group[1:]:
                loser.status = "duplicate"
                loser.canonical_record_id = winner.id
                for source in loser.sources:
                    source.record_id = winner.id
                    winner.sources.append(source)
                loser.sources = []
