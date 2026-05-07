"""EDGAR poll + fetch — production wiring stub (workflow 11 §5.1).

Real impl uses the SEC's submissions JSON endpoint
(https://data.sec.gov/submissions/CIK<padded>.json) plus the full-text
search API. We expose a protocol so the agent code can run end-to-end in
tests with a fake EDGAR.
"""

from __future__ import annotations

from typing import Protocol

from ..types import Filing


class FilingSource(Protocol):
    async def latest_for(self, ticker: str) -> list[Filing]: ...


class InMemoryFilingSource:
    """Test fixture — replays a fixed filing list per ticker."""

    def __init__(self, filings_by_ticker: dict[str, list[Filing]]) -> None:
        self._by_ticker = {k: list(v) for k, v in filings_by_ticker.items()}

    async def latest_for(self, ticker: str) -> list[Filing]:
        return list(self._by_ticker.get(ticker, []))
