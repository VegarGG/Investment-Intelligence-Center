"""Workflow 06 §6.2 + acceptance criterion 1 — DAG A end-to-end with mocked agents."""

from __future__ import annotations

import pytest
from orchestrator.execute.runner import execute
from orchestrator.execute.sla import with_sla_timeout
from orchestrator.plan.agent_client import StubAgentClient
from orchestrator.plan.morning_brief import build_dag, make_initial_state
from orchestrator.plan.personas import list_persona_slugs


def _stub_responses() -> dict[str, dict]:
    """Build stub responses sourced from the v2.5 T0.2 persona registry."""
    base: dict[str, dict] = {
        "agent_intelligence": {
            "macro_regime": "rate_cut",
            "events": [{"id": "evt-1", "headline": "Fed cuts 25bp"}],
        },
        "agent_fundamental": {
            "advices": [{"id": "01HX8E5G7M0000000000000001", "agent": "fundamental"}]
        },
        "agent_quant": {"advices": [{"id": "01HX8E5G7M0000000000000002", "agent": "quant"}]},
        "agent_secretary": {"markdown": "## brief", "ok": True},
    }
    slugs = list_persona_slugs(force_reload=True)
    # First persona returns one advice; others return [] so fan-out math stays predictable.
    for i, slug in enumerate(slugs):
        if i == 0:
            base[f"agent_persona.{slug}"] = {
                "advices": [{"id": "01HX8E5G7M0000000000000003", "agent": f"persona.{slug}"}]
            }
        else:
            base[f"agent_persona.{slug}"] = {"advices": []}
    return base


class TestMorningBriefDag:
    @pytest.mark.asyncio
    async def test_runs_end_to_end(self) -> None:
        client = StubAgentClient(responses=_stub_responses())
        graph = build_dag(client)
        state = make_initial_state()
        result = await execute(graph, state, trace_id=state.trace_id, sla_runner=with_sla_timeout)
        assert result.ok
        # intel + fundamental + quant + N personas + secretary_brief + notify
        n_personas = len(list_persona_slugs(force_reload=True))
        assert len(result.nodes) == 5 + n_personas

    @pytest.mark.asyncio
    async def test_visits_intel_synth_first(self) -> None:
        client = StubAgentClient(responses=_stub_responses())
        graph = build_dag(client)
        state = make_initial_state()
        await execute(graph, state, trace_id=state.trace_id, sla_runner=with_sla_timeout)
        assert client.calls[0][0] == "agent_intelligence"

    @pytest.mark.asyncio
    async def test_personas_fan_out_in_parallel_after_intel(self) -> None:
        """Personas + fundamental + quant should all run after intel.synth completes."""
        client = StubAgentClient(responses=_stub_responses())
        graph = build_dag(client)
        state = make_initial_state()
        result = await execute(graph, state, trace_id=state.trace_id, sla_runner=with_sla_timeout)
        # Brief node runs after all advisors.
        intel = result.by_name("n_intel_synth")
        brief = result.by_name("n_secretary_brief")
        assert intel is not None and brief is not None
        for slug in list_persona_slugs(force_reload=True):
            persona = result.by_name(f"n_persona_{slug}")
            assert persona is not None
            assert persona.started_at >= intel.finished_at - 0.01  # allow tiny clock noise
            assert persona.finished_at <= brief.started_at + 0.01

    @pytest.mark.asyncio
    async def test_macro_regime_propagates_from_digest_to_quant(self) -> None:
        client = StubAgentClient(responses=_stub_responses())
        graph = build_dag(client)
        state = make_initial_state()
        await execute(graph, state, trace_id=state.trace_id, sla_runner=with_sla_timeout)
        # Find the call to agent_quant — payload should have regime=rate_cut.
        quant_call = next((p for a, p in client.calls if a == "agent_quant"), None)
        assert quant_call is not None
        assert quant_call["regime"] == "rate_cut"

    @pytest.mark.asyncio
    async def test_advices_collected_into_brief_node(self) -> None:
        client = StubAgentClient(responses=_stub_responses())
        graph = build_dag(client)
        state = make_initial_state()
        await execute(graph, state, trace_id=state.trace_id, sla_runner=with_sla_timeout)
        secretary_call = next(
            (
                p
                for a, p in client.calls
                if a == "agent_secretary" and p.get("action") == "compose_brief"
            ),
            None,
        )
        assert secretary_call is not None
        # 1 fundamental + 1 quant + 1 persona.rogers = 3 advices
        assert len(secretary_call["advices"]) == 3

    @pytest.mark.asyncio
    async def test_trace_id_propagates_to_every_call(self) -> None:
        client = StubAgentClient(responses=_stub_responses())
        graph = build_dag(client)
        state = make_initial_state(trace_id="01HX8E5G7M0000000000000099")
        await execute(graph, state, trace_id=state.trace_id, sla_runner=with_sla_timeout)
        for _agent, payload in client.calls:
            assert payload.get("trace_id") == "01HX8E5G7M0000000000000099"
