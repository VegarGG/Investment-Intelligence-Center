"""Macro-event ↔ watchlist ticker scorer (workflow 11 §5.2).

`score = α * sector_match + β * primary_asset_link_overlap + γ * peer_mention`
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from schema import IntelEvent

from .types import WatchlistEntry

ALPHA = 0.4
BETA = 0.4
GAMMA = 0.2


@dataclass(frozen=True, slots=True)
class LinkScore:
    ticker: str
    event_id: str
    score: float
    reasons: tuple[str, ...]


def score_event(
    event: IntelEvent,
    entries: Iterable[WatchlistEntry],
    *,
    sector_index: dict[str, set[str]] | None = None,
) -> list[LinkScore]:
    """Return per-ticker scores. Highest-scoring first. Ties stable on ticker."""
    sector_index = sector_index or {}
    out: list[LinkScore] = []
    text = f"{event.headline} {event.why_it_matters}".lower()
    asset_set = {a.upper() for a in event.primary_asset_links}
    for entry in entries:
        reasons: list[str] = []
        sector_hit = 1.0 if entry.ticker in sector_index.get(entry.sector, set()) else 0.0
        if entry.sector and entry.sector.lower() in text:
            sector_hit = max(sector_hit, 0.5)
            reasons.append(f"sector match: {entry.sector}")
        asset_hit = 1.0 if entry.ticker.upper() in asset_set else 0.0
        if asset_hit:
            reasons.append("primary_asset_link")
        peer_hit = 0.0
        for peer in entry.peers:
            if peer.upper() in asset_set or peer.lower() in text:
                peer_hit = 1.0
                reasons.append(f"peer mention: {peer}")
                break
        score = ALPHA * sector_hit + BETA * asset_hit + GAMMA * peer_hit
        if score > 0:
            out.append(LinkScore(entry.ticker, event.id, score, tuple(reasons)))
    out.sort(key=lambda r: (-r.score, r.ticker))
    return out


def top_k(scores: list[LinkScore], k: int = 10) -> list[LinkScore]:
    return scores[:k]
