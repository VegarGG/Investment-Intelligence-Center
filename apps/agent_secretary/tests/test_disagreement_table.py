"""Workflow 15 §5.4 + §7 — disagreement table renders only on disagreement."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import ulid
from schema import AdviceV1, Asset, Evidence
from secretary.inbound.disagreement import render_disagreement_table


def _advice(*, agent: str, ticker: str, direction: str) -> AdviceV1:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    if direction == "long":
        bands = {"entry": (100.0, 100.0), "target": (110.0, 115.0), "stop": 95.0}
    elif direction == "short":
        bands = {"entry": (100.0, 100.0), "target": (85.0, 90.0), "stop": 105.0}
    else:
        bands = {"entry": (100.0, 100.0), "target": (100.0, 100.0), "stop": 100.0}
    return AdviceV1(
        id=str(ulid.ULID()),
        agent=agent,
        issued_at=now,
        asset=Asset(kind="equity", ticker=ticker, venue="NASDAQ"),
        thesis=f"{agent} thesis on {ticker}",
        direction=direction,  # type: ignore[arg-type]
        confidence=0.6,
        entry_band=bands["entry"],  # type: ignore[arg-type]
        target_band=bands["target"],  # type: ignore[arg-type]
        stop_loss=bands["stop"],
        horizon_days=30,
        max_drawdown_pct=10.0,
        sizing_hint_pct_nav=2.0,
        expires_at=now + timedelta(days=30),
        evidence=[Evidence(kind="news", ref="x")],
        disclaimer=(
            "Stylized agent inspired by public writings; not Mr. Burry."
            if agent.startswith("persona.")
            else None
        ),
    )


def test_renders_table_when_directions_conflict() -> None:
    advices = [
        _advice(agent="quant", ticker="INTC", direction="long"),
        _advice(agent="persona.burry", ticker="INTC", direction="short"),
    ]
    out = render_disagreement_table(advices, ticker="INTC", asof=datetime(2026, 1, 2, tzinfo=UTC))
    assert "quant" in out and "persona.burry" in out
    assert "long" in out and "short" in out


def test_no_render_when_directions_agree() -> None:
    advices = [
        _advice(agent="quant", ticker="INTC", direction="long"),
        _advice(agent="fundamental", ticker="INTC", direction="long"),
    ]
    out = render_disagreement_table(advices, ticker="INTC", asof=datetime(2026, 1, 2, tzinfo=UTC))
    assert out == ""
