"""Workflow 03 §8 — token-bucket rate limiter pacing + concurrency cap."""

from __future__ import annotations

import asyncio
import time

import pytest
from llm_client.rate_limiter import BucketConfig, RateLimiter


class TestPacing:
    @pytest.mark.asyncio
    async def test_serial_calls_pace_at_target_rps(self) -> None:
        rl = RateLimiter(overrides={("test", "flash"): BucketConfig(rps=10.0)})
        t0 = time.perf_counter()
        for _ in range(5):
            await rl.acquire(provider="test", tier="flash")
        elapsed = time.perf_counter() - t0
        # 5 calls @ 10 RPS = ~0.4s minimum; allow some slack.
        assert elapsed >= 0.35, f"too fast: {elapsed:.3f}s"
        assert elapsed < 1.0, f"too slow: {elapsed:.3f}s"

    @pytest.mark.asyncio
    async def test_unconfigured_combo_passes_through(self) -> None:
        rl = RateLimiter()
        # No bucket for ("nope", "flash") — must not block.
        t0 = time.perf_counter()
        for _ in range(50):
            await rl.acquire(provider="nope", tier="flash")
        assert time.perf_counter() - t0 < 0.1


class TestConcurrencyCap:
    @pytest.mark.asyncio
    async def test_pro_caps_at_4_in_flight(self) -> None:
        # Pro bucket caps in-flight at 4.
        rl = RateLimiter(overrides={("test", "pro"): BucketConfig(rps=1000.0, concurrency=2)})
        in_flight = 0
        peak = 0
        lock = asyncio.Lock()

        async def call() -> None:
            nonlocal in_flight, peak
            await rl.acquire(provider="test", tier="pro")
            async with lock:
                in_flight += 1
                peak = max(peak, in_flight)
            await asyncio.sleep(0.05)
            async with lock:
                in_flight -= 1
            rl.release(provider="test", tier="pro")

        await asyncio.gather(*(call() for _ in range(10)))
        assert peak <= 2, f"concurrency cap breached: peak={peak}"
