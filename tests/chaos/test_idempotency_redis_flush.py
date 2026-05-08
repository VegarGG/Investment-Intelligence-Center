"""v2.5 burn-in — dedupe survives a Redis flush.

Premise: a Redis restart wipes ephemeral state. The idempotency cache is
ephemeral by design (24h TTL); the question is whether a restart leads to
duplicate DAG fires for the same logical trigger.

Acceptance: after a flush, the next fire is treated as fresh (claim
succeeds). The system never duplicates side-effects because side-effects
are themselves idempotent at the data layer (advice ledger hash chain;
NATS deduplication via JetStream).
"""

from __future__ import annotations

import pytest
from orchestrator.state.idempotency import (
    InMemoryIdempotencyStore,
    claim_or_skip,
)


@pytest.mark.asyncio
async def test_dedupe_within_window():
    """Two fires inside the window: first claims, second skips."""
    store = InMemoryIdempotencyStore()
    a = await claim_or_skip(
        store, dag_id="morning_brief", trigger_kind="cron", trigger_at="2026-05-08T13:30"
    )
    b = await claim_or_skip(
        store, dag_id="morning_brief", trigger_kind="cron", trigger_at="2026-05-08T13:30"
    )
    assert a is True
    assert b is False


@pytest.mark.asyncio
async def test_dedupe_resets_on_redis_flush():
    """Simulate a flush by replacing the store. Next claim succeeds."""
    store = InMemoryIdempotencyStore()
    await claim_or_skip(
        store, dag_id="morning_brief", trigger_kind="cron", trigger_at="2026-05-08T13:30"
    )

    # FLUSHALL equivalent: drop the in-memory backing.
    flushed = InMemoryIdempotencyStore()

    after = await claim_or_skip(
        flushed, dag_id="morning_brief", trigger_kind="cron", trigger_at="2026-05-08T13:30"
    )
    assert after is True


@pytest.mark.asyncio
async def test_force_bypass_still_returns_true():
    """`force=True` bypasses the cache regardless of state."""
    store = InMemoryIdempotencyStore()
    await claim_or_skip(
        store, dag_id="morning_brief", trigger_kind="cron", trigger_at="2026-05-08T13:30"
    )
    bypass = await claim_or_skip(
        store,
        dag_id="morning_brief",
        trigger_kind="cron",
        trigger_at="2026-05-08T13:30",
        force=True,
    )
    assert bypass is True
