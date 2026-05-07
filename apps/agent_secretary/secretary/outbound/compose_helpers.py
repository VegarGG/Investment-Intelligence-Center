"""Shared brief-shaping helpers: WeCom truncation, disclaimer footer, etc."""

from __future__ import annotations

WECHAT_LIMIT = 4096
TRUNCATE_LINK = "\n\n…[more on dashboard →]"
DISCLAIMER_EN = "*For personal research only. Not investment advice.*"
DISCLAIMER_ZH = "*仅供个人研究，不构成投资建议*"

COST_BREAKER_TEXT_EN = (
    "**System paused.** LLM monthly cap reached. "
    "The morning brief is omitted today.\n\n"
    "[See cost dashboard →]"
)
COST_BREAKER_TEXT_ZH = "**系统已暂停。** 已达本月推理上限，今日简报省略。\n\n" "[查看成本面板 →]"


def char_truncate(text: str, limit: int = WECHAT_LIMIT) -> str:
    """Char-aware truncation (workflow 15 §9 — CJK char counting note)."""
    if len(text) <= limit:
        return text
    keep = limit - len(TRUNCATE_LINK)
    if keep <= 0:
        return text[:limit]
    return text[:keep] + TRUNCATE_LINK


def strip_html(text: str) -> str:
    """WeCom rejects HTML inside the markdown msgtype (workflow 15 §9)."""
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


def ensure_disclaimer(text: str, *, language: str) -> str:
    disclaimer = DISCLAIMER_ZH if language == "zh" else DISCLAIMER_EN
    if disclaimer in text:
        return text
    return f"{text.rstrip()}\n\n{disclaimer}"


def cost_breaker_brief(*, language: str = "en") -> str:
    body = COST_BREAKER_TEXT_ZH if language == "zh" else COST_BREAKER_TEXT_EN
    return ensure_disclaimer(body, language=language)
