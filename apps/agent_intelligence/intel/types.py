"""Domain types for the intel pipeline (workflow 10 §5.2 onward)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class SourceCfg:
    """One row of `sources.yaml` (workflow 10 §2.4)."""

    id: str
    region: str
    lean: str
    region_weight: float
    language: str = "en"
    url: str | None = None
    channel: str | None = None
    rate_limit: str | None = None


@dataclass(frozen=True, slots=True)
class RawEvent:
    """Crawler output before dedupe / translation."""

    source_id: str
    event_ts: datetime
    ingest_ts: datetime
    url: str | None
    title: str
    body: str
    lang: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Event:
    """Post-dedupe, post-translate event ready for synthesis / persistence."""

    id: str
    source_id: str
    source_region: str
    source_lean: str
    event_ts: datetime
    title: str
    body: str
    title_en: str
    body_en: str
    lang: str
    sentiment: float = 0.0
    target_assets: list[str] = field(default_factory=list)
    url: str | None = None
