"""Post-trade narrative composer (workflow 14 §5.3).

Flash tier; ≤80 words; banned hyperbole. Tests assert the banned-word filter.
"""

from __future__ import annotations

from llm_client import ChatMessage, chat

from .types import Position

BANNED_WORDS = ("crushed", "epic", "moonshot", "destroyed", "annihilated")


class HypeDetected(ValueError):
    """The Flash narrative slipped a banned hyperbolic word."""


async def compose(position: Position) -> str:
    if position.state != "closed":
        raise ValueError("narrate.compose requires a closed position")
    response = await chat(
        caller_id="backtest.narrate",
        messages=[
            ChatMessage(
                role="system",
                content=(
                    "Write ≤80 words. Factual recap. No hyperbole "
                    "(forbidden: crushed, epic, moonshot, destroyed)."
                ),
            ),
            ChatMessage(
                role="user",
                content=(
                    f"ticker={position.ticker} dir={position.direction} "
                    f"entry={position.fill_px:.2f} exit={position.exit_px} "
                    f"reason={position.exit_reason} pnl_r={position.pnl_r:.2f}"
                ),
            ),
        ],
        max_tokens=200,
        temperature=0.2,
    )
    text = response.text.strip()
    lower = text.lower()
    for word in BANNED_WORDS:
        if word in lower:
            raise HypeDetected(f"narrative contained banned word {word!r}")
    return text
