"""v2.5 T1.6 chaos acceptance — kill one agent, brief still completes.

We exercise the morning_brief DAG with a stub client whose calls to a
chosen agent always raise. Wrapped under a CircuitBreakerRegistry, those
failures should open the breaker after `failure_threshold` retries and
the remaining nodes should still produce an output.
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
    """AgentClient stub that always raises for one chosen target."""

    def __init__(self, *, broken_agent: str) -> None:
        self.broken_agent = broken_agent
        self.breaker = CircuitBreakerRegistry(failure_threshold=2, cooldown_s=60)
        self.calls: list[tuple[str, dict]] = []
        self.intel_macro_regime = "rate_cut"

    async def call(self, agent, payload):
        self.calls.append((agent, payload))

        async def _send():
            if agent == self.broken_agent:
                raise RuntimeError(f"chaos: {agent} is offline")
            return self._respond(agent, payload)

        try:
            return await self.breaker.call(agent, _send)
        except BreakerOpen:
            return _breaker_open_response(agent)

    def _respond(self, agent, payload):
        if agent == "agent_intelligence":
            return {
                "macro_regime": self.intel_macro_regime,
                "events": [{"id": "evt-1", "headline": "fed event"}],
            }
        if agent == "agent_fundamental":
            return {"advices": []}
        if agent == "agent_quant":
            return {"advices": []}
        if agent.startswith("agent_persona."):
            return {"advices": []}
        if agent == "agent_secretary":
            if payload.get("action") == "compose_brief":
                return {"markdown": "## brief", "ok": True}
            return {"ok": True}
        return {"ok": True}


@pytest.mark.asyncio
async def test_morning_brief_completes_when_one_persona_is_offline():
    """Chaos: one persona container is offline; brief still ships."""
    slugs = list_persona_slugs(force_reload=True)
    # Pick the first persona slug as the broken one.
    broken = f"agent_persona.{slugs[0]}"
    client = _ChaosClient(broken_agent=broken)

    graph = build_dag(client)
    state = make_initial_state()
    result = await execute(graph, state, trace_id=state.trace_id, sla_runner=with_sla_timeout)

    # The DAG completes (the secretary brief node ran).
    brief = result.by_name("n_secretary_brief")
    assert brief is not None
    # The broken persona node failed but the breaker degraded the call.
    broken_node = result.by_name(f"n_persona_{slugs[0]}")
    assert broken_node is not None
    # Other personas got through.
    for slug in slugs[1:]:
        node = result.by_name(f"n_persona_{slug}")
        assert node is not None and node.ok


@pytest.mark.asyncio
async def test_breaker_opens_after_repeated_failures():
    """First two failures raise; subsequent calls short-circuit to degraded payload."""
    client = _ChaosClient(broken_agent="agent_quant")

    # First two failures bubble up.
    with pytest.raises(RuntimeError):
        await client.call("agent_quant", {})
    with pytest.raises(RuntimeError):
        await client.call("agent_quant", {})

    # Breaker now open — call short-circuits.
    out3 = await client.call("agent_quant", {})
    assert out3.get("_breaker_open") is True
    assert out3.get("advices") == []
