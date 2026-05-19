"""FRED macro source (P2.8).

Pulls a configurable list of FRED series and emits one ``MacroRelease``
per latest observation. Configuration lives in ``infra/intel/macro-series.yaml``
or via ``IIC_MACRO_SERIES`` env (comma-separated series IDs).

Auth: ``FRED_API_KEY`` env. Without a key the source returns an empty
list (and logs once); we never inject a synthetic value.

Cadence: hourly during business hours; called by the cron registered in
P2.9 (``intel_macro_pull``).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import yaml

from .protocol import MacroRelease, MacroSource

log = logging.getLogger(__name__)

UrlFetcher = Callable[[str], Awaitable[dict[str, Any]]]

DEFAULT_SERIES = (
    "CPIAUCSL",  # CPI All Urban Consumers, SA
    "CORESTICKM159SFRBATL",  # Sticky-price CPI core
    "PAYEMS",  # Non-farm payrolls
    "UMCSENT",  # U-Mich consumer sentiment
    "GS10",  # 10-year treasury constant maturity
    "GS2",  # 2-year treasury constant maturity
    "M2SL",  # M2 money stock
    "INDPRO",  # Industrial production index
    "DTWEXBGS",  # Trade-weighted USD index
    "BAMLH0A0HYM2",  # ICE BofA HY OAS
)


async def _httpx_json(url: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


def _load_series_from_yaml() -> tuple[str, ...]:
    repo_yaml = Path(os.environ.get("IIC_MACRO_SERIES_YAML", "infra/intel/macro-series.yaml"))
    if repo_yaml.is_file():
        raw = yaml.safe_load(repo_yaml.read_text()) or {}
        series = raw.get("fred") if isinstance(raw, dict) else None
        if isinstance(series, list) and series:
            return tuple(str(s) for s in series)
    env = os.environ.get("IIC_MACRO_SERIES")
    if env:
        return tuple(s.strip() for s in env.split(",") if s.strip())
    return DEFAULT_SERIES


class FredMacroSource(MacroSource):
    """MacroSource that fetches the latest observation per series from FRED."""

    __slots__ = ("_api_key", "_series", "_fetch_json")

    def __init__(
        self,
        api_key: str,
        *,
        series: tuple[str, ...] = DEFAULT_SERIES,
        fetch_json: UrlFetcher | None = None,
    ) -> None:
        self._api_key = api_key
        self._series = series
        self._fetch_json = fetch_json or _httpx_json

    @classmethod
    def from_env(cls) -> "FredMacroSource":
        key = os.environ.get("FRED_API_KEY", "")
        return cls(api_key=key, series=_load_series_from_yaml())

    async def fetch(self, asof: datetime) -> list[MacroRelease]:
        if not self._api_key:
            log.warning("FredMacroSource: FRED_API_KEY not set; returning empty")
            return []
        out: list[MacroRelease] = []
        for series_id in self._series:
            url = (
                "https://api.stlouisfed.org/fred/series/observations"
                f"?series_id={series_id}&api_key={self._api_key}"
                "&file_type=json&sort_order=desc&limit=1"
            )
            try:
                blob = await self._fetch_json(url)
            except httpx.HTTPError as exc:
                log.warning("FRED fetch failed for %s: %s", series_id, exc)
                continue
            obs = (blob.get("observations") or [{}])[0]
            if not obs:
                continue
            raw_value = obs.get("value")
            if raw_value in (None, "", "."):
                continue
            try:
                value = float(raw_value)
            except ValueError:
                continue
            released_raw = obs.get("date")
            try:
                released = datetime.strptime(released_raw, "%Y-%m-%d").replace(tzinfo=UTC)
            except (TypeError, ValueError):
                released = asof
            out.append(
                MacroRelease(
                    source="fred",
                    series=series_id,
                    released_at=released,
                    value=value,
                )
            )
        return [r for r in out if r.released_at <= asof]
