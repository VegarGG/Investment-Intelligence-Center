"""Agent HTTP client — the orchestrator calls each agent's /run endpoint
(workflow 06 §6.2). Tests inject a stub.

v2.5 T1.6 — `HttpxAgentClient` is wrapped by a per-agent circuit breaker.
When the breaker is open, the client returns
``{"advices": [], "_breaker_open": True, "_target": agent}`` so fan-out
legs degrade gracefully and the morning brief still ships.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from .breaker import BreakerOpen, CircuitBreakerRegistry, State

log = logging.getLogger(__name__)


class AgentClient(Protocol):
    async def call(self, agent: str, payload: dict[str, Any]) -> dict[str, Any]: ...


class StubAgentClient:
    """In-memory client — used by the morning-brief DAG test."""

    def __init__(
        self,
        responses: dict[str, dict[str, Any]] | None = None,
        delay_fns: dict[str, Callable[[], Awaitable[None]]] | None = None,
    ) -> None:
        self._responses = responses or {}
        self._delays = delay_fns or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call(self, agent: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((agent, payload))
        if agent in self._delays:
            await self._delays[agent]()
        return self._responses.get(agent, {"agent": agent, "ok": True})


def _breaker_open_response(agent: str) -> dict[str, Any]:
    """Graceful-degrade payload returned when the breaker is open.

    Plan v2.5 §T1.6: morning brief should still complete with that
    agent's advice missing — keep the keys downstream nodes already
    look at (`advices` array; `ok` flag) so no node has to special-case
    breaker-open responses.
    """
    return {
        "agent": agent,
        "ok": False,
        "advices": [],
        "_breaker_open": True,
        "_target": agent,
    }


class HttpxAgentClient:
    """Production: POST http://<agent>:<port>/run with JSON body. Trace headers
    propagated by the OpenTelemetry httpx instrumentation.

    Wraps each call in a per-agent circuit breaker (v2.5 T1.6). Breaker
    state is observable via the `breaker` attribute and the `agent_breaker.*`
    log lines.
    """

    def __init__(
        self,
        base_urls: dict[str, str],
        *,
        timeout_s: float = 60.0,
        failure_threshold: int = 5,
        breaker_cooldown_s: float = 60.0,
        breaker: CircuitBreakerRegistry | None = None,
    ) -> None:
        self._base = base_urls
        self._timeout = timeout_s
        self.breaker = breaker or CircuitBreakerRegistry(
            failure_threshold=failure_threshold,
            cooldown_s=breaker_cooldown_s,
        )

    async def call(self, agent: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = self._base.get(agent)
        if url is None:
            raise KeyError(f"no base URL configured for agent={agent}")

        async def _send() -> dict[str, Any]:
            import httpx

            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(f"{url}/run", json=payload)
                resp.raise_for_status()
                data: dict[str, Any] = resp.json()
                return data

        try:
            return await self.breaker.call(agent, _send)
        except BreakerOpen:
            log.info("agent_breaker target=%s short-circuited; degrading", agent)
            return _breaker_open_response(agent)

    def breaker_state(self, agent: str) -> State:
        return self.breaker.state_of(agent)
