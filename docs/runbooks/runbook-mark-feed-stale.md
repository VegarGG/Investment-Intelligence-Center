# Runbook — MARK_FEED_STALE

`last_verified: 2026-05-07`

## What it means

An open virtual position has not received a fresh mark in >5 minutes
during market hours. Backtester P&L and stop-loss detection are degraded
for that ticker until a mark arrives.

## Likely causes (most → least likely)

1. Polygon / Tiingo API outage or 429.
2. ChromaDB or Postgres write stall delaying the timeseries insert.
3. Specific ticker no longer trading (delisted, halt).
4. Network blip to the data provider.

## First-look checks (≤ 2 min)

- `curl https://api.polygon.io/v2/last/trade/<ticker>?apiKey=...`
- `SELECT ticker, max(asof) FROM lake.timeseries WHERE ticker IN (...) GROUP BY 1;`
- Grafana → IIC-005-Trade-Tape → mark age column.

## Resolution paths

- Path A — provider outage: failover to Tiingo (already in the price
  pull chain); confirm Tiingo also unhealthy before paging Polygon support.
- Path B — write stall: `pg_stat_activity` for blocked queries on
  `lake.timeseries`; restart the price-pull worker if needed.
- Path C — halted/delisted ticker: close the position manually (admin
  override per workflow 14 §2.4) with `exit_reason='early_close'`.

## Verification

- Mark age drops below 60 s for affected tickers.

## Postmortem hook

Only if a stop-loss should have fired and didn't — open one with the
fill outcome and the should-have-fired evidence.
