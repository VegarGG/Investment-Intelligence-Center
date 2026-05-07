"""Shared fixtures for the schema package tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest


@pytest.fixture
def now_utc() -> datetime:
    return datetime(2026, 5, 6, 13, 30, tzinfo=UTC)


@pytest.fixture
def good_long(now_utc: datetime) -> dict[str, Any]:
    """A canonical, valid long advice — every test mutates one field."""
    return {
        "schema": "advice.v1",
        "id": "01HX8E5G7M0000000000000001",
        "agent": "fundamental",
        "issued_at": now_utc.isoformat(),
        "asset": {"kind": "equity", "ticker": "INTC", "venue": "NASDAQ"},
        "thesis": "cyclical bottom; insider buying",
        "direction": "long",
        "confidence": 0.62,
        "entry_band": [89.0, 91.5],
        "target_band": [95.0, 100.0],
        "stop_loss": 85.0,
        "horizon_days": 7,
        "max_drawdown_pct": 6.0,
        "sizing_hint_pct_nav": 2.5,
        "expires_at": (now_utc + timedelta(days=7)).isoformat(),
        "evidence": [{"kind": "news", "ref": "intel.digest.v1#evt-1"}],
    }
