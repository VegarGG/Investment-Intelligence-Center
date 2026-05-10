"""v2.5 N3.1 / T2.1 — Event-Triage Gate routing tests.

10 cases per plan §N3.1:
  - Each route covered (trading_room / morning_brief_only / drop)
  - LLM tie-break path
  - LLM-misclassification fallback (default to morning_brief_only)
  - Cost-breaker-open fallback (default to drop)
  - Flag-disabled bypass
  - Empty-overlap edge case
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import pytest
from featureflags import reset_for_test, set_for_test
from llm_client.router import set_router
from llm_client.types import ChatResponse
from orchestrator.plan.event_triage import triage


@dataclass(slots=True)
class _FakeRouter:
    """Stand-in for LlmRouter used in tests.

    Returns a canned ``ChatResponse`` from ``chat_or_skip``. ``cost_skipped``
    flips the cost-breaker-open path; ``text`` controls the parsed token.
    """

    text: str = "morning_brief_only"
    cost_skipped: bool = False

    async def chat_or_skip(self, caller_id: str, messages: list[Any], **_kw: Any) -> ChatResponse:
        if self.cost_skipped:
            return ChatResponse(
                text="[cost-breaker open: synthetic skip]",
                model="synthetic-skip:cost_breaker_open",
                tier="flash",
                prompt_tokens=0,
                completion_tokens=0,
                cost_usd=0.0,
                cached=False,
                fallback_used=False,
                cost_skipped=True,
                request_id="skip-test",
                latency_ms=0,
            )
        return ChatResponse(
            text=self.text,
            model="fake",
            tier="flash",
            prompt_tokens=10,
            completion_tokens=4,
            cost_usd=0.0,
            cached=False,
            fallback_used=False,
            cost_skipped=False,
            request_id="fake-1",
            latency_ms=1,
        )


@asynccontextmanager
async def _enabled_flag() -> AsyncIterator[None]:
    set_for_test("trading_room.event_triage.enabled", True)
    try:
        yield
    finally:
        reset_for_test()


def _evt(**overrides: Any) -> dict[str, Any]:
    base = {
        "event_id": "evt_001",
        "trace_id": "trace_001",
        "title": "FOMC cuts rates 50bps surprise",
        "body": "Powell cited recession risk; markets repriced.",
        "tickers": ["US.SPY", "US.QQQ"],
        "regime_change_score": 0.9,
        "surprise_factor": 0.95,
        "affected_universe_overlap": 0.8,
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_high_impact_with_overlap_routes_to_trading_room() -> None:
    async with _enabled_flag():
        d = await triage(_evt())
    assert d.route == "trading_room"
    assert "high-impact" in d.reason


@pytest.mark.asyncio
async def test_low_impact_routes_to_drop() -> None:
    async with _enabled_flag():
        d = await triage(
            _evt(
                regime_change_score=0.05,
                surprise_factor=0.1,
                tickers=[],
                affected_universe_overlap=0.0,
            )
        )
    assert d.route == "drop"


@pytest.mark.asyncio
async def test_medium_impact_no_overlap_routes_to_morning_brief() -> None:
    async with _enabled_flag():
        d = await triage(
            _evt(
                regime_change_score=0.5,
                surprise_factor=0.45,
                tickers=[],
                affected_universe_overlap=0.0,
            )
        )
    assert d.route == "morning_brief_only"


@pytest.mark.asyncio
async def test_overlap_only_low_signal_routes_to_morning_brief() -> None:
    async with _enabled_flag():
        d = await triage(
            _evt(
                regime_change_score=0.1,
                surprise_factor=0.1,
                tickers=["US.AAPL"],
                affected_universe_overlap=0.5,
            )
        )
    assert d.route == "morning_brief_only"


@pytest.mark.asyncio
async def test_llm_tiebreak_picks_trading_room() -> None:
    set_router(_FakeRouter(text="trading_room"))  # type: ignore[arg-type]
    try:
        async with _enabled_flag():
            d = await triage(
                _evt(
                    regime_change_score=0.6,
                    surprise_factor=0.55,
                    tickers=["US.AAPL"],
                    affected_universe_overlap=0.4,
                )
            )
        assert d.route == "trading_room"
        assert "LLM tie-break" in d.reason
    finally:
        set_router(None)


@pytest.mark.asyncio
async def test_llm_misclassification_falls_back_to_morning_brief() -> None:
    set_router(_FakeRouter(text="please-buy-everything"))  # type: ignore[arg-type]
    try:
        async with _enabled_flag():
            d = await triage(
                _evt(
                    regime_change_score=0.6,
                    surprise_factor=0.5,
                    tickers=["US.AAPL"],
                    affected_universe_overlap=0.4,
                )
            )
        assert d.route == "morning_brief_only"
        assert "unparseable" in d.reason
    finally:
        set_router(None)


@pytest.mark.asyncio
async def test_cost_breaker_open_defaults_to_drop() -> None:
    set_router(_FakeRouter(cost_skipped=True))  # type: ignore[arg-type]
    try:
        async with _enabled_flag():
            d = await triage(
                _evt(
                    regime_change_score=0.6,
                    surprise_factor=0.5,
                    tickers=["US.AAPL"],
                    affected_universe_overlap=0.4,
                )
            )
        assert d.route == "drop"
        assert d.cost_skipped is True
    finally:
        set_router(None)


@pytest.mark.asyncio
async def test_flag_disabled_drops_everything_high_impact() -> None:
    # Even max-signal events drop when the feature flag is OFF.
    reset_for_test()
    d = await triage(_evt())
    assert d.route == "drop"
    assert d.reason == "flag_disabled"


@pytest.mark.asyncio
async def test_empty_payload_drops_safely() -> None:
    async with _enabled_flag():
        d = await triage({})
    assert d.route == "drop"


@pytest.mark.asyncio
async def test_decision_serializes_to_dict_with_required_fields() -> None:
    async with _enabled_flag():
        d = await triage(_evt())
    out = d.to_dict()
    assert out["schema"] == "triage.decision.v1"
    assert out["route"] == "trading_room"
    assert "regime_change_score" in out
    assert "affected_universe" in out
    assert out["affected_universe"] == ["US.SPY", "US.QQQ"]
