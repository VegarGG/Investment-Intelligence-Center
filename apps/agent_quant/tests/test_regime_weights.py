"""Workflow 12 §2.3 — regime weights table is GROUND TRUTH."""

from __future__ import annotations

import pytest
from quant.signal import REGIME_WEIGHTS, regime_weights


def test_every_regime_has_eight_factors() -> None:
    expected = {
        "momentum",
        "mean_reversion",
        "vol_risk_premium",
        "pead",
        "insider",
        "sector_rs",
        "crypto_basis",
        "fx_carry",
    }
    for regime, weights in REGIME_WEIGHTS.items():
        assert set(weights) == expected, f"regime {regime} has wrong factors"


def test_weights_sum_to_one() -> None:
    for regime, weights in REGIME_WEIGHTS.items():
        s = sum(weights.values())
        assert s == pytest.approx(1.0, abs=1e-6), f"regime {regime} sums to {s}"


def test_regime_weights_returns_copy() -> None:
    w = regime_weights("crisis")
    w["momentum"] = 0.99
    assert REGIME_WEIGHTS["crisis"]["momentum"] != 0.99
