"""v2.5 T1.1 acceptance — persona advice anchors on the live mark, not 100.0.

Covers:
- Live mark price flows into entry_band / target_band / stop_loss.
- The legacy `px=100.0` placeholder is the explicit fallback when the
  feature flag is off (chaos drill).
- `_relevant_events` filters by `spec.universe_weights`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import featureflags
import featureflags.registry  # noqa: F401  populate canonical flags
import pytest
from data_lake.quotes import Mark, reset_fetcher_for_test, set_fetcher_for_test
from persona.memory import MemoryEntry, MemoryStore
from persona.reasoner import _relevant_events, reason
from persona.types import CanonicalTrade, MemoryScope, PersonaSpec
from schema import IntelDigestV1, IntelEvent


class _StubMemory(MemoryStore):
    async def query(
        self, persona_slug, query, *, k=8
    ) -> list[MemoryEntry]:
        return []

    async def insert(self, persona_slug, entry: MemoryEntry) -> None:
        return None

    async def insert_canonical_trades(self, persona_slug, trades) -> None:
        return None


def _spec(slug: str = "rogers", weights: dict[str, float] | None = None) -> PersonaSpec:
    return PersonaSpec(
        slug=slug,
        display_name=slug.title(),
        priors=("commodities lead inflation",),
        canonical_trades=(
            CanonicalTrade(era="1980s", asset="gold", action="long", lesson="patience"),
        ),
        universe_weights=weights or {"commodities": 0.5, "us_largecap": 0.5},
        prompt_template_ref="persona.daily.base@1.0.0",
        memory_scope=MemoryScope(retain_days=365),
        guardrails=("Never claim to be the real Jim Rogers.",),
        disclaimer="Stylized agent inspired by public writings; not Mr. Rogers.",
    )


def _digest(events: list[IntelEvent]) -> IntelDigestV1:
    return IntelDigestV1(
        id="01HX8E5G7M0000000000000099",
        issued_at=datetime(2026, 5, 8, 12, 0, tzinfo=UTC),
        macro_regime="risk_on",
        events=events,
        macro_thesis="risk-on regime",
    )


def _evt(eid: str, links: list[str]) -> IntelEvent:
    return IntelEvent(
        id=eid,
        rank=1,
        headline=f"event {eid}",
        why_it_matters="...",
        primary_asset_links=links,
        regime_change_score=0.5,
        novelty=0.5,
        sentiment=0.0,
    )


@pytest.fixture(autouse=True)
def _isolate_quotes_and_flags():
    reset_fetcher_for_test()
    featureflags.reset_for_test()
    yield
    reset_fetcher_for_test()
    featureflags.reset_for_test()


def test_relevant_events_filters_by_universe():
    """Persona with only commodities exposure ignores AAPL, sees GOLD."""
    spec = _spec(weights={"commodities": 1.0})
    events = [
        _evt("e-aapl", ["AAPL"]),
        _evt("e-gold", ["GOLD"]),
        _evt("e-macro", []),  # macro: untargeted, must pass
    ]
    digest = _digest(events)
    out = _relevant_events(digest, spec)
    out_ids = {e.id for e in out}
    assert "e-gold" in out_ids
    assert "e-macro" in out_ids
    assert "e-aapl" not in out_ids


def test_relevant_events_passes_all_when_weights_empty():
    spec = _spec(weights={})
    events = [_evt("e-aapl", ["AAPL"]), _evt("e-gold", ["GOLD"])]
    out = _relevant_events(_digest(events), spec)
    assert len(out) == 2


@pytest.mark.asyncio
async def test_advice_anchors_on_live_mark(monkeypatch):
    """When the flag is on, advice price points come from get_mark()."""
    asof = datetime(2026, 5, 8, 14, 30, tzinfo=UTC)

    async def stub_fetcher(asset, asof_in):
        return Mark(
            price=2_350.0,  # gold-y price
            bar_ts=asof_in,
            asof=asof_in,
            stale_seconds=0,
            source="stub",
        )

    set_fetcher_for_test(stub_fetcher)
    featureflags.set_for_test("persona.live_mark.enabled", True)

    spec = _spec(weights={"commodities": 1.0})
    digest = _digest([_evt("e-gold", ["GOLD"])])
    advice = await reason(spec, digest, memory=_StubMemory(), asof=asof)

    assert advice is not None
    assert advice.entry_band == (2_350.0, 2_350.0)
    assert advice.stop_loss == 2_350.0
    assert advice.asset.ticker == "GOLD"


@pytest.mark.asyncio
async def test_advice_falls_back_to_placeholder_when_flag_off():
    """Chaos drill: with the flag off, the legacy 100.0 fallback kicks in."""
    asof = datetime(2026, 5, 8, 14, 30, tzinfo=UTC)
    featureflags.set_for_test("persona.live_mark.enabled", False)

    spec = _spec(weights={"commodities": 1.0})
    digest = _digest([_evt("e-gold", ["GOLD"])])
    advice = await reason(spec, digest, memory=_StubMemory(), asof=asof)

    assert advice is not None
    # Fallback collapses to the placeholder so chaos tests can detect when
    # the flag was flipped off.
    assert advice.entry_band == (100.0, 100.0)


@pytest.mark.asyncio
async def test_unavailable_mark_falls_back_to_placeholder():
    """A 'no-bar' mark (price=0) must trigger the placeholder safety net."""
    asof = datetime(2026, 5, 8, 14, 30, tzinfo=UTC)

    async def stub_fetcher(asset, asof_in):
        return Mark(
            price=0.0,
            bar_ts=asof_in,
            asof=asof_in,
            stale_seconds=999_999,
            source="no-bar",
        )

    set_fetcher_for_test(stub_fetcher)
    featureflags.set_for_test("persona.live_mark.enabled", True)

    spec = _spec(weights={"commodities": 1.0})
    digest = _digest([_evt("e-gold", ["GOLD"])])
    advice = await reason(spec, digest, memory=_StubMemory(), asof=asof)

    assert advice is not None
    assert advice.entry_band == (100.0, 100.0)
