"""Workflow 10 §5.10 — bias_balance math + dominance check."""

from __future__ import annotations

from datetime import UTC, datetime

from intel import bias_balance as bb
from intel.types import Event, SourceCfg


def _src(sid: str, region: str, lean: str, weight: float = 1.0) -> SourceCfg:
    return SourceCfg(id=sid, region=region, lean=lean, region_weight=weight, language="en")


def _ev(sid: str, region: str, lean: str) -> Event:
    when = datetime(2026, 1, 1, tzinfo=UTC)
    return Event(
        id=f"e:{sid}:{region}",
        source_id=sid,
        source_region=region,
        source_lean=lean,
        event_ts=when,
        title="t",
        body="b",
        title_en="t",
        body_en="b",
        lang="en",
    )


def test_bias_balance_normalizes_to_one() -> None:
    sources = [_src("a", "US", "center"), _src("b", "CN", "state")]
    weights = bb.weights_from(sources)
    events = [_ev("a", "US", "center"), _ev("a", "US", "center"), _ev("b", "CN", "state")]
    bal = bb.compute(events, weights)
    assert round(sum(bal.by_region.values()), 6) == 1.0
    assert round(bal.by_region["US"], 6) == round(2 / 3, 6)


def test_bias_balance_respects_region_weight() -> None:
    sources = [_src("a", "US", "center", weight=0.5), _src("b", "CN", "state", weight=1.5)]
    weights = bb.weights_from(sources)
    events = [_ev("a", "US", "center"), _ev("b", "CN", "state")]
    bal = bb.compute(events, weights)
    # CN weight is 3x US — share should reflect that.
    assert bal.by_region["CN"] > bal.by_region["US"]


def test_dominance_flags_over_threshold() -> None:
    sources = [_src("a", "US", "center"), _src("b", "CN", "state")]
    weights = bb.weights_from(sources)
    events = [_ev("a", "US", "center")] * 7 + [_ev("b", "CN", "state")] * 3
    bal = bb.compute(events, weights)
    assert bb.dominant_region(bal) == "US"


def test_dominance_returns_none_when_balanced() -> None:
    sources = [_src("a", "US", "center"), _src("b", "CN", "state")]
    weights = bb.weights_from(sources)
    events = [_ev("a", "US", "center"), _ev("b", "CN", "state")]
    bal = bb.compute(events, weights)
    assert bb.dominant_region(bal) is None
