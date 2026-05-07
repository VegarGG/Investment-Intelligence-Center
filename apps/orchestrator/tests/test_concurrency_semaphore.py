"""Workflow 06 §6.4 + acceptance criterion 4 — Pro-tier slot cap of 4."""

from __future__ import annotations

import asyncio

import pytest
from orchestrator.execute.concurrency import (
    InMemorySemaphoreBackend,
    acquire_pro_slot,
)


class TestSemaphore:
    @pytest.mark.asyncio
    async def test_acquires_slot(self) -> None:
        backend = InMemorySemaphoreBackend()
        async with acquire_pro_slot(backend, capacity=4) as slot:
            assert 1 <= slot <= 4

    @pytest.mark.asyncio
    async def test_release_on_exit(self) -> None:
        backend = InMemorySemaphoreBackend()
        async with acquire_pro_slot(backend, capacity=2) as first:
            pass
        # After release we can re-acquire the same slot.
        async with acquire_pro_slot(backend, capacity=2) as second:
            assert second == first

    @pytest.mark.asyncio
    async def test_concurrency_cap_observed_under_contention(self) -> None:
        """Spawn 10 concurrent slot-holders against capacity=4 — peak in-flight
        must never exceed 4."""
        backend = InMemorySemaphoreBackend()
        in_flight = 0
        peak = 0
        lock = asyncio.Lock()

        async def worker() -> None:
            nonlocal in_flight, peak
            async with acquire_pro_slot(backend, capacity=4):
                async with lock:
                    in_flight += 1
                    peak = max(peak, in_flight)
                await asyncio.sleep(0.05)
                async with lock:
                    in_flight -= 1

        await asyncio.gather(*(worker() for _ in range(10)))
        assert peak == 4

    @pytest.mark.asyncio
    async def test_timeout_raises(self) -> None:
        backend = InMemorySemaphoreBackend()
        # Hold all slots, then try to acquire one more with tight timeout.
        held = await _hold_all(backend, capacity=2)
        with pytest.raises(asyncio.TimeoutError):
            async with acquire_pro_slot(backend, capacity=2, timeout_s=0.1, poll_interval_s=0.01):
                pass
        # Release the held slots so we don't leak (test cleanup).
        for cm in held:
            await cm.__aexit__(None, None, None)


async def _hold_all(backend: InMemorySemaphoreBackend, capacity: int) -> list:
    held = []
    for _ in range(capacity):
        cm = acquire_pro_slot(backend, capacity=capacity)
        await cm.__aenter__()
        held.append(cm)
    return held
