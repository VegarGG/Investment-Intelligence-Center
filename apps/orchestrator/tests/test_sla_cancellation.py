"""Workflow 06 §6.3 + acceptance criterion 3 — SLA hard timeouts produce SLAStubs."""

from __future__ import annotations

import asyncio

import pytest
from orchestrator.execute.runner import Node, StateGraph, execute
from orchestrator.execute.sla import SLA_TABLE, SLAStub, lookup_sla, with_sla_timeout


class TestSlaTable:
    def test_persona_slug_maps_to_persona_daily(self) -> None:
        assert lookup_sla("persona.rogers.daily") == SLA_TABLE["persona.daily"]

    def test_persona_weekly_slug_maps_to_persona_weekly(self) -> None:
        assert lookup_sla("persona.soros.weekly") == SLA_TABLE["persona.weekly"]

    def test_unknown_node_returns_none(self) -> None:
        assert lookup_sla("custom.node") is None

    def test_intel_synth_table_value(self) -> None:
        assert SLA_TABLE["intel.synth"] == (60.0, 120.0)


class TestSlaWrapper:
    @pytest.mark.asyncio
    async def test_fast_node_returns_normally(self) -> None:
        async def fast(_state: dict) -> str:
            return "ok"

        node = Node(name="x", fn=fast, hard_timeout_s=1.0)
        ok, output, error, timed_out = await with_sla_timeout(node, {})
        assert ok and output == "ok" and error is None and not timed_out

    @pytest.mark.asyncio
    async def test_slow_node_hits_hard_timeout_returns_stub(self) -> None:
        async def slow(_state: dict) -> str:
            await asyncio.sleep(1.0)
            return "never"

        node = Node(name="slow", fn=slow, soft_timeout_s=0.05, hard_timeout_s=0.1)
        ok, output, error, timed_out = await with_sla_timeout(node, {})
        assert not ok
        assert isinstance(output, SLAStub)
        assert output.node_name == "slow"
        assert timed_out
        assert error is not None and "0.1s" in error

    @pytest.mark.asyncio
    async def test_alert_callback_fires_on_hard_timeout(self) -> None:
        alerts: list[tuple[str, str]] = []

        async def alert_cb(name: str, msg: str) -> None:
            alerts.append((name, msg))

        async def slow(_state: dict) -> str:
            await asyncio.sleep(1.0)
            return "never"

        node = Node(name="slow", fn=slow, hard_timeout_s=0.05)
        await with_sla_timeout(node, {}, on_alert=alert_cb)
        assert len(alerts) == 1
        assert alerts[0][0] == "slow"

    @pytest.mark.asyncio
    async def test_node_exception_propagates_as_error(self) -> None:
        async def boom(_state: dict) -> str:
            raise RuntimeError("kaboom")

        node = Node(name="boom", fn=boom, hard_timeout_s=1.0)
        ok, output, error, timed_out = await with_sla_timeout(node, {})
        assert not ok
        assert output is None
        assert error == "kaboom"
        assert not timed_out

    @pytest.mark.asyncio
    async def test_dag_continues_after_sla_stub(self) -> None:
        """Acceptance: a node that times out doesn't stall the whole DAG —
        downstream nodes get the SLAStub in state and degrade."""
        graph: StateGraph[dict] = StateGraph("test_sla_dag")

        async def slow(_state: dict) -> str:
            await asyncio.sleep(0.5)
            return "slow_done"

        async def downstream(_state: dict) -> str:
            return "downstream_done"

        graph.add_node("slow", slow, hard_timeout_s=0.05)
        graph.add_node("downstream", downstream)
        graph.add_edge("slow", "downstream")
        graph.set_entry("slow")

        result = await execute(graph, {}, trace_id="t", sla_runner=with_sla_timeout)
        slow_result = result.by_name("slow")
        downstream_result = result.by_name("downstream")
        assert slow_result is not None and slow_result.timed_out
        assert downstream_result is not None and downstream_result.ok
