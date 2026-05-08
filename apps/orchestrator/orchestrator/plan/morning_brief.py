"""DAG A — Morning Brief (workflow 06 §2.2 + §6.2).

Topology:
  intel.synth → fan-out (fundamental, quant, persona x N) → secretary brief
  → notifier.

trace_id is generated at trigger time and threaded through every node's
state so observability can stitch the run end-to-end.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import ulid

from ..execute.runner import StateGraph
from ..execute.sla import SLA_TABLE
from .agent_client import AgentClient
from .personas import list_persona_slugs


def _default_persona_slugs() -> tuple[str, ...]:
    """Reads `docs/prompts/persona/*.yaml`. Drift across YAML, code, and the
    URL map is prevented by the v2.5 T0.2 source-of-truth helper."""
    return list_persona_slugs()


@dataclass(slots=True)
class MorningBriefState:
    trace_id: str
    persona_slugs: tuple[str, ...] = field(default_factory=_default_persona_slugs)
    digest: dict[str, Any] | None = None
    macro_regime: str = "unknown"
    advices: list[dict[str, Any]] = field(default_factory=list)
    brief_md: str | None = None
    notify_result: dict[str, Any] | None = None


def make_initial_state(
    *,
    trace_id: str | None = None,
    persona_slugs: tuple[str, ...] | None = None,
) -> MorningBriefState:
    return MorningBriefState(
        trace_id=trace_id or str(ulid.ULID()),
        persona_slugs=persona_slugs if persona_slugs is not None else _default_persona_slugs(),
    )


def build_dag(
    client: AgentClient,
) -> StateGraph[MorningBriefState]:
    """Build the morning-brief DAG bound to the supplied agent client."""

    g: StateGraph[MorningBriefState] = StateGraph("morning_brief")

    # ---- n_intel_synth -----------------------------------------------------
    async def n_intel_synth(state: MorningBriefState) -> dict[str, Any]:
        digest = await client.call(
            "agent_intelligence",
            {"action": "synth", "trace_id": state.trace_id},
        )
        state.digest = digest
        state.macro_regime = digest.get("macro_regime", "unknown")
        return {"node": "n_intel_synth", "macro_regime": state.macro_regime}

    intel_soft, intel_hard = SLA_TABLE["intel.synth"]
    g.add_node(
        "n_intel_synth",
        n_intel_synth,
        soft_timeout_s=intel_soft,
        hard_timeout_s=intel_hard,
    )

    # ---- fundamental + quant ---------------------------------------------
    async def n_fundamental(state: MorningBriefState) -> dict[str, Any]:
        result = await client.call(
            "agent_fundamental",
            {"digest": state.digest, "trace_id": state.trace_id},
        )
        for advice in result.get("advices", []):
            state.advices.append(advice)
        return {"node": "n_fundamental", "advices_n": len(result.get("advices", []))}

    fund_soft, fund_hard = SLA_TABLE["fundamental.run"]
    g.add_node(
        "n_fundamental",
        n_fundamental,
        soft_timeout_s=fund_soft,
        hard_timeout_s=fund_hard,
    )

    async def n_quant(state: MorningBriefState) -> dict[str, Any]:
        result = await client.call(
            "agent_quant",
            {"regime": state.macro_regime, "trace_id": state.trace_id},
        )
        for advice in result.get("advices", []):
            state.advices.append(advice)
        return {"node": "n_quant", "advices_n": len(result.get("advices", []))}

    quant_soft, quant_hard = SLA_TABLE["quant.run"]
    g.add_node(
        "n_quant",
        n_quant,
        soft_timeout_s=quant_soft,
        hard_timeout_s=quant_hard,
    )

    # ---- persona fan-out (one node per slug) ------------------------------
    persona_soft, persona_hard = SLA_TABLE["persona.daily"]
    persona_slugs = _default_persona_slugs()
    for slug in persona_slugs:
        node_name = f"n_persona_{slug}"

        def _make_persona_node(slug_capture: str) -> Any:
            async def _node(state: MorningBriefState) -> dict[str, Any]:
                result = await client.call(
                    f"agent_persona.{slug_capture}",
                    {"digest": state.digest, "trace_id": state.trace_id},
                )
                for advice in result.get("advices", []):
                    state.advices.append(advice)
                return {
                    "node": f"n_persona_{slug_capture}",
                    "advices_n": len(result.get("advices", [])),
                }

            return _node

        g.add_node(
            node_name,
            _make_persona_node(slug),
            soft_timeout_s=persona_soft,
            hard_timeout_s=persona_hard,
        )

    # ---- secretary brief --------------------------------------------------
    async def n_secretary_brief(state: MorningBriefState) -> dict[str, Any]:
        result = await client.call(
            "agent_secretary",
            {
                "action": "compose_brief",
                "advices": state.advices,
                "digest": state.digest,
                "macro_regime": state.macro_regime,
                "trace_id": state.trace_id,
            },
        )
        state.brief_md = result.get("markdown")
        return {"node": "n_secretary_brief", "char_count": len(state.brief_md or "")}

    sec_soft, sec_hard = SLA_TABLE["secretary.compose_brief"]
    g.add_node(
        "n_secretary_brief",
        n_secretary_brief,
        soft_timeout_s=sec_soft,
        hard_timeout_s=sec_hard,
    )

    # ---- deliver (v2.5 T1.4: never-fail; redelivery handled by secretary) ----
    async def n_deliver_brief(state: MorningBriefState) -> dict[str, Any]:
        """Plan §T1.4b — failures here MUST NOT fail the DAG.

        The secretary agent owns redelivery (it wraps the router with
        `notify_with_redelivery`); this node just records what happened
        so observability surfaces deferred messages.
        """
        try:
            result = await client.call(
                "agent_secretary",
                {"action": "notify", "markdown": state.brief_md, "trace_id": state.trace_id},
            )
        except Exception as exc:
            state.notify_result = {"ok": False, "deferred": True, "error": str(exc)}
            return {"node": "n_deliver_brief", "ok": True, "deferred": True}
        state.notify_result = result
        return {
            "node": "n_deliver_brief",
            "ok": True,
            "deferred": bool(result.get("deferred", False)),
        }

    g.add_node("n_deliver_brief", n_deliver_brief)

    # ---- edges ------------------------------------------------------------
    g.set_entry("n_intel_synth")
    g.add_edge("n_intel_synth", "n_fundamental")
    g.add_edge("n_intel_synth", "n_quant")
    for slug in persona_slugs:
        g.add_edge("n_intel_synth", f"n_persona_{slug}")
    g.add_edge("n_fundamental", "n_secretary_brief")
    g.add_edge("n_quant", "n_secretary_brief")
    for slug in persona_slugs:
        g.add_edge(f"n_persona_{slug}", "n_secretary_brief")
    g.add_edge("n_secretary_brief", "n_deliver_brief")

    return g
