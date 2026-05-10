"""Event-Triage Gate (v2.5 N3.1 / T2.1).

Sits in front of the trading-room DAG. For every
``intel.event.high_impact.v1`` event it decides one of:

    route=trading_room        → wake the full trading room
    route=morning_brief_only  → fold into the next morning brief
    route=drop                → ignore (stale / off-universe / low-impact)

Inputs (the event payload — see workflow 04 §6.1):
  - title, body, source_id, source_lean
  - tickers (universe overlap pre-computed by intel)
  - regime_change_score (0..1, intel-side)
  - surprise_factor       (0..1, intel-side)

Decision rule (deterministic baseline; LLM augments only if needed):
  1. If ``regime_change_score >= 0.85`` OR ``surprise_factor >= 0.85`` AND
     at least one ticker overlaps the active universe → trading_room.
  2. Else if any of the three numeric scores >= 0.4 OR universe overlap is
     non-empty → morning_brief_only.
  3. Else → drop.

LLM augmentation: when the numeric thresholds straddle the boundary
(0.4 <= max(scores) < 0.85 with non-empty overlap), we ask the LLM
``event_triage`` caller to break the tie with a one-token classification.
``chat_or_skip`` is used so a cost-breaker-open state defaults to
``drop`` (we'd rather miss a wake than spuriously fan out when the LLM
is unavailable).

Output: ``triage.decision.v1`` event published to the same NATS subject.
The event is hash-chain-persisted to ``lake.advice`` under
``agent='event_triage'`` for traceability.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

import featureflags.registry  # noqa: F401  ensure canonical flags are registered
from featureflags import flag

log = logging.getLogger(__name__)

Route = Literal["trading_room", "morning_brief_only", "drop"]


HIGH_IMPACT_THRESHOLD = 0.85
LOW_IMPACT_THRESHOLD = 0.4

LLM_CALLER_ID = "event_triage"


@dataclass(slots=True)
class TriageDecision:
    """Output of the gate. Persisted as ``triage.decision.v1``."""

    schema_version: str = "triage.decision.v1"
    trace_id: str = ""
    event_id: str = ""
    issued_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    route: Route = "drop"
    reason: str = ""
    affected_universe: list[str] = field(default_factory=list)
    regime_change_score: float = 0.0
    surprise_factor: float = 0.0
    affected_universe_overlap: float = 0.0
    cost_skipped: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema_version,
            "trace_id": self.trace_id,
            "event_id": self.event_id,
            "issued_at": self.issued_at,
            "route": self.route,
            "reason": self.reason,
            "affected_universe": self.affected_universe,
            "regime_change_score": self.regime_change_score,
            "surprise_factor": self.surprise_factor,
            "affected_universe_overlap": self.affected_universe_overlap,
            "cost_skipped": self.cost_skipped,
        }


@dataclass(frozen=True, slots=True)
class _TriageInputs:
    event_id: str
    trace_id: str
    title: str
    body: str
    tickers: tuple[str, ...]
    regime_change_score: float
    surprise_factor: float
    affected_universe_overlap: float


def _coerce_score(raw: Any, default: float = 0.0) -> float:
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return default
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


def _parse_event(payload: dict[str, Any]) -> _TriageInputs:
    tickers_raw = payload.get("tickers") or payload.get("affected_universe") or []
    tickers = tuple(str(t) for t in tickers_raw if isinstance(t, str | int))
    regime = _coerce_score(payload.get("regime_change_score"))
    surprise = _coerce_score(payload.get("surprise_factor"))
    overlap = _coerce_score(payload.get("affected_universe_overlap"), default=1.0 if tickers else 0.0)
    return _TriageInputs(
        event_id=str(payload.get("event_id") or payload.get("id") or ""),
        trace_id=str(payload.get("trace_id") or ""),
        title=str(payload.get("title") or ""),
        body=str(payload.get("body") or ""),
        tickers=tickers,
        regime_change_score=regime,
        surprise_factor=surprise,
        affected_universe_overlap=overlap,
    )


def _numeric_route(t: _TriageInputs) -> tuple[Route, str] | None:
    """Return a deterministic route + reason, or None if the LLM should break the tie."""
    has_overlap = bool(t.tickers) and t.affected_universe_overlap > 0.0
    big_signal = (
        t.regime_change_score >= HIGH_IMPACT_THRESHOLD
        or t.surprise_factor >= HIGH_IMPACT_THRESHOLD
    )
    medium_signal = (
        t.regime_change_score >= LOW_IMPACT_THRESHOLD
        or t.surprise_factor >= LOW_IMPACT_THRESHOLD
    )

    if big_signal and has_overlap:
        return (
            "trading_room",
            f"high-impact (regime={t.regime_change_score:.2f}, "
            f"surprise={t.surprise_factor:.2f}) with universe overlap",
        )
    if not has_overlap and not medium_signal:
        return ("drop", "no universe overlap and no medium-impact signal")
    if has_overlap and not medium_signal:
        return ("morning_brief_only", "overlap but only low-impact signals")
    if medium_signal and not has_overlap:
        return ("morning_brief_only", "medium signal but no universe overlap")
    # has_overlap and medium_signal but not big_signal — tie-break with LLM.
    return None


_VALID_LLM_TOKENS: dict[str, Route] = {
    "trading_room": "trading_room",
    "morning_brief_only": "morning_brief_only",
    "morning_brief": "morning_brief_only",
    "drop": "drop",
}


def _parse_llm_route(text: str) -> Route | None:
    t = (text or "").strip().lower().split()
    for token in t:
        for k, v in _VALID_LLM_TOKENS.items():
            if token == k:
                return v
    return None


async def _llm_tiebreak(t: _TriageInputs) -> tuple[Route, str, bool]:
    """Ask the LLM ``event_triage`` caller to pick one of three routes.

    Returns ``(route, reason, cost_skipped)``. On cost-breaker-open we
    default to ``drop`` — we'd rather miss a wake than spuriously fan
    out the trading room when the LLM is unavailable, which is the
    behaviour the plan §N3.1 calls out.
    """
    try:
        from llm_client.router import get_router
        from llm_client.types import ChatMessage
    except ImportError:
        # In a stripped test env without llm_client we fall back to drop.
        return ("drop", "llm_client unavailable; defaulting to drop", True)

    try:
        router = get_router()
    except Exception:  # noqa: BLE001 — defensive: any router-config issue → safe default
        return ("drop", "no router configured; defaulting to drop", True)

    system = (
        "You are the IIC Event Triage Gate. Decide whether a market event "
        "warrants waking the full trading room. Reply with exactly one of: "
        "trading_room, morning_brief_only, drop."
    )
    user = json.dumps(
        {
            "title": t.title,
            "body": t.body[:2000],
            "tickers": list(t.tickers),
            "regime_change_score": t.regime_change_score,
            "surprise_factor": t.surprise_factor,
            "affected_universe_overlap": t.affected_universe_overlap,
        },
        separators=(",", ":"),
    )

    response = await router.chat_or_skip(
        LLM_CALLER_ID,
        [
            ChatMessage(role="system", content=system),
            ChatMessage(role="user", content=user),
        ],
        max_tokens=8,
        temperature=0.0,
    )

    if response.cost_skipped:
        return ("drop", "cost breaker open; defaulting to drop", True)

    parsed = _parse_llm_route(response.text)
    if parsed is None:
        return (
            "morning_brief_only",
            f"LLM returned unparseable token {response.text!r}; safe-default to morning_brief_only",
            False,
        )
    return (parsed, f"LLM tie-break: {parsed}", False)


async def triage(payload: dict[str, Any]) -> TriageDecision:
    """Classify one ``intel.event.high_impact.v1`` payload.

    Honours the ``trading_room.event_triage.enabled`` flag — when OFF, every
    decision is ``drop`` with reason ``flag_disabled`` so the gate can be
    rolled back without redeploying.
    """

    t = _parse_event(payload)
    decision = TriageDecision(
        trace_id=t.trace_id,
        event_id=t.event_id,
        affected_universe=list(t.tickers),
        regime_change_score=t.regime_change_score,
        surprise_factor=t.surprise_factor,
        affected_universe_overlap=t.affected_universe_overlap,
    )

    if not flag("trading_room.event_triage.enabled"):
        decision.route = "drop"
        decision.reason = "flag_disabled"
        return decision

    routed = _numeric_route(t)
    if routed is not None:
        route, reason = routed
        decision.route = route
        decision.reason = reason
        return decision

    route, reason, cost_skipped = await _llm_tiebreak(t)
    decision.route = route
    decision.reason = reason
    decision.cost_skipped = cost_skipped
    return decision
