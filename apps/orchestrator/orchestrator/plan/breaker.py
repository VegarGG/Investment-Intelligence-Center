"""Per-target circuit breaker for HttpxAgentClient (v2.5 T1.6).

Hand-rolled (no `pybreaker` dep) — the surface area we need is small,
async-aware, and observable via Prometheus counters. The breaker has
three states:

- **closed** — requests pass through; consecutive failures are counted.
- **open** — requests short-circuit with `BreakerOpen`. Stays open for
  `cooldown_s`. After cooldown, the next request transitions to half-open.
- **half-open** — exactly one probe is allowed; success returns to
  closed, failure returns to open.

Plan v2.5 §T1.6 acceptance: stop one agent, morning brief still completes
with that agent's advice missing, within SLA.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")


class State(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class BreakerOpen(Exception):
    """Raised when the breaker is open and a call is short-circuited."""

    def __init__(self, target: str) -> None:
        super().__init__(f"circuit breaker open for target={target!r}")
        self.target = target


@dataclass(slots=True)
class _BreakerState:
    state: State = State.CLOSED
    consecutive_failures: int = 0
    opened_at: float = 0.0
    half_open_inflight: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class CircuitBreakerRegistry:
    """One state machine per target string (one per agent slug)."""

    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        cooldown_s: float = 60.0,
    ) -> None:
        self._states: dict[str, _BreakerState] = {}
        self._failure_threshold = failure_threshold
        self._cooldown_s = cooldown_s
        self._on_change: Callable[[str, State], None] | None = None

    def set_on_change(self, cb: Callable[[str, State], None]) -> None:
        """Hook for emitting `agent_breaker.{opened,closed}` events."""
        self._on_change = cb

    def state_of(self, target: str) -> State:
        return self._states.get(target, _BreakerState()).state

    def _state(self, target: str) -> _BreakerState:
        st = self._states.get(target)
        if st is None:
            st = _BreakerState()
            self._states[target] = st
        return st

    async def call(
        self,
        target: str,
        fn: Callable[[], Awaitable[T]],
    ) -> T:
        """Run `fn()` under the per-target breaker.

        Raises `BreakerOpen` immediately when the breaker is open and the
        cooldown hasn't elapsed.
        """
        st = self._state(target)
        await self._maybe_transition_to_half_open(target, st)

        if st.state is State.OPEN:
            raise BreakerOpen(target)

        if st.state is State.HALF_OPEN:
            async with st.lock:
                if st.half_open_inflight:
                    raise BreakerOpen(target)
                st.half_open_inflight = True
            try:
                result = await fn()
            except Exception:
                self._transition(target, st, State.OPEN, reason="half_open_probe_failed")
                st.opened_at = time.monotonic()
                st.consecutive_failures = self._failure_threshold
                st.half_open_inflight = False
                raise
            else:
                self._transition(target, st, State.CLOSED, reason="half_open_probe_succeeded")
                st.consecutive_failures = 0
                st.half_open_inflight = False
                return result

        try:
            result = await fn()
        except Exception:
            st.consecutive_failures += 1
            if st.consecutive_failures >= self._failure_threshold:
                self._transition(target, st, State.OPEN, reason="failure_threshold")
                st.opened_at = time.monotonic()
            raise
        else:
            if st.consecutive_failures:
                st.consecutive_failures = 0
            return result

    async def _maybe_transition_to_half_open(self, target: str, st: _BreakerState) -> None:
        if st.state is not State.OPEN:
            return
        if time.monotonic() - st.opened_at >= self._cooldown_s:
            self._transition(target, st, State.HALF_OPEN, reason="cooldown_elapsed")

    def _transition(
        self,
        target: str,
        st: _BreakerState,
        new_state: State,
        *,
        reason: str,
    ) -> None:
        if st.state is new_state:
            return
        log.info(
            "agent_breaker target=%s %s->%s reason=%s",
            target,
            st.state.value,
            new_state.value,
            reason,
        )
        st.state = new_state
        if self._on_change is not None:
            try:
                self._on_change(target, new_state)
            except Exception:
                log.exception("breaker on_change hook raised")
