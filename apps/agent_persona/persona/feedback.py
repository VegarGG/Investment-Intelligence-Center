"""Backtest feedback consumer (workflow 13 §5.4).

Subscribes to backtest.fill.v1, attaches the outcome to the matching memory,
and Pro-distills a one-line lesson stored as a separate `lesson` entry.
"""

from __future__ import annotations

from datetime import UTC, datetime

import ulid
from llm_client import ChatMessage, chat
from schema import BacktestFillV1

from .memory import MemoryStore
from .types import MemoryEntry, PersonaSpec


async def on_fill(
    fill: BacktestFillV1,
    *,
    spec: PersonaSpec,
    memory: MemoryStore,
) -> MemoryEntry | None:
    if not fill.agent.endswith(spec.slug):
        return None  # not this persona's trade

    await memory.update_pnl(spec.slug, fill.advice_id, fill.pnl_r)

    response = await chat(
        caller_id=f"persona.{spec.slug}.weekly",
        messages=[
            ChatMessage(
                role="system",
                content=(
                    f"You are the persona {spec.display_name}. "
                    "In ≤ 30 words, what would you learn from this trade outcome?"
                ),
            ),
            ChatMessage(
                role="user",
                content=(
                    f"advice_id={fill.advice_id} "
                    f"exit_reason={fill.exit_reason} "
                    f"pnl_r={fill.pnl_r:.2f} "
                    f"narrative={fill.narrative}"
                ),
            ),
        ],
        max_tokens=120,
        temperature=0.3,
    )
    lesson = MemoryEntry(
        doc_id=str(ulid.ULID()),
        text=response.text.strip(),
        kind="lesson",
        pnl_r=fill.pnl_r,
        metadata={
            "indexed_at": datetime.now(UTC).isoformat(),
            "source_advice_id": fill.advice_id,
        },
    )
    await memory.add(spec.slug, lesson)
    return lesson
