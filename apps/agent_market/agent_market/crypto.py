"""ccxt-backed crypto quote writer (P4.7).

Cadence: every 60s during weekdays / every 5 min on weekends (crypto
markets never close, but our consumers don't need sub-minute on the
weekend).

Exchanges supported in this minimal cut: Binance + Coinbase. Add more
by extending ``EXCHANGES`` — each entry is a ccxt class name.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

EXCHANGES = ("binance", "coinbase")
DEFAULT_PAIRS = ("BTC/USDT", "ETH/USDT", "SOL/USDT", "BTC/USD", "ETH/USD")


class CryptoQuoteWriter:
    """Pulls ccxt tickers and writes them to `lake.quotes` via a sink."""

    __slots__ = ("_sink", "_pairs", "_clients")

    def __init__(self, sink: Any, pairs: tuple[str, ...] = DEFAULT_PAIRS) -> None:
        self._sink = sink
        self._pairs = pairs
        self._clients: dict[str, Any] = {}

    def _client(self, exchange: str) -> Any:
        client = self._clients.get(exchange)
        if client is None:
            import ccxt.async_support as ccxt_async  # type: ignore[import-not-found]

            cls = getattr(ccxt_async, exchange, None)
            if cls is None:
                raise RuntimeError(f"ccxt has no exchange {exchange}")
            client = cls({"enableRateLimit": True})
            self._clients[exchange] = client
        return client

    async def pull(self) -> int:
        """Pull every (exchange, pair) tuple and return rows written."""
        from .quotes_sink_compat import QuoteTick  # local: avoid hard dep

        ticks: list[Any] = []
        for ex_name in EXCHANGES:
            try:
                client = self._client(ex_name)
            except Exception as exc:  # noqa: BLE001
                log.warning("ccxt: %s unavailable: %s", ex_name, exc)
                continue
            for pair in self._pairs:
                try:
                    tkr = await client.fetch_ticker(pair)
                except Exception as exc:  # noqa: BLE001
                    log.debug("ccxt: %s %s missing: %s", ex_name, pair, exc)
                    continue
                ticks.append(
                    QuoteTick(
                        ticker=pair.replace("/", ""),
                        exch=ex_name.upper(),
                        last=float(tkr.get("last") or 0.0),
                        bid=_maybe_float(tkr.get("bid")),
                        ask=_maybe_float(tkr.get("ask")),
                        vol=_maybe_int(tkr.get("baseVolume")),
                        src=ex_name,
                    )
                )
        return await self._sink.insert_batch(ticks)

    async def close(self) -> None:
        for c in self._clients.values():
            try:
                await c.close()
            except Exception:  # noqa: BLE001
                pass


def _maybe_float(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _maybe_int(v: Any) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None
