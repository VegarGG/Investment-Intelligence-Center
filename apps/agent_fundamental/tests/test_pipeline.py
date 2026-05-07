"""Workflow 11 §5.4 — writer composes a valid AdviceV1 with citations."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fund.types import Fundamentals, ValuationCase, WatchlistEntry
from fund.writer import (
    InsufficientData,
    WriterContext,
    compose,
    derive_direction,
)


def _entry() -> WatchlistEntry:
    return WatchlistEntry(
        ticker="INTC", venue="NASDAQ", sector="Semiconductors", thesis_tag="turn", peers=()
    )


def _fundamentals(missing: float = 0.0) -> Fundamentals:
    return Fundamentals(
        ticker="INTC",
        venue="NASDAQ",
        sector="Semiconductors",
        asof=datetime(2026, 1, 1, tzinfo=UTC),
        pe=18.0,
        ev_ebitda=10.0,
        fcf_yield=0.04,
        revenue_ttm_usd=60_000_000_000,
        fcf_ttm_usd=4_000_000_000,
        missing_pct=missing,
    )


def _valuation() -> ValuationCase:
    return ValuationCase(
        base=30.0,
        bull=40.0,
        bear=25.0,
        target_12m=32.0,
        assumptions=("Foundry break-even 2027", "DC AI rebound"),
    )


@pytest.mark.asyncio
async def test_compose_emits_valid_advice() -> None:
    ctx = WriterContext(
        entry=_entry(),
        fundamentals=_fundamentals(),
        valuation=_valuation(),
        current_price=24.0,
    )
    advice = await compose(ctx, digest_event_id="evt:1", filing_url="https://e/1")
    assert advice.agent == "fundamental"
    assert advice.asset.ticker == "INTC"
    assert advice.direction == "long"
    assert advice.evidence


@pytest.mark.asyncio
async def test_compose_refuses_insufficient_data() -> None:
    ctx = WriterContext(
        entry=_entry(),
        fundamentals=_fundamentals(missing=0.5),
        valuation=_valuation(),
        current_price=24.0,
    )
    with pytest.raises(InsufficientData):
        await compose(ctx)


def test_direction_bands() -> None:
    assert derive_direction(target_mid=33.0, current_price=20.0) == "long"
    assert derive_direction(target_mid=15.0, current_price=20.0) == "short"
    assert derive_direction(target_mid=20.0, current_price=20.0) == "flat"
