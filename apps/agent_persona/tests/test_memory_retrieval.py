"""Workflow 13 §2.3 + §9 — memory retrieval and recency boost."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from persona.memory import (
    InMemoryMemoryStore,
    score_with_recency,
)
from persona.types import MemoryEntry


def _entry(
    text: str, *, kind: str = "decision", days_old: int = 0, pnl_r: float | None = None
) -> MemoryEntry:
    return MemoryEntry(
        doc_id=f"doc:{text[:8]}",
        text=text,
        kind=kind,
        pnl_r=pnl_r,
        days_old=days_old,
        metadata={
            "indexed_at": (datetime.now(UTC) - timedelta(days=days_old)).isoformat(),
        },
    )


@pytest.mark.asyncio
async def test_query_returns_keyword_matches() -> None:
    store = InMemoryMemoryStore()
    await store.add("rogers", _entry("Long gold during disinflation"))
    await store.add("rogers", _entry("Short tech valuations 2021"))
    hits = await store.query("rogers", "gold disinflation 2026")
    assert hits
    assert "gold" in hits[0].text.lower()


def test_recency_boost_prefers_recent() -> None:
    fresh = _entry("trade A", days_old=10)
    stale = _entry("trade A", days_old=400)
    base = 1.0
    assert score_with_recency(base, fresh) > score_with_recency(base, stale)


def test_losing_trades_penalized() -> None:
    winner = _entry("trade", pnl_r=2.0)
    loser = _entry("trade", pnl_r=-1.5)
    assert score_with_recency(1.0, winner) > score_with_recency(1.0, loser)


@pytest.mark.asyncio
async def test_lessons_surface_even_without_keyword_match() -> None:
    store = InMemoryMemoryStore()
    await store.add(
        "rogers",
        _entry("Patience pays in cycles.", kind="lesson", pnl_r=1.5),
    )
    hits = await store.query("rogers", "platinum spike")
    assert hits and hits[0].kind == "lesson"
