"""Bull/Bear research debate (v2.5 N3.3 / T2.4).

Two debate rounds, max. Bull writes a long thesis; Bear writes a short
thesis. The Chair (in chair.py) breaks the tie. Cost: 4 Flash calls per
board decision (2 rounds × Bull + Bear).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from llm_client import ChatMessage, chat_or_skip
from schema.plan import PlanV1

log = logging.getLogger(__name__)

MAX_ROUNDS = 2


@dataclass(slots=True)
class DebateTurn:
    side: str  # 'bull' | 'bear'
    round_no: int
    text: str
    cost_skipped: bool = False


@dataclass(slots=True)
class BullBearTranscript:
    turns: list[DebateTurn]
    bull_summary: str
    bear_summary: str
    cost_skipped: bool

    @property
    def degraded(self) -> bool:
        """True if any turn was synthetic-skip-tainted or returned junk."""
        return self.cost_skipped or any(t.cost_skipped for t in self.turns)


_SYSTEM_BULL = (
    "You are the IIC Bull research analyst. Argue why the chosen ticker "
    "should be BOUGHT or HELD LONG given the plans below. Cite specific "
    "plan ids. ≤180 words."
)
_SYSTEM_BEAR = (
    "You are the IIC Bear research analyst. Argue why the chosen ticker "
    "should be SOLD or HELD SHORT given the plans below. Cite specific "
    "plan ids. ≤180 words."
)


def _plan_summary(plan: PlanV1) -> str:
    return (
        f"[{plan.id}] team={plan.team} action={plan.action} "
        f"entry={plan.entry_price:.2f} target={plan.target_price:.2f} "
        f"stop={plan.stop_loss:.2f} confidence={plan.confidence:.2f} "
        f"thesis={plan.thesis[:300]}"
    )


async def _one_turn(
    *,
    side: str,
    round_no: int,
    plans: Sequence[PlanV1],
    prior: Sequence[DebateTurn],
) -> DebateTurn:
    system = _SYSTEM_BULL if side == "bull" else _SYSTEM_BEAR
    plan_block = "\n".join(_plan_summary(p) for p in plans)
    prior_block = (
        "\n\nPrior debate:\n"
        + "\n".join(f"[{t.side} r{t.round_no}] {t.text[:300]}" for t in prior)
        if prior
        else ""
    )
    user = f"Plans considered:\n{plan_block}{prior_block}\n\nWrite your argument."
    response = await chat_or_skip(
        f"board.{side}",
        [
            ChatMessage(role="system", content=system),
            ChatMessage(role="user", content=user),
        ],
        max_tokens=350,
        temperature=0.5,
    )
    return DebateTurn(
        side=side,
        round_no=round_no,
        text=(response.text or "").strip(),
        cost_skipped=response.cost_skipped,
    )


async def debate(plans: Sequence[PlanV1]) -> BullBearTranscript:
    """Run up to ``MAX_ROUNDS`` Bull/Bear turns over the candidate plans.

    Returns a transcript even when individual turns are cost-skipped —
    callers (chair.py, the DAG) check ``transcript.degraded`` to fall
    back to single-team mode.
    """

    if not plans:
        raise ValueError("debate requires at least one PlanV1")

    turns: list[DebateTurn] = []
    bull_text, bear_text = "", ""
    any_cost_skipped = False

    for r in range(1, MAX_ROUNDS + 1):
        bull = await _one_turn(side="bull", round_no=r, plans=plans, prior=turns)
        turns.append(bull)
        bear = await _one_turn(side="bear", round_no=r, plans=plans, prior=turns)
        turns.append(bear)
        if bull.cost_skipped or bear.cost_skipped:
            any_cost_skipped = True
            break  # no point continuing once the LLM is unavailable
        bull_text = bull.text
        bear_text = bear.text

    return BullBearTranscript(
        turns=turns,
        bull_summary=bull_text,
        bear_summary=bear_text,
        cost_skipped=any_cost_skipped,
    )
