"""Domain types for the quant pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

Region = Literal["US", "EU", "CN", "EM", "GLOBAL"]


@dataclass(frozen=True, slots=True)
class Bar:
    """One OHLCV bar — PIT correctness enforced by `as_of`."""

    ticker: str
    asof: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(slots=True)
class FactorRow:
    """One cell of the (asof, ticker, factor_id) hypertable."""

    asof: datetime
    ticker: str
    factor_id: str
    value: float
    rank: float


@dataclass(slots=True)
class Candidate:
    """Output of `signal.combine` — pre-risk, sized later by `risk.shape`."""

    ticker: str
    venue: str
    region: Region
    sector: str
    direction: Literal["long", "short"]
    combined_z: float
    contributing_factors: tuple[str, ...] = field(default_factory=tuple)
    realized_vol_60d: float = 0.20
    median_dollar_volume_5d: float = 0.0
    last_close: float = 0.0
