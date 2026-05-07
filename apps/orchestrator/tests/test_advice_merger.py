"""Workflow 06 §6.5 — advice merger validates, normalizes, persists."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from orchestrator.merge.advice_merger import AdviceMerger
from orchestrator.merge.normalizer import canonical_ticker


def _good_advice() -> dict[str, Any]:
    issued = datetime(2026, 5, 7, 13, 30, tzinfo=UTC)
    return {
        "schema": "advice.v1",
        "id": "01HX8E5G7M0000000000000001",
        "agent": "fundamental",
        "issued_at": issued.isoformat(),
        "asset": {"kind": "equity", "ticker": "intc", "venue": "NASDAQ"},
        "thesis": "stub",
        "direction": "long",
        "confidence": 0.5,
        "entry_band": [89.0, 91.5],
        "target_band": [95.0, 100.0],
        "stop_loss": 85.0,
        "horizon_days": 7,
        "max_drawdown_pct": 6.0,
        "sizing_hint_pct_nav": 2.5,
        "expires_at": (issued + timedelta(days=7)).isoformat(),
        "evidence": [{"kind": "news", "ref": "intel.digest.v1#evt-1"}],
    }


class TestNormalizer:
    def test_canonical_uppercases(self) -> None:
        assert canonical_ticker("intc") == "INTC"

    def test_canonical_strips(self) -> None:
        assert canonical_ticker("  AAPL  ") == "AAPL"

    def test_dotted_ticker_ok(self) -> None:
        assert canonical_ticker("BRK.B") == "BRK.B"

    def test_invalid_rejected(self) -> None:
        with pytest.raises(ValueError):
            canonical_ticker("not a ticker!")


class TestMerger:
    @pytest.mark.asyncio
    async def test_accepts_valid_advice(self) -> None:
        appended: list[dict[str, Any]] = []
        alerts: list[dict[str, Any]] = []

        async def append_fn(p: dict[str, Any]) -> None:
            appended.append(p)

        async def alert_fn(p: dict[str, Any]) -> None:
            alerts.append(p)

        merger = AdviceMerger(append_fn=append_fn, alert_fn=alert_fn, now_fn=lambda: 0.0)
        result = await merger.merge(_good_advice())
        assert result.accepted == 1
        assert len(appended) == 1
        # ticker normalized
        assert appended[0]["asset"]["ticker"] == "INTC"
        assert alerts == []

    @pytest.mark.asyncio
    async def test_rejects_persona_without_disclaimer(self) -> None:
        appended: list[dict[str, Any]] = []
        alerts: list[dict[str, Any]] = []

        async def append_fn(p: dict[str, Any]) -> None:
            appended.append(p)

        async def alert_fn(p: dict[str, Any]) -> None:
            alerts.append(p)

        bad = _good_advice()
        bad["agent"] = "persona.rogers"
        # no disclaimer

        merger = AdviceMerger(append_fn=append_fn, alert_fn=alert_fn, now_fn=lambda: 0.0)
        result = await merger.merge(bad)
        assert result.quarantined == 1
        assert appended == []
        assert len(alerts) == 1
        assert alerts[0]["code"] == "ADVICE_VALIDATION_FAILED"

    @pytest.mark.asyncio
    async def test_rate_limits_advice_bombs(self) -> None:
        """Workflow 06 §9 risk #8 — > 10 advices per minute per agent get dropped."""
        appended: list[dict[str, Any]] = []
        alerts: list[dict[str, Any]] = []

        async def append_fn(p: dict[str, Any]) -> None:
            appended.append(p)

        async def alert_fn(p: dict[str, Any]) -> None:
            alerts.append(p)

        merger = AdviceMerger(append_fn=append_fn, alert_fn=alert_fn, now_fn=lambda: 0.0)
        # Push 12 in the same "minute" — last 2 should be rate-limited.
        for i in range(12):
            advice = _good_advice()
            advice["id"] = f"01HX8E5G7M00000000000000{i:02d}"
            await merger.merge(advice)
        assert len(appended) == 10
        rate_limit_alerts = [a for a in alerts if a["code"] == "ADVICE_RATE_LIMITED"]
        assert len(rate_limit_alerts) == 2
