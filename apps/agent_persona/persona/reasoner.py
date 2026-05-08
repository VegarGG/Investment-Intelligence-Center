"""Daily / weekly reasoner (workflow 13 §5.2 - §5.3).

v2.5 T1.1 — uses `data_lake.quotes.get_mark` to anchor advice on the live
mark; `_relevant_events` filters by the persona's universe weights so the
LLM doesn't waste context on tickers the persona never trades.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import ulid
from data_lake.quotes import Mark, get_mark
from featureflags import flag
from llm_client import ChatMessage, chat, with_signals
from prompts import get
from schema import AdviceV1, Asset, Direction, Evidence, IntelDigestV1, IntelEvent

from .memory import MemoryStore
from .output_validator import validate
from .types import PersonaSpec

Cadence = Literal["daily", "weekly"]

# Map Intel event sectors / regions onto canonical universe-weight keys.
# Keys are the strings persona YAMLs use under `universe_weights`; values
# are the rough sectors / asset-class tags Intel attaches via primary_asset_links
# or that we infer from the event's regime_change_score.
_PLACEHOLDER_PX = 100.0  # used when the live-mark feature flag is off.


async def reason(
    spec: PersonaSpec,
    digest: IntelDigestV1,
    *,
    memory: MemoryStore,
    cadence: Cadence = "daily",
    asof: datetime | None = None,
) -> AdviceV1 | None:
    when = asof or datetime.now(UTC)
    relevant = _relevant_events(digest, spec)
    if not relevant:
        return None  # nothing meets the persona's universe filter today

    memory_query = " ".join(ev.headline for ev in relevant[:3])
    memories = await memory.query(spec.slug, memory_query, k=8 if cadence == "daily" else 16)

    rendered = get(
        "persona.daily.base" if cadence == "daily" else "persona.weekly.base",
        persona_slug=spec.slug,
        persona_priors_md="\n".join(f"- {p}" for p in spec.priors),
        digest_excerpt="\n".join(
            f"{ev.rank}. {ev.headline}: {ev.why_it_matters}" for ev in relevant
        ),
        memory_snippets="\n".join(f"- {m.text}" for m in memories) or "(no prior trades)",
    )

    caller = f"persona.{spec.slug}.{cadence}"
    async with with_signals(weekly_deepdive=(cadence == "weekly")):
        response = await chat(
            caller_id=caller,
            messages=[
                ChatMessage(role="system", content=rendered.system or ""),
                ChatMessage(role="user", content=rendered.user),
            ],
            max_tokens=900,
            temperature=0.4,
        )

    anchor = relevant[0]
    asset = _asset_for_event(anchor)
    mark = await _resolve_mark(asset, when)
    advice = _to_advice(
        spec=spec,
        thesis=response.text.strip(),
        anchor_event=anchor,
        asset=asset,
        mark=mark,
        when=when,
    )
    validate(advice, spec=spec)
    return advice


def _relevant_events(digest: IntelDigestV1, spec: PersonaSpec) -> list[IntelEvent]:
    """Filter digest events to those that fall under the persona's universe.

    A persona's `universe_weights` is a dict like
    ``{"us_largecap": 0.5, "commodities": 0.3, ...}``. We treat any key with
    weight > 0 as the persona's tradeable surface; events whose
    `primary_asset_links` resolve to any of those buckets pass the filter.
    Events with no `primary_asset_links` pass through (macro events that
    don't have a single anchor ticker) so personas still see regime signal.
    """

    if not spec.universe_weights:
        return list(digest.events)

    active_buckets = {bucket for bucket, w in spec.universe_weights.items() if w > 0}
    if not active_buckets:
        return list(digest.events)

    out: list[IntelEvent] = []
    for ev in digest.events:
        if not ev.primary_asset_links:
            out.append(ev)  # untargeted macro signal → always relevant
            continue
        if any(_asset_bucket(link) in active_buckets for link in ev.primary_asset_links):
            out.append(ev)
    return out


def _asset_bucket(asset_link: str) -> str:
    """Coarse classifier from a primary_asset_link string to a universe bucket.

    The mapping is intentionally narrow — Intel emits well-known shorthand
    in `primary_asset_links` (ticker symbol, ISO currency code, asset-class
    tag). Anything we don't recognise lands in `us_largecap` so we err on
    the side of letting events through.
    """

    s = asset_link.upper()
    if s in {"BTC", "ETH", "USDC", "USDT"} or s.startswith("CRYPTO_"):
        return "crypto"
    if s in {"GOLD", "OIL", "WTI", "BRENT", "COPPER", "WHEAT", "CORN"}:
        return "commodities"
    if s in {"USD", "EUR", "JPY", "GBP", "CNY", "DXY"} or s.startswith("FX_"):
        return "fx"
    if s.startswith("BOND_") or s in {"TLT", "IEF", "HYG", "LQD"}:
        return "bonds"
    if s.startswith("EM_") or s in {"EEM", "FXI", "INDA"}:
        return "em_equities"
    return "us_largecap"


def _asset_for_event(event: IntelEvent) -> Asset:
    ticker = event.primary_asset_links[0] if event.primary_asset_links else "GENERIC"
    return Asset(kind="equity", ticker=ticker, venue="NASDAQ")


async def _resolve_mark(asset: Asset, when: datetime) -> Mark | None:
    """Pull the live mark unless the feature flag is off.

    We register `persona.live_mark.enabled` (default ON) so the placeholder
    `100.0` survives as a tested fallback path during chaos drills.
    """

    import featureflags.registry  # noqa: F401  ensure flags are registered

    if not flag("persona.live_mark.enabled"):
        return None
    return await get_mark(asset, when)


def _bands_from_priors(
    spec: PersonaSpec, mark_price: float
) -> tuple[Direction, tuple[float, float], tuple[float, float], float]:
    """Derive (direction, entry_band, target_band, stop_loss) from the persona's
    priors + the live mark. v2.5 T1.1d.

    Default direction is `flat` (advisory hold) — reasoner prompts emit thesis
    text, not a directional flip, so flat keeps the advice schema valid while
    still anchoring price points to the live mark.
    """

    px = max(mark_price, 1e-6)
    direction: Direction = "flat"
    return direction, (px, px), (px, px), px


def _to_advice(
    *,
    spec: PersonaSpec,
    thesis: str,
    anchor_event: Any,
    asset: Asset,
    mark: Mark | None,
    when: datetime,
) -> AdviceV1:
    px = mark.price if (mark and mark.price > 0) else _PLACEHOLDER_PX
    direction, entry_band, target_band, stop_loss = _bands_from_priors(spec, px)
    return AdviceV1(
        id=str(ulid.ULID()),
        agent=f"persona.{spec.slug}",
        issued_at=when,
        asset=asset,
        thesis=thesis,
        direction=direction,
        confidence=0.5,
        entry_band=entry_band,
        target_band=target_band,
        stop_loss=stop_loss,
        horizon_days=180,
        max_drawdown_pct=15.0,
        sizing_hint_pct_nav=2.0,
        expires_at=when + timedelta(days=180),
        evidence=[Evidence(kind="news", ref=f"intel.digest.v1#{anchor_event.id}")],
        disclaimer=spec.disclaimer,
    )
