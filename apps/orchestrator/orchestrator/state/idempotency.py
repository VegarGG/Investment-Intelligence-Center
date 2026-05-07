"""Per-DAG-run idempotency cache (workflow 06 §6.6).

Key: (dag_id, trigger_kind, trigger_at). 24h TTL. Repeat fires within
the window are no-ops; users can bypass with `force=true` on /run.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

log = logging.getLogger(__name__)

DEFAULT_TTL_S = 24 * 3600


class IdempotencyStore(Protocol):
    async def set(
        self,
        name: str,
        value: str,
        *,
        nx: bool = False,
        ex: int | None = None,
    ) -> bool | None: ...


class InMemoryIdempotencyStore:
    """For tests."""

    def __init__(self) -> None:
        self._d: dict[str, str] = {}

    async def set(
        self,
        name: str,
        value: str,
        *,
        nx: bool = False,
        ex: int | None = None,
    ) -> bool | None:
        if nx and name in self._d:
            return None
        self._d[name] = value
        return True


def idempotency_key(dag_id: str, trigger_kind: str, trigger_at: str) -> str:
    return f"orch:idem:{dag_id}:{trigger_kind}:{trigger_at}"


async def claim_or_skip(
    store: IdempotencyStore,
    *,
    dag_id: str,
    trigger_kind: str,
    trigger_at: str,
    force: bool = False,
    ttl_s: int = DEFAULT_TTL_S,
) -> bool:
    """Try to claim the run. Returns True if the caller should proceed,
    False if a prior run already claimed this key.

    `force=True` bypasses the cache (e.g., user clicks "regenerate brief").
    """
    if force:
        return True

    key = idempotency_key(dag_id, trigger_kind, trigger_at)
    ok = await store.set(key, "1", nx=True, ex=ttl_s)
    if not ok:
        log.info(
            "idempotency hit — skipping dag=%s trigger=%s at=%s",
            dag_id,
            trigger_kind,
            trigger_at,
        )
        return False
    return True


async def with_idempotency(
    store: IdempotencyStore,
    *,
    dag_id: str,
    trigger_kind: str,
    trigger_at: str,
    force: bool,
    runner: Callable[[], Awaitable[Any]],
    on_skip: Any = None,
) -> Any:
    """Convenience: claim, run, or return on_skip."""
    proceed = await claim_or_skip(
        store, dag_id=dag_id, trigger_kind=trigger_kind, trigger_at=trigger_at, force=force
    )
    if not proceed:
        return on_skip
    return await runner()
