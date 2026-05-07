"""Workflow 14 §2.2 — slippage model."""

from __future__ import annotations

from backtest.slippage import fill_price, slippage_bps


def test_liquid_venue_lower_base() -> None:
    nasdaq = slippage_bps("NASDAQ", size_usd=10, median_dollar_volume_5d=1e9)
    pinksheet = slippage_bps("OTC", size_usd=10, median_dollar_volume_5d=1e9)
    assert nasdaq < pinksheet


def test_size_factor_kicks_in_above_threshold() -> None:
    small = slippage_bps("NASDAQ", size_usd=1_000, median_dollar_volume_5d=1_000_000)
    big = slippage_bps("NASDAQ", size_usd=100_000, median_dollar_volume_5d=1_000_000)
    assert big > small


def test_long_fill_above_mid_short_fill_below() -> None:
    long_px = fill_price(
        entry_band=(99.0, 101.0),
        direction="long",
        venue="NASDAQ",
        size_usd=100,
        median_dollar_volume_5d=1e9,
    )
    short_px = fill_price(
        entry_band=(99.0, 101.0),
        direction="short",
        venue="NASDAQ",
        size_usd=100,
        median_dollar_volume_5d=1e9,
    )
    assert long_px > 100.0
    assert short_px < 100.0
