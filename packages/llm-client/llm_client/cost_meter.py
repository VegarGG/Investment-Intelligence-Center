"""Cost meter + circuit breaker (workflow 03 §7).

Two budgets: primary (LLM_MONTHLY_CAP_USD, default $90) and fallback
(LLM_FALLBACK_CAP_USD, default $20). The fallback budget governs spend
that occurs while DeepSeek is down and we're routing to Anthropic/Groq —
which is ~5x more expensive at the Pro tier.

State machine: CLOSED → OPEN (cap exceeded) → HALF_OPEN after cooldown.
While OPEN, allow() returns False; the router translates that into
CostBudgetExceeded which the secretary surfaces to the user via WeCom.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from enum import Enum
from typing import Protocol

from llm_client.types import ChatResponse, LlmTier

DEFAULT_MONTHLY_CAP_USD = 90.0
DEFAULT_FALLBACK_CAP_USD = 20.0
DEFAULT_SOFT_FRACTION = 0.8
COOLDOWN_SECONDS = 60 * 60  # 1 hour


class BreakerState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class SpendStore(Protocol):
    """Backend for rolling 30-day spend. Postgres in prod, in-memory in tests."""

    async def total_spend(self, *, since: date, fallback_only: bool = False) -> float: ...

    async def record(
        self, *, day: date, tier: LlmTier, fallback: bool, cost_usd: float
    ) -> None: ...


@dataclass
class InMemorySpendStore:
    rows: dict[tuple[date, LlmTier, bool], float] = field(default_factory=dict)

    async def total_spend(self, *, since: date, fallback_only: bool = False) -> float:
        return sum(
            cost
            for (day, _tier, fb), cost in self.rows.items()
            if day >= since and (not fallback_only or fb)
        )

    async def record(self, *, day: date, tier: LlmTier, fallback: bool, cost_usd: float) -> None:
        key = (day, tier, fallback)
        self.rows[key] = self.rows.get(key, 0.0) + cost_usd


@dataclass
class CostMeter:
    """Wraps a SpendStore with breaker state + soft/hard cap enforcement."""

    store: SpendStore
    monthly_cap_usd: float = DEFAULT_MONTHLY_CAP_USD
    fallback_cap_usd: float = DEFAULT_FALLBACK_CAP_USD
    soft_fraction: float = DEFAULT_SOFT_FRACTION
    cooldown_seconds: int = COOLDOWN_SECONDS

    _state: BreakerState = field(default=BreakerState.CLOSED, init=False)
    _opened_at: float = field(default=0.0, init=False)

    def _now(self) -> float:
        return time.monotonic()

    def _today(self) -> date:
        return datetime.now(UTC).date()

    def _since(self) -> date:
        return self._today() - timedelta(days=30)

    @property
    def state(self) -> BreakerState:
        if self._state == BreakerState.OPEN and (
            self._now() - self._opened_at >= self.cooldown_seconds
        ):
            self._state = BreakerState.HALF_OPEN
        return self._state

    async def allow(self, *, fallback: bool = False) -> bool:
        """Return True if the next call can proceed. Recompute breaker state
        from rolling spend; opens the breaker the moment spend ≥ cap."""
        if self.state == BreakerState.OPEN:
            return False

        spent = await self.store.total_spend(since=self._since())
        if spent >= self.monthly_cap_usd:
            self._open()
            return False

        if fallback:
            fb_spent = await self.store.total_spend(since=self._since(), fallback_only=True)
            if fb_spent >= self.fallback_cap_usd:
                self._open()
                return False

        return True

    async def soft_breach(self) -> bool:
        """True if we're past the soft cap (default 80% of monthly). Caller
        should publish ops.alert.v1 WARN once when this transitions to true."""
        spent = await self.store.total_spend(since=self._since())
        return spent >= self.monthly_cap_usd * self.soft_fraction

    async def record(self, response: ChatResponse) -> None:
        await self.store.record(
            day=self._today(),
            tier=response.tier,
            fallback=response.fallback_used,
            cost_usd=response.cost_usd,
        )

    def _open(self) -> None:
        self._state = BreakerState.OPEN
        self._opened_at = self._now()

    def reset(self) -> None:
        """Manual override for the runbook (workflow 31 §6)."""
        self._state = BreakerState.CLOSED
        self._opened_at = 0.0
