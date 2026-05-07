"""Workflow 10 §3 — full pipeline with stubbed externals."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from intel.crawler.protocol import InMemoryCrawler
from intel.dedupe.hash_gate import HashGate, InMemoryHashStore
from intel.dedupe.semantic_gate import (
    InMemorySemanticIndex,
    SemanticGate,
    hash_embed,
)
from intel.macro import InMemoryMacroSource
from intel.persistence import InMemoryEventStore
from intel.pipeline import IntelPipeline
from intel.types import RawEvent, SourceCfg


async def _embed(text: str) -> list[float]:
    return hash_embed(text)


def _src(sid: str, region: str, lean: str) -> SourceCfg:
    return SourceCfg(id=sid, region=region, lean=lean, region_weight=1.0, language="en")


def _raw(source: str, title: str, *, body: str = "") -> RawEvent:
    when = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    return RawEvent(
        source_id=source,
        event_ts=when,
        ingest_ts=when,
        url=f"https://e/{title.replace(' ', '_')}",
        title=title,
        body=body or title,
        lang="en",
    )


@pytest.mark.asyncio
async def test_pipeline_produces_three_outputs() -> None:
    sources = [_src("rss:us", "US", "center"), _src("rss:cn", "CN", "state")]
    crawler = InMemoryCrawler(
        {
            "rss:us": [_raw("rss:us", "Fed signals slower hikes")],
            "rss:cn": [_raw("rss:cn", "PBoC adds RMB liquidity")],
        }
    )
    pipeline = IntelPipeline(
        sources=sources,
        crawler=crawler,
        hash_gate=HashGate(InMemoryHashStore()),
        semantic_gate=SemanticGate(InMemorySemanticIndex(), embed=_embed),
        macro=InMemoryMacroSource([]),
        event_store=InMemoryEventStore(),
    )
    result = await pipeline.run(macro_regime="rate_cut")
    assert len(result.accepted_events) == 2
    assert result.dropped_hash == 0
    assert result.digest is not None
    assert result.brief is not None
    assert result.dashboard is not None


@pytest.mark.asyncio
async def test_pipeline_dedupes_retransmission() -> None:
    sources = [_src("rss:us", "US", "center")]
    raw = _raw("rss:us", "Same headline twice")
    crawler = InMemoryCrawler({"rss:us": [raw, raw]})
    store = InMemoryEventStore()
    pipeline = IntelPipeline(
        sources=sources,
        crawler=crawler,
        hash_gate=HashGate(InMemoryHashStore()),
        semantic_gate=SemanticGate(InMemorySemanticIndex(), embed=_embed),
        macro=InMemoryMacroSource([]),
        event_store=store,
    )
    result = await pipeline.run()
    assert len(result.accepted_events) == 1
    assert result.dropped_hash == 1
    assert len(store.rows) == 1
