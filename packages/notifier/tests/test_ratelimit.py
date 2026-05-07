"""Workflow 20 §11.2 — sliding-window rate limiter."""

from __future__ import annotations

import pytest
from notifier.adapters.base import AdapterRateLimit
from notifier.ratelimit import RateLimiter


@pytest.mark.asyncio
async def test_under_capacity_allows_calls() -> None:
    limiter = RateLimiter(limits={"k": (3, 60.0)})
    for _ in range(3):
        await limiter.acquire("k")


@pytest.mark.asyncio
async def test_over_capacity_raises() -> None:
    limiter = RateLimiter(limits={"k": (2, 60.0)})
    await limiter.acquire("k")
    await limiter.acquire("k")
    with pytest.raises(AdapterRateLimit):
        await limiter.acquire("k")


@pytest.mark.asyncio
async def test_window_expiry_releases_slots() -> None:
    now = [0.0]

    def clock() -> float:
        return now[0]

    limiter = RateLimiter(limits={"k": (2, 60.0)}, clock=clock)
    await limiter.acquire("k")
    await limiter.acquire("k")
    now[0] = 61.0  # window passed
    await limiter.acquire("k")  # should not raise
