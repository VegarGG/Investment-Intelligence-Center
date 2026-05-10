"""3-way Risk Panel debate (v2.5 N3.3 / T2.4).

Aggressive, Conservative, Neutral risk perspectives, each takes one
turn for up to 3 turns total. Cost: 3 Flash calls per board decision.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from llm_client import ChatMessage, chat_or_skip
from schema.plan import PlanV1

log = logging.getLogger(__name__)

MAX_TURNS = 3

_PROMPTS = {
    "aggressive": (
        "You are the Aggressive risk analyst. Argue the highest-conviction "
        "position the panel could take. Cite plan ids. ≤120 words."
    ),
    "conservative": (
        "You are the Conservative risk analyst. Argue what could go wrong "
        "and how to size DOWN the position. Cite plan ids. ≤120 words."
    ),
    "neutral": (
        "You are the Neutral risk analyst. Synthesise the prior two "
        "viewpoints into one sized recommendation. Cite plan ids. ≤120 words."
    ),
}


@dataclass(slots=True)
class RiskTurn:
    perspective: str
    text: str
    cost_skipped: bool = False


@dataclass(slots=True)
class RiskTranscript:
    turns: list[RiskTurn]
    aggressive: str
    conservative: str
    neutral: str
    cost_skipped: bool

    @property
    def degraded(self) -> bool:
        return self.cost_skipped or any(t.cost_skipped for t in self.turns)


def _plan_block(plans: Sequence[PlanV1]) -> str:
    return "\n".join(
        f"[{p.id}] team={p.team} action={p.action} sizing={p.sizing_pct_nav:.2f}% conf={p.confidence:.2f}"
        for p in plans
    )


async def _one_turn(
    *,
    perspective: str,
    plans: Sequence[PlanV1],
    prior: Sequence[RiskTurn],
) -> RiskTurn:
    system = _PROMPTS[perspective]
    block = _plan_block(plans)
    prior_block = (
        "\n\nPrior risk takes:\n" + "\n".join(f"[{t.perspective}] {t.text[:200]}" for t in prior)
        if prior
        else ""
    )
    user = f"Plans:\n{block}{prior_block}\n\nWrite your risk view."
    response = await chat_or_skip(
        f"board.risk_{perspective}",
        [
            ChatMessage(role="system", content=system),
            ChatMessage(role="user", content=user),
        ],
        max_tokens=250,
        temperature=0.4,
    )
    return RiskTurn(
        perspective=perspective,
        text=(response.text or "").strip(),
        cost_skipped=response.cost_skipped,
    )


async def deliberate(plans: Sequence[PlanV1]) -> RiskTranscript:
    """Run the 3-way risk debate. Returns a transcript with each take."""

    if not plans:
        raise ValueError("risk_panel requires at least one PlanV1")

    turns: list[RiskTurn] = []
    summaries: dict[str, str] = {"aggressive": "", "conservative": "", "neutral": ""}
    any_cost_skipped = False

    for perspective in ("aggressive", "conservative", "neutral"):
        if len(turns) >= MAX_TURNS:
            break
        turn = await _one_turn(perspective=perspective, plans=plans, prior=turns)
        turns.append(turn)
        summaries[perspective] = turn.text
        if turn.cost_skipped:
            any_cost_skipped = True
            break

    return RiskTranscript(
        turns=turns,
        aggressive=summaries["aggressive"],
        conservative=summaries["conservative"],
        neutral=summaries["neutral"],
        cost_skipped=any_cost_skipped,
    )
