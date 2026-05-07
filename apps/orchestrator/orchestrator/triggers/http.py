"""HTTP /run/{dag_id} surface — manual kicks from the dashboard or operator."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from .types import Trigger


async def from_http(
    on_trigger: Callable[[Trigger], Awaitable[Any]],
    dag_id: str,
    body: dict[str, Any] | None = None,
    *,
    force: bool = False,
) -> Any:
    """Adapt an HTTP POST /run/{dag_id} into a Trigger.

    `force=true` query param bypasses the idempotency cache (workflow 06 §9
    risk #5 — user clicking 'regenerate brief' is a legitimate re-run)."""
    trigger = Trigger(
        kind="http",
        name=f"http:{dag_id}",
        fired_at=datetime.now(),
        payload=body or {},
        force=force,
    )
    return await on_trigger(trigger)
