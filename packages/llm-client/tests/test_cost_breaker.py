"""Workflow 03 §7 — cost meter circuit breaker."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from llm_client.cost_meter import (
    BreakerState,
    CostMeter,
    InMemorySpendStore,
)
from llm_client.types import ChatResponse


def _resp(cost: float, *, fallback: bool = False) -> ChatResponse:
    return ChatResponse(
        text="x",
        model="deepseek-v4-pro",
        tier="pro",
        prompt_tokens=1,
        completion_tokens=1,
        cost_usd=cost,
        cached=False,
        fallback_used=fallback,
        request_id="t",
        latency_ms=1,
    )


class TestPrimaryCap:
    @pytest.mark.asyncio
    async def test_allows_under_cap(self) -> None:
        meter = CostMeter(store=InMemorySpendStore(), monthly_cap_usd=10.0)
        assert await meter.allow() is True

    @pytest.mark.asyncio
    async def test_blocks_at_cap(self) -> None:
        store = InMemorySpendStore()
        meter = CostMeter(store=store, monthly_cap_usd=0.01)
        await meter.record(_resp(0.02))
        assert await meter.allow() is False
        assert meter.state == BreakerState.OPEN

    @pytest.mark.asyncio
    async def test_soft_breach_at_80_percent(self) -> None:
        store = InMemorySpendStore()
        meter = CostMeter(store=store, monthly_cap_usd=10.0)
        await meter.record(_resp(8.5))
        assert await meter.soft_breach() is True
        # but still allows
        assert await meter.allow() is True


class TestFallbackCap:
    @pytest.mark.asyncio
    async def test_fallback_cap_independent_of_primary(self) -> None:
        store = InMemorySpendStore()
        # Generous primary cap, tight fallback cap.
        meter = CostMeter(store=store, monthly_cap_usd=100.0, fallback_cap_usd=1.0)
        # Burn the fallback budget.
        await meter.record(_resp(2.0, fallback=True))
        # Primary calls still allowed (well under primary cap).
        assert await meter.allow(fallback=False) is True
        # Fallback calls now blocked.
        assert await meter.allow(fallback=True) is False


class TestCooldown:
    @pytest.mark.asyncio
    async def test_open_to_half_open_after_cooldown(self) -> None:
        store = InMemorySpendStore()
        meter = CostMeter(store=store, monthly_cap_usd=0.01, cooldown_seconds=0)
        await meter.record(_resp(0.02))
        assert await meter.allow() is False
        # cooldown=0 means we transition to HALF_OPEN immediately on next state read.
        assert meter.state == BreakerState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_manual_reset(self) -> None:
        meter = CostMeter(store=InMemorySpendStore(), monthly_cap_usd=0.01)
        await meter.record(_resp(0.02))
        # Breaker is lazy — allow() is what observes the over-cap state.
        assert await meter.allow() is False
        assert meter.state == BreakerState.OPEN
        meter.reset()
        assert meter.state == BreakerState.CLOSED


class TestRollingWindow:
    @pytest.mark.asyncio
    async def test_old_spend_does_not_count(self) -> None:
        store = InMemorySpendStore()
        # Record spend > 30 days ago.
        ancient = datetime.now(UTC).date() - timedelta(days=60)
        store.rows[(ancient, "pro", False)] = 1000.0
        meter = CostMeter(store=store, monthly_cap_usd=10.0)
        # The ancient row falls outside the rolling window.
        assert await meter.allow() is True
