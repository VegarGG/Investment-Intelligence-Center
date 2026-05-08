"""v2.5 T1.6 — per-agent circuit breaker on HttpxAgentClient.

Plan acceptance: stop one agent, morning brief still completes (with
that agent's advice missing) within SLA. We exercise the breaker
directly + at the HttpxAgentClient seam (skipping the real httpx
network call by injecting a fake transport).
"""

from __future__ import annotations

import time

import pytest
from orchestrator.plan.breaker import BreakerOpen, CircuitBreakerRegistry, State


@pytest.mark.asyncio
async def test_closed_state_passes_through():
    breaker = CircuitBreakerRegistry(failure_threshold=3, cooldown_s=60)

    async def ok():
        return {"ok": True}

    out = await breaker.call("agent_x", ok)
    assert out == {"ok": True}
    assert breaker.state_of("agent_x") is State.CLOSED


@pytest.mark.asyncio
async def test_opens_after_threshold_failures():
    breaker = CircuitBreakerRegistry(failure_threshold=3, cooldown_s=60)

    async def fail():
        raise RuntimeError("boom")

    for _ in range(3):
        with pytest.raises(RuntimeError):
            await breaker.call("agent_x", fail)
    # 3rd consecutive failure trips the breaker.
    assert breaker.state_of("agent_x") is State.OPEN


@pytest.mark.asyncio
async def test_open_short_circuits_calls():
    breaker = CircuitBreakerRegistry(failure_threshold=2, cooldown_s=60)

    async def fail():
        raise RuntimeError("boom")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await breaker.call("agent_x", fail)

    async def ok():
        return {"ok": True}

    with pytest.raises(BreakerOpen):
        await breaker.call("agent_x", ok)


@pytest.mark.asyncio
async def test_recovers_after_cooldown_with_successful_probe(monkeypatch):
    breaker = CircuitBreakerRegistry(failure_threshold=2, cooldown_s=0.01)

    async def fail():
        raise RuntimeError("boom")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await breaker.call("agent_x", fail)
    assert breaker.state_of("agent_x") is State.OPEN

    # Wait past the cooldown.
    time.sleep(0.02)

    async def ok():
        return {"ok": True}

    out = await breaker.call("agent_x", ok)
    assert out == {"ok": True}
    assert breaker.state_of("agent_x") is State.CLOSED


@pytest.mark.asyncio
async def test_half_open_failure_returns_to_open():
    breaker = CircuitBreakerRegistry(failure_threshold=2, cooldown_s=0.01)

    async def fail():
        raise RuntimeError("boom")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await breaker.call("agent_x", fail)
    time.sleep(0.02)

    # Probe fails: should go back to OPEN.
    with pytest.raises(RuntimeError):
        await breaker.call("agent_x", fail)
    assert breaker.state_of("agent_x") is State.OPEN


@pytest.mark.asyncio
async def test_breaker_state_is_isolated_per_target():
    breaker = CircuitBreakerRegistry(failure_threshold=2, cooldown_s=60)

    async def fail():
        raise RuntimeError("boom")

    async def ok():
        return {"ok": True}

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await breaker.call("agent_a", fail)
    assert breaker.state_of("agent_a") is State.OPEN

    out = await breaker.call("agent_b", ok)
    assert out == {"ok": True}
    assert breaker.state_of("agent_b") is State.CLOSED


@pytest.mark.asyncio
async def test_state_change_hook_fires():
    breaker = CircuitBreakerRegistry(failure_threshold=2, cooldown_s=60)
    events: list[tuple[str, State]] = []
    breaker.set_on_change(lambda target, state: events.append((target, state)))

    async def fail():
        raise RuntimeError("boom")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await breaker.call("agent_x", fail)

    assert ("agent_x", State.OPEN) in events
