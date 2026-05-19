"""P7.5 — regime detector classifications."""

from __future__ import annotations

from quant.regime import RegimeInputs, classify


def test_unknown_when_vix_missing():
    assert classify(RegimeInputs()) == "unknown"


def test_crisis_high_vix_and_correlation():
    assert classify(RegimeInputs(vix_ema_20d=40.0, pairwise_corr=0.75)) == "crisis"


def test_risk_off_elevated_vix_weak_breadth():
    assert classify(RegimeInputs(vix_ema_20d=28.0, breadth_pct=0.30)) == "risk_off"


def test_recession_curve_inverted_and_weak_breadth():
    assert classify(RegimeInputs(vix_ema_20d=20.0, breadth_pct=0.40, yield_curve_bps=-50)) == "recession"


def test_risk_on_low_vix_strong_breadth():
    assert classify(RegimeInputs(vix_ema_20d=15.0, breadth_pct=0.65, yield_curve_bps=80)) == "risk_on"


def test_rate_cut_when_curve_flat_and_low_vix():
    assert classify(RegimeInputs(vix_ema_20d=16.0, yield_curve_bps=5)) == "rate_cut"
