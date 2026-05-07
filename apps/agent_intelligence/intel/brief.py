"""WeChat brief composer (workflow 10 §5.9). Pro tier; produces 200-400
word markdown bounded at 4096 chars."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from llm_client import ChatMessage, chat
from prompts import get
from schema import IntelBriefV1, IntelDigestV1

WECHAT_LIMIT = 4096
TRUNCATE_LINK = "\n\n…[more on dashboard →]"
DISCLAIMER_EN = "*For personal research only. Not investment advice.*"
DISCLAIMER_ZH = "*仅供个人研究，不构成投资建议*"


async def compose(
    digest: IntelDigestV1,
    *,
    audience: Literal["principal", "family"] = "principal",
    language: Literal["en", "zh"] = "en",
) -> IntelBriefV1:
    rendered = get(
        "secretary.brief.morning",
        digest_md=_digest_summary(digest),
        top_advices_md="(no advices emitted yet — pre-fundamental cycle)",
        leaderboard_md="(leaderboard pending; emitted weekly by backtester)",
        language=language,
    )
    response = await chat(
        caller_id="secretary.brief.morning",
        messages=[
            ChatMessage(role="system", content=rendered.system or ""),
            ChatMessage(role="user", content=rendered.user),
        ],
        max_tokens=1200,
        temperature=0.3,
    )
    markdown = _normalize(response.text, language=language)
    return IntelBriefV1(
        issued_at=datetime.now(UTC),
        audience=audience,
        language=language,
        markdown=markdown,
        char_count=len(markdown),
        wechat_safe=True,
    )


def _normalize(markdown: str, *, language: str) -> str:
    """WeCom-safe: strip HTML, ensure footer disclaimer, char-aware truncate."""
    text = markdown.strip()
    text = _strip_html(text)
    disclaimer = DISCLAIMER_ZH if language == "zh" else DISCLAIMER_EN
    if disclaimer not in text:
        text = f"{text}\n\n{disclaimer}"
    return _char_truncate(text, WECHAT_LIMIT)


def _strip_html(text: str) -> str:
    out: list[str] = []
    in_tag = False
    for ch in text:
        if ch == "<":
            in_tag = True
            continue
        if ch == ">":
            in_tag = False
            continue
        if not in_tag:
            out.append(ch)
    return "".join(out)


def _digest_summary(digest: IntelDigestV1) -> str:
    """Compact, LLM-friendly digest summary — kept short to leave room for prose."""
    head = f"Macro regime: {digest.macro_regime}\nMacro thesis: {digest.macro_thesis}\n\n"
    rows = [f"{ev.rank}. **{ev.headline}** — {ev.why_it_matters}" for ev in digest.events[:15]]
    return head + "\n".join(rows)


def _char_truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    keep = limit - len(TRUNCATE_LINK)
    if keep <= 0:
        return text[:limit]
    return text[:keep] + TRUNCATE_LINK
