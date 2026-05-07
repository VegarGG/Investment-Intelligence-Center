# Runbook — NVME_WEAR_HIGH / NVME_WEAR_CRITICAL

`last_verified: 2026-05-07`

## What it means

The host NVMe's reported wear-leveling indicator passed 70% (warn) or
80% (critical). At 80% the manufacturer's endurance budget is essentially
spent; replace before failure.

## Likely causes (most → least likely)

1. Heavy ChromaDB rebuilds writing the embedding index repeatedly.
2. Postgres WAL pinned to NVMe (expected; budget for it).
3. A loop spawning excessive log volume (check Loki).

## First-look checks (≤ 2 min)

- `sudo nvme smart-log /dev/nvme0n1 | grep -i percentage_used`
- `iotop -ao` for top writers
- Grafana → IIC-002-Host → "NVMe wear" panel

## Resolution paths

- Path A — order replacement (Samsung 990 EVO Plus 2 TB, ~$130). Schedule
  a swap during the next quarterly maintenance window.
- Path B — interim mitigation: move ChromaDB collections to the NAS
  (per `workflows/01_INFRASTRUCTURE_AND_HOST.md` §5.6 hybrid mode).
- Path C — verify the wear is real, not a misread, by cross-checking with
  `smartctl -A /dev/nvme0n1`.

## Verification

- After replacement, `nvme smart-log` reports `percentage_used: 0%`.
- Alert clears within one scrape cycle.

## Postmortem hook

Required only if data was lost; replacement-on-schedule is routine.
