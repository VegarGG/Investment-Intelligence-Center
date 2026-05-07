"""Workflow 11 §5.2 — linker scoring favors sector + asset overlap."""

from __future__ import annotations

from fund.linker import score_event, top_k
from fund.types import WatchlistEntry
from schema import IntelEvent


def _entry(ticker: str, sector: str, peers: tuple[str, ...] = ()) -> WatchlistEntry:
    return WatchlistEntry(ticker=ticker, venue="NASDAQ", sector=sector, thesis_tag="x", peers=peers)


def _event(headline: str, assets: list[str]) -> IntelEvent:
    return IntelEvent(
        id="01HX0000000000000000000001",
        rank=1,
        headline=headline,
        why_it_matters="...",
        primary_asset_links=assets,
        regime_change_score=0.5,
        novelty=0.5,
    )


def test_direct_asset_match_scores_high() -> None:
    entries = [_entry("INTC", "Semiconductors", peers=("AMD", "NVDA"))]
    ev = _event("Intel guidance lifts semiconductor names", assets=["INTC"])
    scores = score_event(ev, entries)
    assert scores
    assert scores[0].ticker == "INTC"
    assert any("primary_asset_link" in r for r in scores[0].reasons)


def test_peer_mention_scores_lower_than_direct() -> None:
    entries = [_entry("INTC", "Semiconductors", peers=("AMD",))]
    ev = _event("AMD raises guidance", assets=["AMD"])
    scores = score_event(ev, entries)
    # Peer-only match scores lower than a direct asset match (0.2 vs 0.4 weight).
    assert scores
    assert scores[0].score < 0.5


def test_top_k_caps() -> None:
    entries = [_entry(f"X{i}", "Tech") for i in range(20)]
    ev = _event("tech rally broadens", assets=[])
    scores = score_event(ev, entries)
    assert len(top_k(scores, k=10)) <= 10
