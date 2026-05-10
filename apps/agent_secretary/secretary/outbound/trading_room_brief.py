"""Trading-room brief composer (v2.5 N3.4 / T2.6).

Renders a BoardDecisionV1 + the considered PlanV1 envelopes + the risk
panel takes into one Markdown brief. Pushed at severity=ALERT (lower
than CRITICAL — interesting, not urgent).

Format mirrors plan §N3.4 verbatim so the snapshot golden is stable.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from schema.plan import PlanV1

DISCLAIMER = (
    "This is research, not investment advice. The IIC Investment Board "
    "is a simulated decision body; positions are illustrative only."
)


def _fmt_when(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M %Z").strip() or dt.isoformat()


def _team_label(plan: PlanV1) -> str:
    if plan.team == "persona" and plan.persona_slug:
        return f"persona/{plan.persona_slug}"
    return plan.team


def compose_trading_room_brief(
    *,
    decision: dict[str, Any],
    considered_plans: Sequence[PlanV1],
    aggressive_view: str = "",
    conservative_view: str = "",
    neutral_view: str = "",
    issued_at: datetime | None = None,
) -> str:
    """Pure-function Markdown composer. ``decision`` is a BoardDecisionV1 dict.

    Splits the deterministic format from any LLM polish — the trading-room
    DAG calls this directly so the brief shape never depends on LLM output.
    """

    plans_by_id = {p.id: p for p in considered_plans}
    chosen_id = str(decision.get("chosen_plan_id") or "")
    chosen = plans_by_id.get(chosen_id)
    if chosen is None:
        # Defensive: fail with a recognisable brief rather than crashing.
        return (
            "# Trading Room — (unknown ticker)\n\n"
            "Investment Board decision references a plan we don't have.\n\n"
            f"## Disclaimer\n{DISCLAIMER}\n"
        )

    when = issued_at or chosen.issued_at
    ticker = chosen.asset.ticker
    confidence = float(decision.get("confidence", 0.0))
    chair_rationale = str(decision.get("chair_rationale") or "")
    dissent_record = str(decision.get("dissent_record") or "")

    others = [p for p in considered_plans if p.id != chosen_id]
    n_dissenting = len(others)

    def _ev_block(p: PlanV1) -> str:
        if not p.evidence:
            return "(no evidence)"
        return ", ".join(
            (e.url or e.ref or e.kind)
            for e in p.evidence[:5]
        )

    plan_rows = "\n".join(
        f"| {_team_label(p)} | {p.action} | {p.entry_price:.2f} | "
        f"{p.target_price:.2f} | {p.stop_loss:.2f} | {p.confidence:.2f} |"
        for p in considered_plans
    )

    return (
        f"# Trading Room — {ticker}, {_fmt_when(when)}\n\n"
        f"## Winning plan ({_team_label(chosen)} — confidence {confidence:.2f})\n"
        f"Action: {chosen.action}; "
        f"entry {chosen.entry_price:.2f}; "
        f"target {chosen.target_price:.2f}; "
        f"stop {chosen.stop_loss:.2f}; "
        f"horizon {chosen.horizon_days}d\n\n"
        f"Thesis: {chosen.thesis}\n\n"
        f"Evidence: {_ev_block(chosen)}\n\n"
        f"Chair rationale: {chair_rationale or '(no rationale captured)'}\n\n"
        f"## Dissent ({n_dissenting} plans disagreed)\n"
        f"{dissent_record or '(no dissent recorded)'}\n\n"
        f"## Risk view\n"
        f"Aggressive: {aggressive_view or '(no view)'}\n\n"
        f"Conservative: {conservative_view or '(no view)'}\n\n"
        f"Neutral: {neutral_view or '(no view)'}\n\n"
        f"## All plans considered\n"
        f"| Team | Action | Entry | Target | Stop | Conf |\n"
        f"|------|--------|-------|--------|------|------|\n"
        f"{plan_rows}\n\n"
        f"## Disclaimer\n{DISCLAIMER}\n"
    )
