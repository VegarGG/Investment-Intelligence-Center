"""Workflow 11 §5.3 — DCF math sanity."""

from __future__ import annotations

import pytest
from fund.valuation.dcf import DCFInputs, dcf_value


def test_dcf_simple_case() -> None:
    """5y at 5% growth, 2.5% terminal, 8% WACC. Hand-checked."""
    inputs = DCFInputs(
        starting_fcf_usd=100.0,
        growth_rates=(0.05,) * 5,
        terminal_growth=0.025,
        wacc=0.08,
        net_debt_usd=0.0,
        shares_outstanding=10.0,
    )
    result = dcf_value(inputs)
    # Each year's FCF and terminal calc are deterministic; spot-check fair value.
    assert result.enterprise_value_usd > 1500
    assert result.enterprise_value_usd < 3000
    assert result.fair_value_per_share_usd == pytest.approx(result.equity_value_usd / 10.0)


def test_dcf_rejects_wacc_below_terminal() -> None:
    inputs = DCFInputs(
        starting_fcf_usd=1.0,
        growth_rates=(0.05,) * 5,
        terminal_growth=0.10,
        wacc=0.05,
    )
    with pytest.raises(ValueError, match="terminal growth"):
        dcf_value(inputs)


def test_dcf_subtracts_net_debt() -> None:
    inputs = DCFInputs(
        starting_fcf_usd=100.0,
        growth_rates=(0.05,) * 5,
        terminal_growth=0.025,
        wacc=0.08,
        net_debt_usd=500.0,
        shares_outstanding=10.0,
    )
    result = dcf_value(inputs)
    assert result.equity_value_usd == pytest.approx(result.enterprise_value_usd - 500.0)
