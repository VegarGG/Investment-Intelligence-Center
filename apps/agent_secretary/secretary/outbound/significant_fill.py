"""Significant-fill alert (workflow 15 §5.2).

Trigger: backtest.fill.v1 with pnl_r >= 1.5 OR (exit_reason=stop AND |pnl_r| >= 0.8).
Templated; Flash narrative; throttled to 5/hour at the dispatcher level.
"""

from __future__ import annotations

from typing import Literal

from schema import BacktestFillV1, SecretaryNotifyV1

Severity = Literal["info", "warn", "alert", "critical"]

ALERT_THRESHOLD_R = 1.5
STOP_ALERT_THRESHOLD_R = 0.8


def is_significant(fill: BacktestFillV1) -> bool:
    if fill.pnl_r >= ALERT_THRESHOLD_R:
        return True
    return fill.exit_reason == "stop" and abs(fill.pnl_r) >= STOP_ALERT_THRESHOLD_R


def render(fill: BacktestFillV1) -> SecretaryNotifyV1:
    direction_word = "Take-profit" if fill.exit_reason == "target" else "Stop"
    pnl_pct = (fill.exit_px - fill.entry_px) / fill.entry_px * 100.0 if fill.entry_px else 0.0
    body = (
        f"**{direction_word}: {fill.agent}**\n"
        f"- advice id: `{fill.advice_id}`\n"
        f"- entry → exit: {fill.entry_px:.2f} → {fill.exit_px:.2f} ({pnl_pct:+.2f}%)\n"
        f"- pnl_r: {fill.pnl_r:+.2f}\n"
        f"- {fill.narrative}"
    )
    severity: Severity = "warn" if fill.exit_reason == "stop" else "info"
    return SecretaryNotifyV1(
        severity=severity,
        channel_hint="fills",
        language="en",
        markdown=body,
    )
