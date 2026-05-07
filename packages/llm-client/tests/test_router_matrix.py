"""Workflow 03 §2 — every entry in the routing matrix picks the right tier."""

from __future__ import annotations

import pytest
from llm_client._matrix import MATRIX, lookup, resolve_tier
from llm_client.exceptions import UnknownCallerId


class TestMatrixLookup:
    def test_unknown_caller_raises(self) -> None:
        with pytest.raises(UnknownCallerId):
            lookup("does.not.exist")

    def test_persona_slug_collapses_to_daily(self) -> None:
        # persona.<any_slug>.daily → MATRIX["persona.daily"]
        assert lookup("persona.rogers.daily") is MATRIX["persona.daily"]
        assert lookup("persona.buffett.daily") is MATRIX["persona.daily"]

    def test_persona_slug_collapses_to_weekly(self) -> None:
        assert lookup("persona.soros.weekly") is MATRIX["persona.weekly"]


class TestResolveTier:
    def test_intel_synth_always_pro(self) -> None:
        assert resolve_tier("intel.synth", {}) == "pro"

    def test_translate_is_flash(self) -> None:
        assert resolve_tier("intel.crawler.translate", {}) == "flash"

    def test_dedupe_embed_is_embed_tier(self) -> None:
        assert resolve_tier("intel.dedupe.embed", {}) == "embed"

    def test_filings_extract_default_flash(self) -> None:
        assert resolve_tier("fund.filings.extract", {}) == "flash"

    def test_filings_extract_escalates_over_200_pages(self) -> None:
        assert resolve_tier("fund.filings.extract", {"filing_pages": 250}) == "pro"

    def test_filings_extract_does_not_escalate_under_threshold(self) -> None:
        assert resolve_tier("fund.filings.extract", {"filing_pages": 100}) == "flash"

    def test_quant_writer_default_flash(self) -> None:
        assert resolve_tier("quant.writer", {}) == "flash"

    def test_quant_writer_escalates_on_regime_change(self) -> None:
        assert resolve_tier("quant.writer", {"regime_change": True}) == "pro"

    def test_persona_daily_flash(self) -> None:
        assert resolve_tier("persona.rogers.daily", {}) == "flash"

    def test_persona_daily_escalates_on_weekly_deepdive(self) -> None:
        assert resolve_tier("persona.rogers.daily", {"weekly_deepdive": True}) == "pro"

    def test_persona_weekly_always_pro(self) -> None:
        assert resolve_tier("persona.soros.weekly", {}) == "pro"

    def test_secretary_chat_default_flash(self) -> None:
        assert resolve_tier("secretary.chat", {}) == "flash"

    def test_secretary_chat_escalates_explain_deeply(self) -> None:
        assert resolve_tier("secretary.chat", {"explain_deeply": True}) == "pro"

    def test_secretary_chat_escalates_multi_step(self) -> None:
        assert resolve_tier("secretary.chat", {"multi_step_question": True}) == "pro"

    def test_morning_brief_pro(self) -> None:
        assert resolve_tier("secretary.brief.morning", {}) == "pro"

    def test_midday_brief_flash(self) -> None:
        assert resolve_tier("secretary.brief.midday", {}) == "flash"

    def test_orchestrator_plan_pro(self) -> None:
        assert resolve_tier("orchestrator.plan", {}) == "pro"

    def test_backtest_narrate_flash(self) -> None:
        assert resolve_tier("backtest.narrate", {}) == "flash"


class TestMatrixCacheEligibility:
    def test_translate_is_cache_eligible_24h(self) -> None:
        spec = lookup("intel.crawler.translate")
        assert spec.cache_eligible is True
        assert spec.cache_ttl_seconds == 24 * 3600

    def test_sentiment_is_cache_eligible_1h(self) -> None:
        spec = lookup("intel.sentiment.classify")
        assert spec.cache_eligible is True
        assert spec.cache_ttl_seconds == 3600

    def test_synth_not_cache_eligible(self) -> None:
        spec = lookup("intel.synth")
        assert spec.cache_eligible is False

    def test_pro_callers_never_cacheable(self) -> None:
        for caller_id in (
            "intel.synth",
            "fund.valuation",
            "fund.writer",
            "secretary.brief.morning",
            "orchestrator.plan",
        ):
            assert lookup(caller_id).cache_eligible is False
