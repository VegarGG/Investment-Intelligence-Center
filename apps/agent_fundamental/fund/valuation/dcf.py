"""5-year DCF (workflow 11 §5.3).

Inputs in USD; user supplies starting FCF, growth schedule, terminal
growth, WACC, net debt, share count. Returns equity value per share.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DCFInputs:
    starting_fcf_usd: float
    growth_rates: Sequence[float]  # length = projection horizon
    terminal_growth: float
    wacc: float
    net_debt_usd: float = 0.0
    shares_outstanding: float = 1.0


@dataclass(frozen=True, slots=True)
class DCFResult:
    enterprise_value_usd: float
    equity_value_usd: float
    fair_value_per_share_usd: float
    pv_terminal_usd: float


def dcf_value(inputs: DCFInputs) -> DCFResult:
    if inputs.wacc <= inputs.terminal_growth:
        raise ValueError(
            f"WACC ({inputs.wacc}) must exceed terminal growth "
            f"({inputs.terminal_growth}) for DCF to converge"
        )

    fcf = inputs.starting_fcf_usd
    discounted_fcfs: list[float] = []
    for i, g in enumerate(inputs.growth_rates, start=1):
        fcf = fcf * (1 + g)
        discounted_fcfs.append(fcf / (1 + inputs.wacc) ** i)
    n = len(inputs.growth_rates)

    terminal_fcf = fcf * (1 + inputs.terminal_growth)
    terminal_value = terminal_fcf / (inputs.wacc - inputs.terminal_growth)
    pv_terminal = terminal_value / (1 + inputs.wacc) ** n

    ev = sum(discounted_fcfs) + pv_terminal
    equity = ev - inputs.net_debt_usd
    per_share = equity / inputs.shares_outstanding if inputs.shares_outstanding else 0.0
    return DCFResult(
        enterprise_value_usd=ev,
        equity_value_usd=equity,
        fair_value_per_share_usd=per_share,
        pv_terminal_usd=pv_terminal,
    )
