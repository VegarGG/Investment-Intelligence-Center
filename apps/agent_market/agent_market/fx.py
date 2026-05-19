"""FX writer (P4.7).

Pulls end-of-day FX rates for the major pairs from FRED. Cadence:
daily at 18:00 UTC (post-NY close); higher-frequency FX requires a
paid feed and is out of scope for the prototype.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

import httpx

log = logging.getLogger(__name__)

FRED_FX_SERIES: dict[str, str] = {
    "DEXUSEU": "EURUSD",
    "DEXJPUS": "USDJPY",  # FRED inverts JPY relative to others
    "DEXCHUS": "USDCNY",
    "DEXHKUS": "USDHKD",
    "DEXSZUS": "USDCHF",
    "DEXUSUK": "GBPUSD",
}


class FxQuoteWriter:
    """One row per pair per call. Source = 'fred'."""

    __slots__ = ("_sink", "_api_key", "_fetch_json")

    def __init__(self, sink: Any, *, api_key: str | None = None, fetch_json=None) -> None:
        self._sink = sink
        self._api_key = api_key or os.environ.get("FRED_API_KEY", "")
        self._fetch_json = fetch_json or _httpx_json

    async def pull(self) -> int:
        if not self._api_key:
            log.warning("FxQuoteWriter: FRED_API_KEY missing; returning 0")
            return 0
        from .quotes_sink_compat import QuoteTick

        ticks: list[QuoteTick] = []
        for series, ticker in FRED_FX_SERIES.items():
            url = (
                "https://api.stlouisfed.org/fred/series/observations"
                f"?series_id={series}&api_key={self._api_key}"
                "&file_type=json&sort_order=desc&limit=1"
            )
            try:
                blob = await self._fetch_json(url)
            except httpx.HTTPError as exc:
                log.warning("fx fetch %s failed: %s", series, exc)
                continue
            obs = (blob.get("observations") or [{}])[0]
            raw_val = obs.get("value")
            if raw_val in (None, "", "."):
                continue
            try:
                last = float(raw_val)
            except ValueError:
                continue
            ticks.append(
                QuoteTick(
                    ticker=ticker,
                    exch="FX",
                    last=last,
                    src="fred",
                    ts=datetime.now(UTC),
                )
            )
        return await self._sink.insert_batch(ticks)


async def _httpx_json(url: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()
