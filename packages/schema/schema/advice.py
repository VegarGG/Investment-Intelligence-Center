"""advice.v1 — the central contract emitted by every advisory agent.

GROUND TRUTH from PLAN_v2.1 §3. Append-only: adding a field is allowed; renaming
or removing a field requires bumping to advice.v2 with a parallel-publish window
(see workflow 05 §versioning policy).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

AssetKind = Literal["equity", "etf", "future", "option", "fx", "crypto", "bond"]
Direction = Literal["long", "short", "flat"]
EvidenceKind = Literal["news", "filing", "factor", "macro", "social", "filing_url"]


class Asset(BaseModel):
    kind: AssetKind
    ticker: str
    venue: str
    name: str | None = None


class Evidence(BaseModel):
    kind: EvidenceKind
    ref: str | None = None
    url: str | None = None


class AdviceV1(BaseModel):
    """The contract every advisory agent emits and the backtester consumes."""

    schema_version: Literal["advice.v1"] = Field(default="advice.v1", alias="schema")
    id: str
    agent: str
    issued_at: datetime
    asset: Asset
    thesis: str = Field(max_length=4000)
    direction: Direction
    confidence: float = Field(ge=0.0, le=1.0)
    entry_band: tuple[float, float]
    target_band: tuple[float, float]
    stop_loss: float
    horizon_days: int = Field(ge=1, le=365 * 5)
    max_drawdown_pct: float = Field(ge=0.0, le=100.0)
    sizing_hint_pct_nav: float = Field(ge=0.0, le=100.0)
    expires_at: datetime
    evidence: list[Evidence]
    disclaimer: str | None = None

    @field_validator("evidence")
    @classmethod
    def _require_at_least_one_citation(cls, v: list[Evidence]) -> list[Evidence]:
        if not v:
            raise ValueError(
                "advice.v1 requires at least one evidence entry "
                "— uncited advice is rejected by the backtester"
            )
        return v

    @field_validator("entry_band", "target_band")
    @classmethod
    def _band_ascending(cls, v: tuple[float, float]) -> tuple[float, float]:
        lo, hi = v
        if lo > hi:
            raise ValueError(f"band must be ascending: got ({lo}, {hi})")
        return v
