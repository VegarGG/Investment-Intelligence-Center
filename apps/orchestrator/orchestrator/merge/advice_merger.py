"""Advice merger — validate via schema, normalize, persist via the ledger.

Workflow 06 §6.5. On validation failure we emit ops.alert.v1 and
quarantine the offending payload to /srv/iic/advice_ledger/quarantine/
for human review (the ledger is immutable; rejected advice never lands
in lake.advice).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import orjson

log = logging.getLogger(__name__)

QUARANTINE_DIR = Path("/srv/iic/advice_ledger/quarantine")
DEFAULT_PER_AGENT_RATE_LIMIT = 10  # advices per minute (workflow 06 §9 advice bombs)


@dataclass(slots=True)
class MergeResult:
    accepted: int = 0
    quarantined: int = 0
    rate_limited: int = 0


class _PerAgentRateLimit:
    """Sliding-window counter per agent. Workflow 06 §9 risk: advice bombs."""

    def __init__(self, max_per_minute: int = DEFAULT_PER_AGENT_RATE_LIMIT) -> None:
        self._max = max_per_minute
        self._buckets: dict[str, list[float]] = {}

    def allow(self, agent: str, *, now: float) -> bool:
        cutoff = now - 60.0
        history = self._buckets.setdefault(agent, [])
        # drop expired entries; keep ordered
        self._buckets[agent] = [ts for ts in history if ts >= cutoff]
        if len(self._buckets[agent]) >= self._max:
            return False
        self._buckets[agent].append(now)
        return True


def _quarantine(payload: dict[str, Any], reason: str) -> Path | None:
    """Drop the offending payload to /srv/iic/advice_ledger/quarantine/<id>.json.
    Returns the written path or None when the dir isn't writable (dev mode)."""
    try:
        QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError) as exc:
        log.warning("quarantine path not writable: %s — payload dropped on floor", exc)
        return None
    name = payload.get("id") or f"unknown-{len(list(QUARANTINE_DIR.iterdir()))}"
    target = QUARANTINE_DIR / f"{name}.json"
    body = {"reason": reason, "payload": payload}
    target.write_bytes(orjson.dumps(body, option=orjson.OPT_INDENT_2))
    return target


@dataclass(slots=True)
class AdviceMerger:
    """Stateful merger — call merge() per incoming advice envelope.

    `append_fn` is the persistence callable (production: data_lake.advice_ledger.append).
    `alert_fn` publishes ops.alert.v1 on failures (production: data_bus.publish).
    `now_fn` is the clock — tests inject a fake.
    """

    append_fn: Callable[[dict[str, Any]], Awaitable[Any]]
    alert_fn: Callable[[dict[str, Any]], Awaitable[None]]
    now_fn: Callable[[], float]
    rate_limit: _PerAgentRateLimit = field(default_factory=lambda: _PerAgentRateLimit())

    async def merge(self, payload: dict[str, Any]) -> MergeResult:
        result = MergeResult()
        agent = payload.get("agent", "<unknown>")

        if not self.rate_limit.allow(agent, now=self.now_fn()):
            result.rate_limited = 1
            await self.alert_fn(
                {
                    "schema": "ops.alert.v1",
                    "severity": "warn",
                    "service": "orchestrator.advice_merger",
                    "code": "ADVICE_RATE_LIMITED",
                    "message": f"agent {agent} exceeded {DEFAULT_PER_AGENT_RATE_LIMIT}/min",
                    "context": {"agent": agent, "advice_id": payload.get("id")},
                }
            )
            return result

        # Validate via the canonical Pydantic model.
        try:
            from schema import AdviceV1

            AdviceV1.model_validate(payload)
        except Exception as exc:
            result.quarantined = 1
            quarantine_path = _quarantine(payload, reason=str(exc))
            await self.alert_fn(
                {
                    "schema": "ops.alert.v1",
                    "severity": "warn",
                    "service": "orchestrator.advice_merger",
                    "code": "ADVICE_VALIDATION_FAILED",
                    "message": f"advice from {agent} rejected: {exc}",
                    "context": {
                        "agent": agent,
                        "advice_id": payload.get("id"),
                        "quarantined_at": str(quarantine_path) if quarantine_path else None,
                    },
                }
            )
            return result

        # Normalize the ticker (string hygiene only for v0).
        try:
            from .normalizer import canonical_ticker

            payload["asset"] = {
                **payload["asset"],
                "ticker": canonical_ticker(payload["asset"]["ticker"]),
            }
        except (KeyError, ValueError) as exc:
            result.quarantined = 1
            _quarantine(payload, reason=f"normalizer: {exc}")
            await self.alert_fn(
                {
                    "schema": "ops.alert.v1",
                    "severity": "warn",
                    "service": "orchestrator.advice_merger",
                    "code": "ADVICE_NORMALIZE_FAILED",
                    "message": str(exc),
                    "context": {"agent": agent, "advice_id": payload.get("id")},
                }
            )
            return result

        await self.append_fn(payload)
        result.accepted = 1
        return result
