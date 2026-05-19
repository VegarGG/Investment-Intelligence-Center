"""Outbound agent dispatcher (P6.1).

Lets the secretary call other agents over HTTP using a registry mapping
``agent_name -> base_url``. Mirrors the orchestrator's HttpxAgentClient
but stays local to the secretary so the package boundary is clean.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

log = logging.getLogger(__name__)

DEFAULT_REGISTRY: dict[str, str] = {
    "agent_intelligence": "http://iic-agent-intelligence:8081",
    "agent_fundamental": "http://iic-agent-fundamental:8082",
    "agent_quant": "http://iic-agent-quant:8083",
    "agent_persona": "http://iic-agent-persona:8084",
    "agent_backtest": "http://iic-agent-backtest:8085",
    "agent_board": "http://iic-agent-board:8088",
    "orchestrator": "http://iic-orchestrator:8080",
}


class AgentClient(Protocol):
    async def call(self, agent: str, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        ...


@dataclass(slots=True)
class HttpxAgentClient(AgentClient):
    registry: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_REGISTRY))
    timeout_s: float = 30.0

    @classmethod
    def from_env(cls) -> "HttpxAgentClient":
        # Allow `SECRETARY_AGENT_<NAME>=http://...` overrides for dev.
        registry = dict(DEFAULT_REGISTRY)
        for key, val in os.environ.items():
            if key.startswith("SECRETARY_AGENT_") and val:
                name = key[len("SECRETARY_AGENT_") :].lower()
                registry[name] = val
        return cls(registry=registry)

    async def call(self, agent: str, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        base = self.registry.get(agent)
        if base is None:
            raise KeyError(f"unknown agent {agent!r}; known: {sorted(self.registry)}")
        ep = endpoint if endpoint.startswith("/") else "/" + endpoint
        url = f"{base}{ep}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                try:
                    return resp.json()
                except ValueError:
                    return {"_raw": resp.text}
        except httpx.HTTPError as exc:
            log.warning("dispatch failed agent=%s ep=%s: %s", agent, endpoint, exc)
            return {"_error": str(exc), "_status": getattr(exc, "response", None) and exc.response.status_code}


@dataclass(slots=True)
class StubAgentClient(AgentClient):
    """Test client — records calls + returns canned responses."""

    responses: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    calls: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)

    async def call(self, agent: str, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((agent, endpoint, payload))
        return self.responses.get((agent, endpoint), {"status": "ok"})
