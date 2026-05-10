"""Persist BoardDecisionV1 to lake.advice (v2.5 N3.3 / T2.4).

The Board piggy-backs on the existing advice ledger: ``agent='board'``
under the same hash chain that protects every other agent's advice.
The trigger from migration 0002 enforces chain linkage; no new SQL
needed.

We project a BoardDecisionV1 onto the AdviceV1 shape because the ledger
table is the canonical immutable surface. The chosen plan's
prices / horizon flow through; the BoardDecision's `chair_rationale`
becomes the AdviceV1 `thesis`; the dissent_record is folded into the
JSONB payload.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

from schema.advice import AdviceV1, Direction, Evidence
from schema.plan import PlanV1

from .schema import BoardDecisionV1


def _action_to_direction(action: str) -> Direction:
    if action == "buy":
        return "long"
    if action == "sell":
        return "short"
    return "flat"


def board_decision_to_advice(
    decision: BoardDecisionV1,
    plans: Sequence[PlanV1],
) -> AdviceV1:
    """Project the Board's decision onto an AdviceV1 envelope for the ledger.

    The chosen plan supplies prices, asset, and horizon; the Board's
    rationale + dissent supply the thesis + evidence trail.
    """

    chosen = next(p for p in plans if p.id == decision.chosen_plan_id)
    direction = _action_to_direction(chosen.action)

    if direction == "long":
        entry_band = (chosen.entry_price * 0.999, chosen.entry_price * 1.001)
        target_band = (chosen.target_price * 0.99, chosen.target_price)
    elif direction == "short":
        entry_band = (chosen.entry_price * 0.999, chosen.entry_price * 1.001)
        target_band = (chosen.target_price, chosen.target_price * 1.01)
    else:
        entry_band = (chosen.entry_price, chosen.entry_price)
        target_band = (chosen.entry_price, chosen.entry_price)

    evidence: list[Evidence] = [
        Evidence(kind="news", ref=f"board.trigger.{decision.trigger_event_id}"),
    ]
    for pid in decision.considered_plan_ids:
        evidence.append(Evidence(kind="factor", ref=f"board.plan.{pid}"))

    return AdviceV1(
        id=decision.id,
        agent="board",
        issued_at=decision.issued_at,
        asset=chosen.asset,
        thesis=(decision.chair_rationale or "Investment Board decision.")[:4000],
        direction=direction,
        confidence=decision.confidence,
        entry_band=entry_band,
        target_band=target_band,
        stop_loss=chosen.stop_loss,
        horizon_days=chosen.horizon_days,
        max_drawdown_pct=chosen.max_drawdown_pct,
        sizing_hint_pct_nav=chosen.sizing_pct_nav,
        expires_at=decision.issued_at + timedelta(days=chosen.horizon_days),
        evidence=evidence,
        disclaimer=None,
    )


async def persist_decision(
    decision: BoardDecisionV1,
    plans: Sequence[PlanV1],
) -> bytes:
    """Append the Board's decision to ``lake.advice``. Returns the row hash."""

    from data_lake.advice_ledger import append

    advice = board_decision_to_advice(decision, plans)
    return await append(advice.model_dump(mode="json", by_alias=True))
