"""Domain types for the fundamental pipeline (workflow 11 §2.2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass(frozen=True, slots=True)
class WatchlistEntry:
    ticker: str
    venue: str
    sector: str
    thesis_tag: str
    peers: tuple[str, ...]


Form = Literal["10-K", "10-Q", "8-K", "20-F", "annual_cn", "annual_hk", "interim", "quarterly"]


@dataclass(frozen=True, slots=True)
class Filing:
    """One filing fetched + chunked + indexed."""

    ticker: str
    form: Form
    accession: str
    filed_at: datetime
    url: str
    text: str = ""


@dataclass(slots=True)
class Chunk:
    """Output of `filings.chunker.split` — preserves Item-level metadata so
    retrieval can prefer Item 7 / Item 1A."""

    parent_doc: str
    section: str
    chunk_idx: int
    text: str
    token_count: int


@dataclass(slots=True)
class ValuationCase:
    base: float
    bull: float
    bear: float
    target_12m: float
    assumptions: tuple[str, ...]
    catalysts: tuple[str, ...] = field(default_factory=tuple)


@dataclass(slots=True)
class Fundamentals:
    """Inputs the valuation prompt sees. Currency normalized to USD."""

    ticker: str
    venue: str
    sector: str
    asof: datetime
    pe: float | None
    ev_ebitda: float | None
    fcf_yield: float | None
    revenue_ttm_usd: float | None
    fcf_ttm_usd: float | None
    peers: dict[str, dict[str, float | None]] = field(default_factory=dict)
    missing_pct: float = 0.0
