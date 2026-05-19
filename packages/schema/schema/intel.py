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


class IntelGeoClusterV1(BaseModel):
    """High-impact geo cluster emitted by intel (P5.5).

    Fires when a region accumulates ``event_count`` events above
    ``tone_threshold`` within ``window_hours``. The trading-room treats
    this as a high-impact event identical to ``intel.event.high_impact.v1``.
    """

    schema_version: Literal["intel.event.geo_cluster.v1"] = Field(
        default="intel.event.geo_cluster.v1", alias="schema"
    )
    cluster_id: str
    region_label: str
    centroid_lat: float
    centroid_lon: float
    event_count: int = Field(ge=1)
    window_hours: int = Field(ge=1, le=168)
    mean_tone: float = Field(ge=-10.0, le=10.0)
    themes: list[str] = Field(default_factory=list)
    notable_event_ids: list[str] = Field(default_factory=list)
    issued_at: datetime

    model_config = {"populate_by_name": True}


class IntelContextV1(BaseModel):
    """Per-ticker rolling 24h context emitted by intel (P2.7).

    The trading room consumes this so persona / quant / fundamental nodes
    can attach context to plans without re-fetching the underlying
    events. Hash-friendly: every numeric field is bounded so the schema
    is amenable to feature-flag-gated golden tests.
    """

    schema_version: Literal["intel.context.v1"] = Field(
        default="intel.context.v1", alias="schema"
    )
    ticker: str
    asof: datetime
    window_hours: int = Field(ge=1, le=168, default=24)
    event_count: int = Field(ge=0, default=0)
    sentiment_ema: float = Field(ge=-1.0, le=1.0, default=0.0)
    regime_change_score: float = Field(ge=0.0, le=1.0, default=0.0)
    top_themes: list[str] = Field(default_factory=list)
    top_sources: list[str] = Field(default_factory=list)
    notable_event_ids: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}
