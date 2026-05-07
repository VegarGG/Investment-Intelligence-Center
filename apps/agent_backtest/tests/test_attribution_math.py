"""Workflow 14 §2.6 — Sharpe + bootstrap CI math."""

from __future__ import annotations

import pytest
from backtest.attribution.stats import (
    bootstrap_sharpe,
    max_drawdown,
    sharpe,
)


def test_sharpe_zero_for_constant_returns() -> None:
    assert sharpe([0.01, 0.01, 0.01, 0.01]) == 0.0


def test_sharpe_positive_for_uptrend() -> None:
    assert sharpe([0.01, 0.02, 0.015, 0.018, 0.012]) > 0.0


def test_max_drawdown_simple_case() -> None:
    # cumsum: 0.05, 0.10, 0.07, 0.04, 0.09 -> peak 0.10, trough 0.04 -> dd = 0.06
    dd = max_drawdown([0.05, 0.05, -0.03, -0.03, 0.05])
    assert dd == pytest.approx(0.06)


def test_bootstrap_returns_band_around_point() -> None:
    rng_returns = [0.01, 0.02, -0.01, 0.015, 0.005, 0.012, -0.005, 0.018, 0.01, 0.014]
    point, lower, upper = bootstrap_sharpe(rng_returns, n_boot=200, seed=7)
    assert lower <= point <= upper
