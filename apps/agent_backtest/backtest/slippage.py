"""Slippage model (workflow 14 §2.2 verbatim).

fill_px = midpoint(entry_band) * (1 + sign(direction) * slip_bps / 10_000)
slip_bps = base + size_factor + volatility_factor
  base       = 5 bps for liquid US/HK/A-share large-cap; 15 bps else
  size_factor= 5 bps if size_usd > 0.5% of 5-day median dollar volume; else 0
  volatility_factor = 0.05 * 20-day realized vol in bps
"""

from __future__ import annotations

LIQUID_VENUES = ("NASDAQ", "NYSE", "HKEX", "SSE", "SZSE")
BASE_LIQUID_BPS = 5.0
BASE_OTHER_BPS = 15.0
SIZE_FACTOR_BPS = 5.0
SIZE_THRESHOLD_PCT = 0.005


def slippage_bps(
    venue: str,
    *,
    size_usd: float,
    median_dollar_volume_5d: float,
    realized_vol_20d_pct: float = 20.0,
) -> float:
    base = BASE_LIQUID_BPS if venue in LIQUID_VENUES else BASE_OTHER_BPS
    size_factor = (
        SIZE_FACTOR_BPS
        if median_dollar_volume_5d > 0 and size_usd > SIZE_THRESHOLD_PCT * median_dollar_volume_5d
        else 0.0
    )
    vol_factor = 0.05 * realized_vol_20d_pct  # rv in bps
    return base + size_factor + vol_factor


def fill_price(
    *,
    entry_band: tuple[float, float],
    direction: str,
    venue: str,
    size_usd: float,
    median_dollar_volume_5d: float,
    realized_vol_20d_pct: float = 20.0,
) -> float:
    mid = (entry_band[0] + entry_band[1]) / 2
    sign = 1.0 if direction == "long" else -1.0
    bps = slippage_bps(
        venue,
        size_usd=size_usd,
        median_dollar_volume_5d=median_dollar_volume_5d,
        realized_vol_20d_pct=realized_vol_20d_pct,
    )
    return mid * (1.0 + sign * bps / 10_000.0)
