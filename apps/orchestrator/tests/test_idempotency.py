"""Workflow 06 §6.6 + acceptance criterion 5 — idempotency cache + force bypass."""

from __future__ import annotations

import pytest
from orchestrator.state.idempotency import (
    InMemoryIdempotencyStore,
    claim_or_skip,
    idempotency_key,
    with_idempotency,
)


class TestClaimOrSkip:
    @pytest.mark.asyncio
    async def test_first_claim_proceeds(self) -> None:
        store = InMemoryIdempotencyStore()
        ok = await claim_or_skip(
            store,
            dag_id="morning_brief",
            trigger_kind="cron",
            trigger_at="2026-05-07T06:30",
        )
        assert ok is True

    @pytest.mark.asyncio
    async def test_repeat_claim_within_window_blocks(self) -> None:
        store = InMemoryIdempotencyStore()
        await claim_or_skip(
            store,
            dag_id="morning_brief",
            trigger_kind="cron",
            trigger_at="2026-05-07T06:30",
        )
        ok = await claim_or_skip(
            store,
            dag_id="morning_brief",
            trigger_kind="cron",
            trigger_at="2026-05-07T06:30",
        )
        assert ok is False

    @pytest.mark.asyncio
    async def test_force_bypasses_cache(self) -> None:
        store = InMemoryIdempotencyStore()
        await claim_or_skip(
            store,
            dag_id="morning_brief",
            trigger_kind="cron",
            trigger_at="2026-05-07T06:30",
        )
        ok = await claim_or_skip(
            store,
            dag_id="morning_brief",
            trigger_kind="cron",
            trigger_at="2026-05-07T06:30",
            force=True,
        )
        assert ok is True

    @pytest.mark.asyncio
    async def test_different_trigger_at_proceeds(self) -> None:
        store = InMemoryIdempotencyStore()
        await claim_or_skip(
            store,
            dag_id="morning_brief",
            trigger_kind="cron",
            trigger_at="2026-05-07T06:30",
        )
        ok = await claim_or_skip(
            store,
            dag_id="morning_brief",
            trigger_kind="cron",
            trigger_at="2026-05-08T06:30",
        )
        assert ok is True


class TestWithIdempotency:
    @pytest.mark.asyncio
    async def test_runs_when_first(self) -> None:
        store = InMemoryIdempotencyStore()
        ran = []

        async def runner() -> str:
            ran.append("yes")
            return "ok"

        out = await with_idempotency(
            store,
            dag_id="d",
            trigger_kind="cron",
            trigger_at="2026-05-07T06:30",
            force=False,
            runner=runner,
        )
        assert out == "ok"
        assert ran == ["yes"]

    @pytest.mark.asyncio
    async def test_skips_when_repeat(self) -> None:
        store = InMemoryIdempotencyStore()
        ran = []

        async def runner() -> str:
            ran.append("yes")
            return "ok"

        await with_idempotency(
            store,
            dag_id="d",
            trigger_kind="cron",
            trigger_at="2026-05-07T06:30",
            force=False,
            runner=runner,
        )
        out = await with_idempotency(
            store,
            dag_id="d",
            trigger_kind="cron",
            trigger_at="2026-05-07T06:30",
            force=False,
            runner=runner,
            on_skip="skipped",
        )
        assert out == "skipped"
        assert ran == ["yes"]  # second run was a no-op


class TestKeyShape:
    def test_key_includes_all_axes(self) -> None:
        key = idempotency_key("morning_brief", "cron", "2026-05-07T06:30")
        assert key == "orch:idem:morning_brief:cron:2026-05-07T06:30"
