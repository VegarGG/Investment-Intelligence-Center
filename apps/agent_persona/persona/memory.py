"""Persona memory store (workflow 13 §2.3 + §9 recency boost).

Production wires ChromaDB collection `persona_memory_<slug>`. Tests use
the in-memory backend with the same retrieval scoring.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Protocol

from .types import MemoryEntry

RECENCY_HALF_LIFE_DAYS = 365.0
LOSING_TRADE_PENALTY = 1.0  # subtract this from score when pnl_r < -1


class MemoryStore(Protocol):
    async def query(self, slug: str, query: str, *, k: int = 8) -> list[MemoryEntry]: ...

    async def add(self, slug: str, entry: MemoryEntry) -> None: ...

    async def update_pnl(self, slug: str, doc_id: str, pnl_r: float) -> None: ...

    async def all(self, slug: str) -> list[MemoryEntry]: ...


class InMemoryMemoryStore:
    """Keyword-overlap retriever — adequate for unit tests; production uses Chroma."""

    def __init__(self) -> None:
        self._by_slug: dict[str, list[MemoryEntry]] = {}

    async def query(self, slug: str, query: str, *, k: int = 8) -> list[MemoryEntry]:
        entries = self._by_slug.get(slug, [])
        terms = {t.lower() for t in query.split() if len(t) > 3}
        now = datetime.now(UTC)
        scored: list[tuple[float, MemoryEntry]] = []
        for entry in entries:
            text = entry.text.lower()
            base = sum(1 for t in terms if t in text)
            if base == 0 and entry.kind != "lesson":
                continue
            score = score_with_recency(base + (0.5 if entry.kind == "lesson" else 0.0), entry)
            scored.append((score, entry))
        scored.sort(key=lambda r: r[0], reverse=True)
        out = []
        for score, entry in scored[:k]:
            entry.similarity = score
            entry.days_old = (now - _meta_dt(entry, "indexed_at", now)).days
            out.append(entry)
        return out

    async def add(self, slug: str, entry: MemoryEntry) -> None:
        self._by_slug.setdefault(slug, []).append(entry)

    async def update_pnl(self, slug: str, doc_id: str, pnl_r: float) -> None:
        for entry in self._by_slug.get(slug, []):
            if entry.doc_id == doc_id:
                entry.pnl_r = pnl_r
                return

    async def all(self, slug: str) -> list[MemoryEntry]:
        return list(self._by_slug.get(slug, []))


def score_with_recency(base: float, entry: MemoryEntry) -> float:
    """Score = base * (0.5 + 0.5 * exp(-days/half_life)) − loser penalty.

    Workflow 13 §9: pure cosine returns stale memories — combine with a
    recency boost; down-weight lessons from losing trades.
    """
    decay = 0.5 + 0.5 * math.exp(-entry.days_old / RECENCY_HALF_LIFE_DAYS)
    score = base * decay
    if entry.pnl_r is not None and entry.pnl_r < -1:
        score -= LOSING_TRADE_PENALTY
    return score


def filter_by_universe(candidates: Iterable[str], universe_weights: dict[str, float]) -> list[str]:
    """Drop candidates whose universe slot has zero weight (workflow 13 §5.2)."""
    if not universe_weights:
        return list(candidates)
    return [c for c in candidates if universe_weights.get(c, 1.0) > 0]


def _meta_dt(entry: MemoryEntry, key: str, default: datetime) -> datetime:
    raw = entry.metadata.get(key)
    if not raw:
        return default
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return default
