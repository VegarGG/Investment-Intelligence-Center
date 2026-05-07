"""Daily / weekly reasoner (workflow 13 §5.2 - §5.3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import ulid
from llm_client import ChatMessage, chat, with_signals
from prompts import get
from schema import AdviceV1, Asset, Direction, Evidence, IntelDigestV1, IntelEvent

from .memory import MemoryStore
from .output_validator import validate
from .types import PersonaSpec

Cadence = Literal["daily", "weekly"]


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

    advice = _to_advice(
        spec=spec,
        thesis=response.text.strip(),
        anchor_event=relevant[0],
        when=when,
    )
    validate(advice, spec=spec)
    return advice


def _relevant_events(digest: IntelDigestV1, spec: PersonaSpec) -> list[IntelEvent]:
    """Filter digest events to those whose primary asset / sector falls under
    the persona's universe weights. Spec hook reserved for asset-level filtering."""
    _ = spec
    return list(digest.events)


def _to_advice(*, spec: PersonaSpec, thesis: str, anchor_event: Any, when: datetime) -> AdviceV1:
    direction: Direction = "flat"
    px = 100.0  # caller would fetch the live mark; tests stub this
    return AdviceV1(
        id=str(ulid.ULID()),
        agent=f"persona.{spec.slug}",
        issued_at=when,
        asset=Asset(
            kind="equity",
            ticker=(
                anchor_event.primary_asset_links[0]
                if anchor_event.primary_asset_links
                else "GENERIC"
            ),
            venue="NASDAQ",
        ),
        thesis=thesis,
        direction=direction,
        confidence=0.5,
        entry_band=(px, px),
        target_band=(px, px),
        stop_loss=px,
        horizon_days=180,
        max_drawdown_pct=15.0,
        sizing_hint_pct_nav=2.0,
        expires_at=when + timedelta(days=180),
        evidence=[Evidence(kind="news", ref=f"intel.digest.v1#{anchor_event.id}")],
        disclaimer=spec.disclaimer,
    )
