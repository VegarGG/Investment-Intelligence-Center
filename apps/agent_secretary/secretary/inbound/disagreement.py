"""Render the agent-disagreement table (workflow 15 §5.4 + §7)."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta

from schema import AdviceV1


def render_disagreement_table(
    advices: Iterable[AdviceV1],
    *,
    ticker: str,
    asof: datetime,
    window: timedelta = timedelta(days=7),
) -> str:
    """Filter to `ticker` within the last 7 days and group by direction.

    Returns a markdown table or an empty string if there is no disagreement.
    """
    relevant = [
        a
        for a in advices
        if a.asset.ticker.upper() == ticker.upper() and (asof - a.issued_at) <= window
    ]
    directions = {a.direction for a in relevant}
    if len(directions) < 2:
        return ""

    rows = [
        "| agent | direction | entry | target | confidence | thesis |",
        "|---|---|---|---|---|---|",
    ]
    for a in sorted(relevant, key=lambda r: r.agent):
        entry = f"{a.entry_band[0]:.2f}–{a.entry_band[1]:.2f}"
        target = f"{a.target_band[0]:.2f}–{a.target_band[1]:.2f}"
        thesis = (a.thesis[:80] + "…") if len(a.thesis) > 80 else a.thesis
        rows.append(
            f"| {a.agent} | {a.direction} | {entry} | {target} "
            f"| {a.confidence:.2f} | {thesis} |"
        )
    rows.append("")
    rows.append(
        f"_{len(relevant)} advices on {ticker} disagree across {len(directions)} directions._"
    )
    return "\n".join(rows)
