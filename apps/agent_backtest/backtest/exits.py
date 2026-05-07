"""Exit detection (workflow 14 §2.4 + §5.3)."""

from __future__ import annotations

from datetime import datetime

from .types import ExitReason, Position


def check_exit(
    position: Position, mark_px: float, *, asof: datetime
) -> tuple[bool, ExitReason | None, float]:
    """Returns (exited, reason, exit_px). Defensive defaults — exit at the
    band edge, not market, to keep the leaderboard honest."""
    if position.state != "open":
        return False, None, position.exit_px or position.fill_px

    target_low, target_high = position.target_band

    if position.direction == "long":
        if mark_px >= target_low:
            return True, "target", target_low
        if mark_px <= position.stop_loss:
            return True, "stop", position.stop_loss
    else:  # short
        if mark_px <= target_high:
            return True, "target", target_high
        if mark_px >= position.stop_loss:
            return True, "stop", position.stop_loss

    if asof >= position.expires_at:
        return True, "expiry", mark_px

    return False, None, mark_px


def realize_pnl(position: Position, exit_px: float) -> tuple[float, float]:
    """Return (pnl_usd, pnl_r). pnl_r uses |entry_band| midpoint - stop_loss
    as the unit risk."""
    sign = 1.0 if position.direction == "long" else -1.0
    px_pnl = sign * (exit_px - position.fill_px)
    pnl_usd = px_pnl
    risk_unit = abs(position.fill_px - position.stop_loss) or 1.0
    pnl_r = px_pnl / risk_unit
    return pnl_usd, pnl_r
