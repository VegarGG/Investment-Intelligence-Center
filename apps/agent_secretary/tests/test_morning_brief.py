"""Workflow 15 §5.1, §5.7 — morning brief composition + cost-breaker fallback."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from schema import IntelBriefV1
from secretary.outbound.compose_helpers import (
    DISCLAIMER_EN,
    DISCLAIMER_ZH,
    cost_breaker_brief,
)
from secretary.outbound.morning_brief import compose


def _intel_brief(text: str = "## upstream brief", lang: str = "en") -> IntelBriefV1:
    return IntelBriefV1(
        issued_at=datetime.now(UTC),
        audience="principal",
        language=lang,  # type: ignore[arg-type]
        markdown=text,
        char_count=len(text),
        wechat_safe=True,
    )


@pytest.mark.asyncio
async def test_morning_brief_includes_disclaimer() -> None:
    notify = await compose(
        intel_brief=_intel_brief(),
        top_advices_md="- AAPL long 0.7",
        leaderboard_md="quant:1.2",
    )
    assert DISCLAIMER_EN in notify.markdown
    assert notify.channel_hint == "briefs"


@pytest.mark.asyncio
async def test_morning_brief_zh_disclaimer() -> None:
    notify = await compose(
        intel_brief=_intel_brief(text="## 上游简报", lang="zh"),
        top_advices_md="",
        leaderboard_md="",
        language="zh",
    )
    assert DISCLAIMER_ZH in notify.markdown


def test_cost_breaker_brief_is_bilingual_and_no_llm() -> None:
    en = cost_breaker_brief(language="en")
    zh = cost_breaker_brief(language="zh")
    assert "paused" in en.lower()
    assert "暂停" in zh
    assert DISCLAIMER_ZH in zh
