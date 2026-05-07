"""Sharpe / Sortino / Calmar / bootstrap CI (workflow 14 §2.6)."""

from __future__ import annotations

import math
import random
import statistics
from collections.abc import Sequence


def sharpe(returns: Sequence[float], *, risk_free: float = 0.0) -> float:
    if len(returns) < 2:
        return 0.0
    excess = [r - risk_free for r in returns]
    sigma = statistics.pstdev(excess)
    if sigma == 0:
        return 0.0
    return statistics.fmean(excess) / sigma * math.sqrt(252)


def sortino(returns: Sequence[float], *, risk_free: float = 0.0) -> float:
    if len(returns) < 2:
        return 0.0
    excess = [r - risk_free for r in returns]
    downside = [min(0.0, r) for r in excess]
    sigma = math.sqrt(statistics.fmean([d * d for d in downside]))
    if sigma == 0:
        return 0.0
    return statistics.fmean(excess) / sigma * math.sqrt(252)


def max_drawdown(returns: Sequence[float]) -> float:
    if not returns:
        return 0.0
    peak = 0.0
    cum = 0.0
    max_dd = 0.0
    for r in returns:
        cum += r
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)
    return max_dd


def calmar(returns: Sequence[float]) -> float:
    dd = max_drawdown(returns)
    if dd == 0:
        return 0.0
    annual = statistics.fmean(returns) * 252
    return annual / dd


def bootstrap_sharpe(
    returns: Sequence[float],
    *,
    alpha: float = 0.05,
    n_boot: int = 1000,
    seed: int = 42,
) -> tuple[float, float, float]:
    if len(returns) < 5:
        s = sharpe(returns)
        return s, s, s
    rng = random.Random(seed)  # noqa: S311 — bootstrap statistics, not crypto
    samples = []
    n = len(returns)
    for _ in range(n_boot):
        draw = [returns[rng.randrange(n)] for _ in range(n)]
        samples.append(sharpe(draw))
    samples.sort()
    lower = samples[int(alpha / 2 * n_boot)]
    upper = samples[int((1 - alpha / 2) * n_boot)]
    return sharpe(returns), lower, upper
