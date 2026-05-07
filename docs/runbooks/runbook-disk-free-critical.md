# Runbook — DISK_FREE_CRITICAL

`last_verified: 2026-05-07`

## What it means

`/srv/iic` has < 5% free. Postgres will refuse new writes long before the
disk is fully out — cascading failures will follow.

## Likely causes (most → least likely)

1. ChromaDB `news` / `filings` collection grew faster than expected.
2. MinIO bucket retention policy not pruning old snapshots.
3. Loki retention misconfigured (>14 d).
4. A run-away log loop.

## First-look checks (≤ 2 min)

- `df -h /srv/iic`
- `du -sh /srv/iic/* | sort -h | tail`
- Loki: `count_over_time({}[1h])` to spot a noisy emitter.

## Resolution paths

- Path A — prune Loki: lower `retention_period` in
  `infra/observability/loki-config.yml`, restart Loki.
- Path B — vacuum Postgres: `VACUUM (FULL, ANALYZE) lake.eval_runs;`
  for the largest hypertables (only outside trading hours).
- Path C — clear MinIO old snapshots: `mc rb --force --dangerous` only
  on `iic-news-html/snapshots/<old>` paths older than 365 d.

## Verification

- `df -h /srv/iic` reports >15% free.
- Alert clears.

## Postmortem hook

If Postgres halted writes, open a postmortem and include the Loki
saturation trace.
