"""v2.5 burn-in — kill an agent, morning brief still completes.

Re-runs the orchestrator-level chaos test from a top-level path so the
burn-in script can sweep the whole `tests/chaos/` directory in one
invocation.
"""

from __future__ import annotations

import pytest
from orchestrator.execute.runner import execute
from orchestrator.execute.sla import with_sla_timeout
from orchestrator.plan.agent_client import AgentClient, _breaker_open_response
from orchestrator.plan.breaker import BreakerOpen, CircuitBreakerRegistry
from orchestrator.plan.morning_brief import build_dag, make_initial_state
from orchestrator.plan.personas import list_persona_slugs


class _ChaosClient(AgentClient):
    def __init__(self, *, broken_agent: str) -> None:
        self.broken_agent = broken_agent
        self.breaker = CircuitBreakerRegistry(failure_threshold=2, cooldown_s=60)
        self.calls: list[tuple[str, dict]] = []

    async def call(self, agent, payload):
        self.calls.append((agent, payload))

        async def _send():
            if agent == self.broken_agent:
                raise RuntimeError(f"{agent} offline")
            return self._respond(agent, payload)

        try:
            return await self.breaker.call(agent, _send)
        except BreakerOpen:
            return _breaker_open_response(agent)

    def _respond(self, agent, payload):
        if agent == "agent_intelligence":
            return {"macro_regime": "rate_cut", "events": [{"id": "evt-1", "headline": "x"}]}
        if agent.startswith("agent_persona.") or agent in {"agent_fundamental", "agent_quant"}:
            return {"advices": []}
        if agent == "agent_secretary":
            return {"markdown": "## brief", "ok": True}
        return {"ok": True}


@pytest.mark.asyncio
async def test_morning_brief_completes_when_quant_offline():
    client = _ChaosClient(broken_agent="agent_quant")
    graph = build_dag(client)
    state = make_initial_state()
    result = await execute(graph, state, trace_id=state.trace_id, sla_runner=with_sla_timeout)

    # The deliver node was renamed to n_deliver_brief in v2.5 T1.4 — it must
    # complete (never raise) even when an upstream node is degraded.
    deliver = result.by_name("n_deliver_brief")
    assert deliver is not None


@pytest.mark.asyncio
async def test_morning_brief_completes_when_one_persona_offline():
    slugs = list_persona_slugs(force_reload=True)
    broken = f"agent_persona.{slugs[0]}"
    client = _ChaosClient(broken_agent=broken)
    graph = build_dag(client)
    state = make_initial_state()
    result = await execute(graph, state, trace_id=state.trace_id, sla_runner=with_sla_timeout)
    assert result.by_name("n_deliver_brief") is not None
