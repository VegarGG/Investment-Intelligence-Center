"""Title + body translation via the llm_client (workflow 10 §5.4).

Caller_id `intel.crawler.translate` is registered in the routing matrix
as Flash-tier with a 24h cache. Skip translation when source language is
already English.
"""

from __future__ import annotations

from llm_client import ChatMessage, chat

from .types import RawEvent

_PROMPT = (
    "Translate the following news headline and body to English. "
    "Preserve numbers, tickers, and named entities exactly. "
    "Output two lines: the first is the translated headline, the second is the body."
)


async def translate(event: RawEvent) -> tuple[str, str]:
    """Returns (title_en, body_en). Pass-through for `lang == "en"`."""
    if event.lang.lower() == "en":
        return event.title, event.body

    user_msg = f"Headline: {event.title}\n\nBody: {event.body}"
    response = await chat(
        caller_id="intel.crawler.translate",
        messages=[
            ChatMessage(role="system", content=_PROMPT),
            ChatMessage(role="user", content=user_msg),
        ],
        max_tokens=1500,
        temperature=0.0,
    )
    return _split_translation(response.text, fallback_title=event.title, fallback_body=event.body)


def _split_translation(text: str, *, fallback_title: str, fallback_body: str) -> tuple[str, str]:
    parts = [p.strip() for p in text.strip().splitlines() if p.strip()]
    if not parts:
        return fallback_title, fallback_body
    title = parts[0]
    body = "\n".join(parts[1:]) or fallback_body
    return title, body
