"""Backtest Reflector (v2.5 T1.11).

On every realised outcome (target hit, stop hit, expiry), Reflector writes
a 2-4 sentence reflection back into the source agent's decision-log entry:

- Cite alpha vs the agent's benchmark (SPY for US, HSI for HK).
- Declare ``thesis-held`` vs ``thesis-failed``.
- Name one concrete lesson — "be wary of 200-DMA fades on EM mid-caps".

The reflection is short on purpose; the markdown decision log is for
human grokking, not for ML training.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from data_lake.decision_log import DecisionLog


@dataclass(frozen=True, slots=True)
class RealizedOutcome:
    advice_id: str
    agent: str
    ticker: str
    venue: str
    direction: Literal["long", "short"]
    entry_px: float
    exit_px: float
    exit_reason: Literal["target", "stop", "expiry", "early_close"]
    realized_pnl_pct: float
    benchmark_pnl_pct: float
    issued_at: datetime
    closed_at: datetime


@dataclass(slots=True)
class Reflector:
    """Writes a reflection sentence back into the agent's decision log."""

    decision_log: DecisionLog

    async def reflect(self, outcome: RealizedOutcome) -> bool:
        text = compose_reflection(outcome)
        return await self.decision_log.attach_reflection(
            agent=outcome.agent,
            advice_id=outcome.advice_id,
            reflection=text,
        )


def compose_reflection(outcome: RealizedOutcome) -> str:
    """Deterministic 3-sentence reflection — no LLM, fully reproducible."""

    alpha = outcome.realized_pnl_pct - outcome.benchmark_pnl_pct
    held = _thesis_held(outcome)
    lesson = _lesson_for(outcome, held=held)
    benchmark = "SPY" if outcome.venue.upper() in {"NASDAQ", "NYSE", "ARCA"} else "HSI"

    return (
        f"Realized {outcome.realized_pnl_pct:+.1%} ({outcome.exit_reason}); "
        f"alpha vs {benchmark} = {alpha:+.1%}. "
        f"Thesis-{'held' if held else 'failed'}. "
        f"Lesson: {lesson}"
    )


def _thesis_held(outcome: RealizedOutcome) -> bool:
    if outcome.exit_reason == "target":
        return True
    if outcome.exit_reason == "stop":
        return False
    # Expiry / early_close: thesis held iff direction-aligned outcome.
    if outcome.direction == "long":
        return outcome.exit_px >= outcome.entry_px
    return outcome.exit_px <= outcome.entry_px


def _lesson_for(outcome: RealizedOutcome, *, held: bool) -> str:
    """Pick a one-line lesson keyed on (exit_reason, held). Deterministic."""
    if outcome.exit_reason == "target":
        return f"target hit on {outcome.ticker}; momentum continuation in this regime is real"
    if outcome.exit_reason == "stop":
        return (
            f"stop on {outcome.ticker}; thesis was {abs(outcome.benchmark_pnl_pct):.1%}× wrong "
            f"vs benchmark — review entry timing"
        )
    if outcome.exit_reason == "expiry":
        return (
            f"expiry on {outcome.ticker}; horizon was probably too short"
            if held
            else f"expiry on {outcome.ticker}; thesis didn't crystallize — re-examine catalyst timing"
        )
    return f"early_close on {outcome.ticker}; check whether the trigger was correct"
