"""Routing matrix — workflow 03 §2 GROUND TRUTH (verbatim).

Every caller_id in the system maps to a CallerSpec here. Adding a new caller
elsewhere without registering here raises UnknownCallerId at runtime.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from llm_client.exceptions import UnknownCallerId
from llm_client.types import LlmTier

RuntimeSignals = Mapping[str, Any]
EscalateRule = Callable[[RuntimeSignals], bool]


@dataclass(frozen=True, slots=True)
class CallerSpec:
    default_tier: LlmTier
    escalate_when: EscalateRule | None = None
    cache_eligible: bool = False
    cache_ttl_seconds: int | None = None


def _always(_signals: RuntimeSignals) -> bool:
    return True


def _filing_over_200_pages(signals: RuntimeSignals) -> bool:
    return int(signals.get("filing_pages", 0)) > 200


def _regime_change(signals: RuntimeSignals) -> bool:
    return bool(signals.get("regime_change", False))


def _persona_weekly_deepdive(signals: RuntimeSignals) -> bool:
    return bool(signals.get("weekly_deepdive", False))


def _secretary_explain_deeply(signals: RuntimeSignals) -> bool:
    return bool(signals.get("explain_deeply", False)) or bool(
        signals.get("multi_step_question", False)
    )


# GROUND TRUTH — workflow 03 §2. Order matches the doc table.
MATRIX: dict[str, CallerSpec] = {
    "intel.crawler.translate": CallerSpec(
        default_tier="flash", cache_eligible=True, cache_ttl_seconds=24 * 3600
    ),
    "intel.sentiment.classify": CallerSpec(
        default_tier="flash", cache_eligible=True, cache_ttl_seconds=3600
    ),
    "intel.dedupe.embed": CallerSpec(
        default_tier="embed", cache_eligible=True, cache_ttl_seconds=None
    ),
    "intel.synth": CallerSpec(default_tier="pro", escalate_when=_always),
    "fund.filings.extract": CallerSpec(
        default_tier="flash",
        escalate_when=_filing_over_200_pages,
        cache_eligible=True,
        cache_ttl_seconds=7 * 24 * 3600,
    ),
    "fund.valuation": CallerSpec(default_tier="pro", escalate_when=_always),
    "fund.writer": CallerSpec(default_tier="pro", escalate_when=_always),
    "quant.writer": CallerSpec(default_tier="flash", escalate_when=_regime_change),
    "persona.daily": CallerSpec(default_tier="flash", escalate_when=_persona_weekly_deepdive),
    "persona.weekly": CallerSpec(default_tier="pro", escalate_when=_always),
    "backtest.narrate": CallerSpec(default_tier="flash"),
    "secretary.chat": CallerSpec(default_tier="flash", escalate_when=_secretary_explain_deeply),
    "secretary.brief.morning": CallerSpec(default_tier="pro", escalate_when=_always),
    "secretary.brief.midday": CallerSpec(default_tier="flash"),
    # D7.1 §H1.2 — always-LLM demo endpoint (POST /chat/echo) used by the
    # fresh-bringup wiring smoke. Flash so the smoke gate stays cheap.
    "secretary.echo": CallerSpec(default_tier="flash"),
    # P6.2 — secretary's natural-language planner. Pro on multi-step
    # questions; flash on single-RPC questions.
    "secretary.plan": CallerSpec(
        default_tier="flash", escalate_when=_secretary_explain_deeply
    ),
    "orchestrator.plan": CallerSpec(default_tier="pro", escalate_when=_always),
    # v2.5 N3.1 — Event-Triage Gate (LLM tie-break only when numeric scores
    # straddle the boundary). Flash by default; small token budget.
    "event_triage": CallerSpec(default_tier="flash"),
    # v2.5 N3.2 — persona team_plan synthesizer (consensus thesis rollup).
    "persona.team_plan": CallerSpec(default_tier="flash"),
    # v2.5 N3.3 — Investment Board sub-agents.
    "board.bull": CallerSpec(default_tier="flash"),
    "board.bear": CallerSpec(default_tier="flash"),
    "board.risk_aggressive": CallerSpec(default_tier="flash"),
    "board.risk_conservative": CallerSpec(default_tier="flash"),
    "board.risk_neutral": CallerSpec(default_tier="flash"),
    # The Chair is the only Pro-tier call per board decision (≤ $0.05 budget).
    "board.chair": CallerSpec(default_tier="pro", escalate_when=_always),
}


def lookup(caller_id: str) -> CallerSpec:
    """Strict lookup — typos and forgotten registrations fail loudly."""
    # Persona slugs collapse to a single registry entry: persona.<slug>.daily/weekly
    if caller_id.startswith("persona.") and caller_id.endswith(".daily"):
        return MATRIX["persona.daily"]
    if caller_id.startswith("persona.") and caller_id.endswith(".weekly"):
        return MATRIX["persona.weekly"]
    spec = MATRIX.get(caller_id)
    if spec is None:
        raise UnknownCallerId(f"caller_id '{caller_id}' is not registered in the routing matrix")
    return spec


def resolve_tier(caller_id: str, signals: RuntimeSignals) -> LlmTier:
    """Apply the caller's default + escalate rule to pick the actual tier."""
    spec = lookup(caller_id)
    if spec.escalate_when is not None and spec.escalate_when(signals):
        return "pro"
    return spec.default_tier
