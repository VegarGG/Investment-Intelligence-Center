"""DAG registry — maps trigger.name → DAG entry point.

Workflow 06 §6.1 — every cron + NATS subscription routes through one
`route(trigger)` function which looks up the DAG here.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

# Trigger.name → coroutine that runs the DAG with the trigger payload.
# Concrete entries are registered by main.py at startup once the agent
# client is constructed.
DagEntry = Callable[[Any], Awaitable[Any]]

REGISTRY: dict[str, DagEntry] = {}


def register(trigger_name: str, entry: DagEntry) -> None:
    REGISTRY[trigger_name] = entry


def lookup(trigger_name: str) -> DagEntry | None:
    return REGISTRY.get(trigger_name)


def clear() -> None:
    """Test helper — drop all registrations between cases."""
    REGISTRY.clear()
