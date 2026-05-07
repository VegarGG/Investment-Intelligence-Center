"""Synth — Pro-tier digest composer (workflow 10 §5.8).

Loads the prompt from `intel.synth/1.0.0.md`, calls the LLM, parses the
JSON response into `IntelDigestV1`, and runs the §5.10 bias re-prompt loop
when one region dominates the candidate set.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

import ulid
from llm_client import ChatMessage, chat
from prompts import get
from schema import (
    BiasBalance,
    IntelDigestV1,
    IntelEvent,
    IntelEventSource,
    MacroRegime,
    canonical_json,
)

from . import bias_balance as bb
from .macro import MacroRelease
from .types import Event, SourceCfg

log = logging.getLogger(__name__)

MAX_REPROMPTS = 2


async def synthesize(
    events: list[Event],
    *,
    macro_releases: list[MacroRelease],
    macro_regime: str,
    sources: Iterable[SourceCfg],
    asof: datetime | None = None,
) -> IntelDigestV1:
    """Compose the digest. Re-prompt up to twice if region dominance > 0.55."""
    when = asof or datetime.now(UTC)
    weights = bb.weights_from(sources)
    balance = bb.compute(events, weights)

    rendered = get(
        "intel.synth",
        events_json=_events_payload(events, macro_releases),
        macro_regime=macro_regime,
    )

    messages = [
        ChatMessage(role="system", content=rendered.system or ""),
        ChatMessage(role="user", content=rendered.user),
    ]

    digest = await _call_synth(messages, when=when)

    attempts = 0
    while attempts < MAX_REPROMPTS:
        dominant = bb.dominant_region(balance)
        if dominant is None:
            break
        attempts += 1
        log.info("bias re-prompt #%d (dominant=%s)", attempts, dominant)
        messages.append(
            ChatMessage(
                role="user",
                content=(
                    f"Previous synth was too {dominant}-heavy. "
                    f"Surface at least 5 events from non-{dominant} regions."
                ),
            )
        )
        digest = await _call_synth(messages, when=when)

    digest.bias_balance = balance
    return digest


async def _call_synth(messages: list[ChatMessage], *, when: datetime) -> IntelDigestV1:
    response = await chat(
        caller_id="intel.synth",
        messages=messages,
        max_tokens=4096,
        temperature=0.2,
    )
    parsed = _parse_response(response.text)
    parsed.setdefault("id", str(ulid.ULID()))
    parsed.setdefault("issued_at", when.isoformat())
    parsed.setdefault("macro_thesis", "Macro thesis pending.")
    parsed.setdefault("events", [])
    parsed.setdefault("bias_balance", {"by_region": {}, "by_lean": {}})
    return IntelDigestV1.model_validate(parsed)


def _parse_response(text: str) -> dict[str, Any]:
    """Pro often wraps JSON in fences or prose. Extract the first {...} blob."""
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return _json_loads(text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"synth response did not contain a JSON object: {text[:200]!r}")
    return _json_loads(text[start : end + 1])


def _json_loads(text: str) -> dict[str, Any]:
    obj = json.loads(text)
    if not isinstance(obj, dict):
        raise ValueError(f"synth response root must be an object, got {type(obj).__name__}")
    return obj


def _events_payload(events: list[Event], releases: list[MacroRelease]) -> str:
    payload = {
        "events": [
            {
                "id": ev.id,
                "title": ev.title_en,
                "body": ev.body_en[:600],
                "source_id": ev.source_id,
                "source_region": ev.source_region,
                "source_lean": ev.source_lean,
                "event_ts": ev.event_ts.isoformat(),
                "sentiment": ev.sentiment,
                "target_assets": ev.target_assets,
            }
            for ev in events
        ],
        "macro_releases": [
            {
                "source": r.source,
                "series": r.series,
                "value": r.value,
                "released_at": r.released_at.isoformat(),
                "note": r.note,
            }
            for r in releases
        ],
    }
    return str(canonical_json(payload).decode("utf-8"))


def fallback_digest(
    events: Iterable[Event], *, balance: BiasBalance, macro_regime: MacroRegime
) -> IntelDigestV1:
    """Used when the synth call fails outright — never blocks the brief."""
    ev_list = list(events)[:25]
    return IntelDigestV1(
        id=str(ulid.ULID()),
        issued_at=datetime.now(UTC),
        macro_regime=macro_regime,
        events=[
            IntelEvent(
                id=ev.id,
                rank=i + 1,
                headline=ev.title_en,
                why_it_matters="Auto-stub: synth fallback path.",
                primary_asset_links=list(ev.target_assets),
                regime_change_score=0.0,
                novelty=0.0,
                sentiment=ev.sentiment,
                sources=[IntelEventSource(id=ev.source_id, url=ev.url)],
            )
            for i, ev in enumerate(ev_list)
        ],
        bias_balance=balance,
        macro_thesis="Synth fallback — review manually.",
    )
