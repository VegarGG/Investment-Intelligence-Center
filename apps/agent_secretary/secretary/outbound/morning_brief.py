"""Morning brief composer (workflow 15 §5.1).

Pro-tier composition. Inputs: intel.brief.v1 (Intelligence) + ranked
day's advices + previous evening's leaderboard delta. Tone is loaded from
KV per recipient (defaults to `conv`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from llm_client import ChatMessage, chat
from prompts import get
from schema import IntelBriefV1, SecretaryNotifyV1

from ..tone import Tone, suffix
from .compose_helpers import (
    char_truncate,
    ensure_disclaimer,
    strip_html,
)


async def compose(
    *,
    intel_brief: IntelBriefV1 | None,
    top_advices_md: str,
    leaderboard_md: str,
    tone: Tone = "conv",
    language: Literal["en", "zh"] = "en",
) -> SecretaryNotifyV1:
    digest_md = intel_brief.markdown if intel_brief else "(no upstream brief today)"
    rendered = get(
        "secretary.brief.morning",
        digest_md=digest_md,
        top_advices_md=top_advices_md or "(no advices today)",
        leaderboard_md=leaderboard_md or "(leaderboard pending)",
        language=language,
    )
    response = await chat(
        caller_id="secretary.brief.morning",
        messages=[
            ChatMessage(
                role="system",
                content=f"{rendered.system or ''}\n\nTONE: {suffix(tone)}",
            ),
            ChatMessage(role="user", content=rendered.user),
        ],
        max_tokens=1500,
        temperature=0.3,
    )
    body = ensure_disclaimer(strip_html(response.text.strip()), language=language)
    body = char_truncate(body)
    return SecretaryNotifyV1(
        severity="info",
        channel_hint="briefs",
        language=language,
        markdown=body,
    )


def utc_now() -> datetime:
    return datetime.now(UTC)
