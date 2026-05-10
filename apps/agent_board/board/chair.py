"""Board Chair LLM-synthesizes the BoardDecisionV1 (v2.5 N3.3 / T2.4).

Exactly one Pro-tier LLM call per board decision. Cost budget per
decision: ≤ $0.05 (per plan §N3.10).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from datetime import UTC, datetime

import ulid
from llm_client import ChatMessage, chat_or_skip
from schema.plan import PlanV1

from .bull_bear import BullBearTranscript
from .risk_panel import RiskTranscript
from .schema import BoardDecisionV1

log = logging.getLogger(__name__)

_SYSTEM_CHAIR = (
    "You are the IIC Investment Board Chair. Pick exactly ONE plan from "
    "the candidates and write a 3-section JSON object: "
    "{\"chosen_plan_id\": \"<id>\", \"chair_rationale\": \"...\", "
    "\"dissent_record\": \"...\", \"risk_view\": \"...\", \"confidence\": 0.0-1.0}. "
    "The chosen_plan_id MUST be one of the candidate ids. The dissent_record "
    "must cite at least 2 candidate plans by id when there is more than one. "
    "Output JSON only — no surrounding prose."
)


_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    match = _JSON_OBJECT_RE.search(text)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _fallback_decision(
    *,
    trigger_event_id: str,
    plans: Sequence[PlanV1],
    bull_bear: BullBearTranscript,
    risk: RiskTranscript,
    when: datetime,
    reason: str,
) -> BoardDecisionV1:
    """Deterministic fallback: pick the highest-confidence plan."""

    chosen = max(plans, key=lambda p: p.confidence)
    others = [p for p in plans if p.id != chosen.id]
    dissent = (
        "Synthetic-fallback dissent record — Chair LLM unavailable.\n\n"
        + (
            "Considered plans:\n"
            + "\n".join(
                f"- [{p.id}] team={p.team} action={p.action} conf={p.confidence:.2f}"
                for p in plans
            )
        )
        + (
            f"\n\nFallback chose [{chosen.id}] (highest confidence). "
            f"Other plans not chosen: {', '.join(p.id for p in others) or '(none)'}."
        )
    )
    risk_view = (
        f"aggressive: {risk.aggressive[:200]}\n"
        f"conservative: {risk.conservative[:200]}\n"
        f"neutral: {risk.neutral[:200]}".strip()
        or "Risk panel unavailable."
    )
    return BoardDecisionV1(
        id=str(ulid.ULID()),
        trigger_event_id=trigger_event_id,
        considered_plan_ids=[p.id for p in plans],
        chosen_plan_id=chosen.id,
        chair_rationale=(
            f"Fallback selection ({reason}): chose plan {chosen.id} on "
            f"highest confidence ({chosen.confidence:.2f})."
        ),
        dissent_record=dissent,
        risk_view=risk_view,
        confidence=chosen.confidence,
        issued_at=when,
    )


async def synthesize_decision(
    *,
    trigger_event_id: str,
    plans: Sequence[PlanV1],
    bull_bear: BullBearTranscript,
    risk: RiskTranscript,
    asof: datetime | None = None,
) -> BoardDecisionV1:
    when = asof or datetime.now(UTC)
    if not plans:
        raise ValueError("Investment Board requires at least one PlanV1")

    if bull_bear.degraded:
        log.info("board.chair: bull/bear degraded — falling back deterministically")
        return _fallback_decision(
            trigger_event_id=trigger_event_id,
            plans=plans,
            bull_bear=bull_bear,
            risk=risk,
            when=when,
            reason="bull_bear_degraded",
        )

    plan_block = "\n".join(
        f"[{p.id}] team={p.team} action={p.action} entry={p.entry_price:.2f} "
        f"target={p.target_price:.2f} stop={p.stop_loss:.2f} conf={p.confidence:.2f}: "
        f"{p.thesis[:300]}"
        for p in plans
    )
    user = (
        f"Trigger event: {trigger_event_id}\n\n"
        f"Candidate plans:\n{plan_block}\n\n"
        f"Bull thesis (round-{len(bull_bear.turns) // 2}): {bull_bear.bull_summary[:600]}\n"
        f"Bear thesis (round-{len(bull_bear.turns) // 2}): {bull_bear.bear_summary[:600]}\n\n"
        f"Risk panel:\n"
        f"- aggressive: {risk.aggressive[:300]}\n"
        f"- conservative: {risk.conservative[:300]}\n"
        f"- neutral: {risk.neutral[:300]}\n"
    )

    response = await chat_or_skip(
        "board.chair",
        [
            ChatMessage(role="system", content=_SYSTEM_CHAIR),
            ChatMessage(role="user", content=user),
        ],
        force_tier="pro",
        max_tokens=900,
        temperature=0.3,
    )

    if response.cost_skipped:
        return _fallback_decision(
            trigger_event_id=trigger_event_id,
            plans=plans,
            bull_bear=bull_bear,
            risk=risk,
            when=when,
            reason="chair_cost_skipped",
        )

    parsed = _extract_json(response.text)
    if parsed is None:
        return _fallback_decision(
            trigger_event_id=trigger_event_id,
            plans=plans,
            bull_bear=bull_bear,
            risk=risk,
            when=when,
            reason="chair_json_parse_failed",
        )

    valid_ids = {p.id for p in plans}
    chosen_id = str(parsed.get("chosen_plan_id") or "")
    if chosen_id not in valid_ids:
        return _fallback_decision(
            trigger_event_id=trigger_event_id,
            plans=plans,
            bull_bear=bull_bear,
            risk=risk,
            when=when,
            reason="chair_picked_unknown_plan",
        )

    chosen_plan = next(p for p in plans if p.id == chosen_id)
    confidence = float(parsed.get("confidence", chosen_plan.confidence))
    confidence = max(0.0, min(1.0, confidence))

    dissent = str(parsed.get("dissent_record") or "")
    if len(plans) > 1 and not dissent.strip():
        dissent = (
            "Chair did not produce dissent record; auto-generated: "
            + ", ".join(f"[{p.id}]" for p in plans if p.id != chosen_id)
        )

    return BoardDecisionV1(
        id=str(ulid.ULID()),
        trigger_event_id=trigger_event_id,
        considered_plan_ids=[p.id for p in plans],
        chosen_plan_id=chosen_id,
        chair_rationale=str(parsed.get("chair_rationale") or "")[:4000],
        dissent_record=dissent[:8000],
        risk_view=str(parsed.get("risk_view") or "")[:4000],
        confidence=confidence,
        issued_at=when,
    )
