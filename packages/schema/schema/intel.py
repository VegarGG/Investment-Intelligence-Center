"""intel.* event schemas (workflow 05 §4.1 - §4.3)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

MacroRegime = Literal[
    "rate_cut", "risk_on", "risk_off", "stagflation", "recession", "crisis", "unknown"
]
SourceLean = Literal["left", "center", "right", "state", "unknown"]


class IntelEventSource(BaseModel):
    id: str
    url: str | None = None
    lean: SourceLean | None = None
    region: str | None = None  # ISO-3166 alpha-2 or 'GLOBAL'


class IntelEvent(BaseModel):
    id: str
    rank: int = Field(ge=1)
    headline: str
    why_it_matters: str
    primary_asset_links: list[str] = Field(default_factory=list)
    regime_change_score: float = Field(ge=0.0, le=1.0)
    novelty: float = Field(ge=0.0, le=1.0)
    sentiment: float = Field(ge=-1.0, le=1.0, default=0.0)
    sources: list[IntelEventSource] = Field(default_factory=list)


class BiasBalance(BaseModel):
    """Distribution of source coverage across regions and political lean
    (workflow 10 §6 / 04 RISK)."""

    by_region: dict[str, float] = Field(default_factory=dict)
    by_lean: dict[str, float] = Field(default_factory=dict)


class IntelDigestV1(BaseModel):
    """Machine-readable event ranking emitted by intel.synth (workflow 05 §4.1)."""

    schema_version: Literal["intel.digest.v1"] = Field(default="intel.digest.v1", alias="schema")
    id: str
    issued_at: datetime
    macro_regime: MacroRegime = "unknown"
    events: list[IntelEvent] = Field(default_factory=list)
    bias_balance: BiasBalance = Field(default_factory=BiasBalance)
    macro_thesis: str = Field(max_length=2000)

    model_config = {"populate_by_name": True}


class IntelBriefV1(BaseModel):
    """Human-readable WeChat brief composed by the secretary (workflow 05 §4.2)."""

    schema_version: Literal["intel.brief.v1"] = Field(default="intel.brief.v1", alias="schema")
    issued_at: datetime
    audience: Literal["principal", "family"] = "principal"
    language: Literal["en", "zh"] = "en"
    markdown: str = Field(max_length=4096)
    char_count: int = Field(ge=0)
    wechat_safe: bool = True

    model_config = {"populate_by_name": True}


class IntelDashboardV1(BaseModel):
    """JSON snapshot consumed by the dashboard (workflow 21 §4 owns the
    inner shape; for now keep it open)."""

    schema_version: Literal["intel.dashboard.v1"] = Field(
        default="intel.dashboard.v1", alias="schema"
    )
    issued_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}
