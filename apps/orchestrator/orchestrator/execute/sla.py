"""Soft + hard SLA wrapper (workflow 06 §2.4, §6.3).

Soft = log a warning, continue.
Hard = cancel via asyncio.wait_for, return SLAStub, downstream nodes
       handle stubs gracefully (the secretary brief notes "(N agents
       timed out)").
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .runner import Node, NodeResult  # noqa: F401 — re-exposed type

log = logging.getLogger(__name__)

# Workflow 06 §2.4 SLA table — soft warns, hard cancels.
SLA_TABLE: dict[str, tuple[float, float]] = {
    "intel.synth": (60.0, 120.0),
    "fundamental.run": (45.0, 90.0),
    "quant.run": (30.0, 60.0),
    "persona.daily": (30.0, 90.0),
    "persona.weekly": (60.0, 180.0),
    "secretary.compose_brief": (30.0, 60.0),
    "secretary.chat": (8.0, 20.0),
    # v2.5 T1.5 — auxiliary DAG SLAs.
    "backtest.daily": (60.0, 180.0),
    "backtest.weekly_eval": (120.0, 300.0),
}


@dataclass(frozen=True, slots=True)
class SLAStub:
    """Sentinel returned when a node hits its hard timeout. Downstream
    nodes should detect this and degrade gracefully rather than fail."""

    node_name: str
    reason: str = "hard_timeout"


def lookup_sla(node_name: str) -> tuple[float, float] | None:
    """Return (soft_s, hard_s) for `node_name`, or None if not in the table."""
    if node_name in SLA_TABLE:
        return SLA_TABLE[node_name]
    # Persona slugs collapse: persona.rogers.daily → persona.daily.
    if node_name.startswith("persona.") and node_name.endswith(".daily"):
        return SLA_TABLE["persona.daily"]
    if node_name.startswith("persona.") and node_name.endswith(".weekly"):
        return SLA_TABLE["persona.weekly"]
    return None


async def with_sla_timeout(
    node: Node[Any],
    state: Any,
    *,
    on_alert: Callable[[str, str], Awaitable[None]] | None = None,
) -> tuple[bool, Any, str | None, bool]:
    """Run node.fn(state) under its declared SLA.

    Returns (ok, output, error_msg, timed_out). When the hard timeout
    fires, output is an SLAStub and `on_alert(node_name, message)` is
    awaited so the orchestrator can publish ops.alert.v1.
    """
    soft_s = node.soft_timeout_s
    hard_s = node.hard_timeout_s
    if hard_s is None:
        # Fall back to the canonical SLA table.
        sla = lookup_sla(node.name)
        if sla is not None:
            soft_s, hard_s = sla

    if hard_s is None:
        # No SLA declared — run unbounded. Caller can still pass overall
        # DAG timeout via the runner.
        try:
            output = await node.fn(state)
            return True, output, None, False
        except Exception as exc:
            return False, None, str(exc), False

    soft_task: asyncio.Task[None] | None = None
    if soft_s is not None and soft_s < hard_s:
        soft_task = asyncio.create_task(_soft_warn(node.name, soft_s))

    try:
        output = await asyncio.wait_for(node.fn(state), timeout=hard_s)
        return True, output, None, False
    except TimeoutError:
        msg = f"node {node.name} exceeded hard timeout {hard_s}s"
        log.warning(msg)
        if on_alert is not None:
            await on_alert(node.name, msg)
        return False, SLAStub(node_name=node.name), msg, True
    except Exception as exc:
        return False, None, str(exc), False
    finally:
        if soft_task is not None:
            soft_task.cancel()


async def _soft_warn(node_name: str, soft_s: float) -> None:
    try:
        await asyncio.sleep(soft_s)
        log.warning("node %s exceeded soft timeout %ss — still running", node_name, soft_s)
    except asyncio.CancelledError:
        pass  # node finished before the soft window — silent
