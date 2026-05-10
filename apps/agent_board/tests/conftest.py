"""Shared fixtures + LLM stub for board tests."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import ulid
from llm_client.router import set_router
from llm_client.types import ChatMessage, ChatResponse
from schema.advice import Asset, Evidence
from schema.plan import PlanV1


@dataclass(slots=True)
class StubRouter:
    """Deterministic router. Maps caller_id substring → response text."""

    responses: dict[str, str]
    cost_skipped_callers: set[str]

    async def chat(
        self,
        caller_id: str,
        messages: list[ChatMessage],
        **_kw: Any,
    ) -> ChatResponse:
        text = self._pick(caller_id)
        return ChatResponse(
            text=text,
            model="stub",
            tier="flash",
            prompt_tokens=10,
            completion_tokens=10,
            cost_usd=0.0,
            cached=False,
            fallback_used=False,
            cost_skipped=False,
            request_id="stub",
            latency_ms=1,
        )

    async def chat_or_skip(
        self,
        caller_id: str,
        messages: list[ChatMessage],
        **_kw: Any,
    ) -> ChatResponse:
        if any(c in caller_id for c in self.cost_skipped_callers):
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
                request_id="skip",
                latency_ms=0,
            )
        return await self.chat(caller_id, messages)

    def _pick(self, caller_id: str) -> str:
        for key, text in self.responses.items():
            if key in caller_id:
                return text
        return ""


@pytest.fixture
def stub_router() -> Iterator[StubRouter]:
    router = StubRouter(responses={}, cost_skipped_callers=set())
    set_router(router)  # type: ignore[arg-type]
    try:
        yield router
    finally:
        set_router(None)


@pytest.fixture
def sample_plans() -> list[PlanV1]:
    asset = Asset(kind="equity", ticker="US.AAPL", venue="NASDAQ")
    when = datetime(2026, 5, 10, 12, 0, tzinfo=UTC)

    return [
        PlanV1(
            id=str(ulid.ULID()),
            team="quant",
            persona_slug=None,
            issued_at=when,
            asset=asset,
            action="buy",
            entry_price=100.0,
            entry_window_open=when,
            entry_window_close=when + timedelta(hours=4),
            target_price=110.0,
            stop_loss=95.0,
            max_drawdown_pct=10.0,
            horizon_days=21,
            sizing_pct_nav=2.0,
            confidence=0.65,
            thesis="Quant net z = 0.7. Momentum + value carry.",
            evidence=[Evidence(kind="factor", ref="quant.momentum")],
            expires_at=when + timedelta(days=21),
        ),
        PlanV1(
            id=str(ulid.ULID()),
            team="fundamental",
            persona_slug=None,
            issued_at=when,
            asset=asset,
            action="buy",
            entry_price=100.0,
            entry_window_open=when,
            entry_window_close=when + timedelta(days=2),
            target_price=130.0,
            stop_loss=80.0,
            max_drawdown_pct=12.0,
            horizon_days=180,
            sizing_pct_nav=3.5,
            confidence=0.70,
            thesis="10-Q margin of safety to fair value $130.",
            evidence=[Evidence(kind="filing", ref="filing.AAPL_10Q")],
            expires_at=when + timedelta(days=180),
        ),
        PlanV1(
            id=str(ulid.ULID()),
            team="persona",
            persona_slug="consensus",
            issued_at=when,
            asset=asset,
            action="hold",
            entry_price=100.0,
            entry_window_open=when,
            entry_window_close=when + timedelta(hours=24),
            target_price=100.0,
            stop_loss=100.0,
            max_drawdown_pct=15.0,
            horizon_days=30,
            sizing_pct_nav=0.0,
            confidence=0.30,
            thesis="Persona panel split — flat.",
            evidence=[],
            disclaimer="Not advice; persona consensus rollup.",
            expires_at=when + timedelta(days=30),
        ),
    ]
