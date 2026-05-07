"""Workflow 10 §5.3 — hash gate + semantic gate."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from intel.dedupe.hash_gate import HashGate, InMemoryHashStore
from intel.dedupe.semantic_gate import (
    InMemorySemanticIndex,
    SemanticGate,
    hash_embed,
)
from intel.types import RawEvent


async def _embed(text: str) -> list[float]:
    return hash_embed(text)


def _ev(title: str, *, source: str = "rss:reuters", body: str = "") -> RawEvent:
    when = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    return RawEvent(
        source_id=source,
        event_ts=when,
        ingest_ts=when,
        url=f"https://example.com/{title}",
        title=title,
        body=body or title,
        lang="en",
    )


@pytest.mark.asyncio
async def test_hash_gate_rejects_repeat() -> None:
    gate = HashGate(InMemoryHashStore())
    ev = _ev("Fed cuts rates 50bps")
    assert await gate.accept(ev) is True
    assert await gate.accept(ev) is False


@pytest.mark.asyncio
async def test_hash_gate_distinguishes_sources() -> None:
    gate = HashGate(InMemoryHashStore())
    a = _ev("Same headline", source="rss:reuters")
    b = _ev("Same headline", source="rss:bloomberg")
    assert await gate.accept(a) is True
    assert await gate.accept(b) is True


@pytest.mark.asyncio
async def test_semantic_gate_drops_near_duplicate() -> None:
    gate = SemanticGate(
        InMemorySemanticIndex(),
        embed=_embed,
        threshold=0.95,
    )
    ok1, _ = await gate.accept(_ev("Apple beats earnings handily"))
    ok2, dup = await gate.accept(_ev("Apple beats earnings handily."))
    assert ok1 is True
    assert ok2 is False
    assert dup is not None


@pytest.mark.asyncio
async def test_semantic_gate_keeps_distinct_news() -> None:
    gate = SemanticGate(InMemorySemanticIndex(), embed=_embed)
    ok1, _ = await gate.accept(_ev("ECB holds rates"))
    ok2, _ = await gate.accept(_ev("PBoC injects liquidity"))
    assert ok1 is True and ok2 is True
