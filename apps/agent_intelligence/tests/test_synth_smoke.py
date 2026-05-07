"""Workflow 10 §5.8 — synth call returns a parseable IntelDigestV1 with stub LLM."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from intel.synth import synthesize
from intel.types import Event, SourceCfg


def _ev() -> Event:
    when = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    return Event(
        id="01HX0000000000000000000001",
        source_id="rss:reuters",
        source_region="GLOBAL",
        source_lean="center",
        event_ts=when,
        title="Fed cuts rates",
        body="...",
        title_en="Fed cuts rates",
        body_en="...",
        lang="en",
    )


@pytest.mark.asyncio
async def test_synth_returns_valid_digest() -> None:
    src = SourceCfg(
        id="rss:reuters", region="GLOBAL", lean="center", region_weight=1.0, language="en"
    )
    digest = await synthesize(
        [_ev()],
        macro_releases=[],
        macro_regime="unknown",
        sources=[src],
    )
    assert digest.macro_thesis
    assert digest.bias_balance.by_region.get("GLOBAL", 0.0) > 0
