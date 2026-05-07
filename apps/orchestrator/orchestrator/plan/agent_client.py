"""Agent HTTP client — the orchestrator calls each agent's /run endpoint
(workflow 06 §6.2). Tests inject a stub.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol


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


class HttpxAgentClient:
    """Production: POST http://<agent>:<port>/run with JSON body. Trace headers
    propagated by the OpenTelemetry httpx instrumentation."""

    def __init__(self, base_urls: dict[str, str], *, timeout_s: float = 60.0) -> None:
        self._base = base_urls
        self._timeout = timeout_s

    async def call(self, agent: str, payload: dict[str, Any]) -> dict[str, Any]:
        import httpx

        url = self._base.get(agent)
        if url is None:
            raise KeyError(f"no base URL configured for agent={agent}")
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(f"{url}/run", json=payload)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            return data
