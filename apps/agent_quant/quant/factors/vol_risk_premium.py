"""Vol risk premium (workflow 12 §2.1 #3): front-month IV − 20-day RV."""

from __future__ import annotations

from collections.abc import Mapping


def vol_risk_premium(iv: Mapping[str, float], rv_20d: Mapping[str, float]) -> dict[str, float]:
    """Return {ticker: IV − RV}. Positive readings suggest premium-selling setups.

    Both inputs already in same units (e.g. annualized, decimal).
    """
    return {t: iv[t] - rv_20d.get(t, 0.0) for t in iv if t in rv_20d}
