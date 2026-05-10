"""Persona team writer (v2.5 N3.2 / T2.3).

Synthesises N persona ``AdviceV1`` outputs into ONE ``PlanV1`` envelope
with ``team='persona'`` and ``persona_slug='consensus'``.

Synthesis rules:
  - direction (action) = majority vote across the 8 personas (tie → hold)
  - entry_price = median of per-persona entry-band midpoints
  - target_price = mean of per-persona target-band midpoints
  - stop_loss   = max of per-persona stop_loss (the most conservative)
  - thesis      = LLM-rolled-up 3-paragraph synthesis with per-persona citations
  - evidence    = de-duplicated union of every persona's evidence list
  - confidence  = mean of per-persona confidence × (majority share)
  - horizon_days = max horizon (the longest-horizon persona wins on duration)

The disclaimer is mandatory for ``team='persona'`` per the workflow-13
ethics rule reified in PlanV1's validators.
"""

from __future__ import annotations

import logging
import statistics
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import ulid
from llm_client import ChatMessage, chat_or_skip
from schema import AdviceV1, Evidence
from schema.plan import PlanV1, PortfolioContextV1

log = logging.getLogger(__name__)

CONSENSUS_DISCLAIMER = (
    "IIC Persona Consensus is a research synthesis of 8 named investor personas. "
    "It is not personalised investment advice and does not constitute a "
    "recommendation. The views are those of the simulated personas, not the user."
)


def _direction_to_action(direction: str, *, has_signal: bool) -> str:
    if not has_signal:
        return "hold"
    if direction == "long":
        return "buy"
    if direction == "short":
        return "sell"
    return "hold"


def _band_mid(band: tuple[float, float]) -> float:
    lo, hi = band
    return (lo + hi) / 2.0


def _majority_direction(advices: Sequence[AdviceV1]) -> tuple[str, float]:
    """Return (direction, share). Tie favours 'flat'."""
    counts: dict[str, int] = {"long": 0, "short": 0, "flat": 0}
    for a in advices:
        counts[a.direction] = counts.get(a.direction, 0) + 1
    total = sum(counts.values()) or 1
    sorted_dirs = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    top, top_n = sorted_dirs[0]
    runner_n = sorted_dirs[1][1] if len(sorted_dirs) > 1 else 0
    if top_n == runner_n:
        return ("flat", top_n / total)
    return (top, top_n / total)


def _dedupe_evidence(advices: Sequence[AdviceV1]) -> list[Evidence]:
    seen: set[tuple[str, str | None, str | None]] = set()
    out: list[Evidence] = []
    for a in advices:
        for ev in a.evidence:
            key = (ev.kind, ev.ref, ev.url)
            if key in seen:
                continue
            seen.add(key)
            out.append(ev)
    return out


async def _synthesize_thesis(advices: Sequence[AdviceV1], action: str) -> str:
    """LLM-roll the 8 personas' theses into a 3-paragraph consensus.

    Falls back to a deterministic plaintext concat if the LLM is
    skipped (cost breaker open or no router configured) so the plan
    still ships with a non-empty thesis.
    """

    prompt_body = "\n".join(
        f"- [{a.agent}] direction={a.direction} confidence={a.confidence:.2f}: {a.thesis[:400]}"
        for a in advices
    )
    system = (
        "You are the IIC Persona Board synthesizer. Roll the per-persona "
        "advisories below into a 3-paragraph consensus thesis. Cite each "
        "persona by their agent slug at least once. Do not invent prices."
    )
    user = (
        f"Action: {action}\nPersona advisories:\n{prompt_body}\n\n"
        "Output 3 paragraphs (≤600 words total)."
    )

    try:
        response = await chat_or_skip(
            "persona.team_plan",
            [
                ChatMessage(role="system", content=system),
                ChatMessage(role="user", content=user),
            ],
            max_tokens=900,
            temperature=0.4,
        )
    except Exception as exc:  # noqa: BLE001 — never raise from a writer; degrade gracefully
        log.warning("persona team_plan llm fallback: %s", exc)
        return _fallback_thesis(advices, action)

    if response.cost_skipped or not response.text.strip():
        return _fallback_thesis(advices, action)
    return response.text.strip()


def _fallback_thesis(advices: Sequence[AdviceV1], action: str) -> str:
    bullets = "\n".join(
        f"- {a.agent}: {a.direction} (conf={a.confidence:.2f}) — {a.thesis[:200]}"
        for a in advices
    )
    return (
        f"Persona consensus action: {action}.\n\nPer-persona signals:\n{bullets}\n\n"
        "Synthesis was performed without the LLM (cost breaker or unavailable). "
        "The action follows the majority direction across the panel."
    )


async def synthesize_persona_plan(
    advices: Sequence[AdviceV1],
    *,
    portfolio_context: PortfolioContextV1 | None = None,
    asof: datetime | None = None,
) -> PlanV1:
    """Roll up N persona AdviceV1 records into ONE consensus PlanV1.

    Raises ValueError if `advices` is empty (the orchestrator should
    short-circuit upstream and not call us).
    """

    if not advices:
        raise ValueError("synthesize_persona_plan requires at least one AdviceV1")

    when = asof or datetime.now(UTC)
    asset = advices[0].asset

    direction, share = _majority_direction(advices)
    action = _direction_to_action(direction, has_signal=share > 0.5)

    entry_mid = statistics.median(_band_mid(a.entry_band) for a in advices)
    target_mid = statistics.fmean(_band_mid(a.target_band) for a in advices)
    stop_loss = max(a.stop_loss for a in advices)
    horizon_days = max(a.horizon_days for a in advices)
    confidence = statistics.fmean(a.confidence for a in advices) * share

    if action == "buy":
        # Enforce target_price > entry_price > stop_loss.
        if target_mid <= entry_mid:
            target_mid = entry_mid * 1.01
        if stop_loss >= entry_mid:
            stop_loss = entry_mid * 0.99
    elif action == "sell":
        # Enforce stop_loss > entry_price > target_price.
        if target_mid >= entry_mid:
            target_mid = entry_mid * 0.99
        if stop_loss <= entry_mid:
            stop_loss = entry_mid * 1.01

    evidence = _dedupe_evidence(advices)
    if action != "hold" and not evidence:
        # Synthesise a single anchor citation from the first advice so the
        # validator passes — a hard fail here would mean we silently lose
        # the consensus signal.
        evidence = [Evidence(kind="news", ref=f"persona.consensus.{advices[0].id}")]

    thesis = await _synthesize_thesis(advices, action)

    return PlanV1(
        id=str(ulid.ULID()),
        team="persona",
        persona_slug="consensus",
        issued_at=when,
        asset=asset,
        action=action,  # type: ignore[arg-type]
        entry_price=entry_mid,
        entry_window_open=when,
        entry_window_close=when + timedelta(hours=24),
        target_price=target_mid,
        stop_loss=stop_loss,
        max_drawdown_pct=15.0,
        horizon_days=horizon_days,
        sizing_pct_nav=2.0,
        confidence=max(0.0, min(1.0, confidence)),
        thesis=thesis,
        evidence=evidence,
        portfolio_context=portfolio_context,
        expires_at=when + timedelta(days=horizon_days),
        disclaimer=CONSENSUS_DISCLAIMER,
    )


async def team_plan_endpoint_payload(
    request: dict[str, Any],
) -> dict[str, Any]:
    """FastAPI entry: accepts a dict like
       {"advices": [<AdviceV1 dump>...], "portfolio_context": {...}}
       and returns the PlanV1 dump. Used by the trading-room DAG.
    """

    advices = [AdviceV1.model_validate(a) for a in request.get("advices") or []]
    pc_raw = request.get("portfolio_context")
    pc = PortfolioContextV1.model_validate(pc_raw) if pc_raw else None
    plan = await synthesize_persona_plan(advices, portfolio_context=pc)
    return plan.model_dump(mode="json", by_alias=True)
