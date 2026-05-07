# Runbook — BIAS_BALANCE_SKEW

`last_verified: 2026-05-07`

## What it means

One region's share of the digest's source mix exceeded 0.55 averaged over
the last 7 days. Workflow 10 §5.10 is a hard rule — we re-prompt the
synthesizer and (if still skewed) emit this alert so the principal is
informed of the bias.

## Likely causes (most → least likely)

1. A non-Western feed went silent (rate-limit ban, broken HTML).
2. A new high-weight Western source was added without rebalancing.
3. Crawler circuit breaker opened on multiple CN/EM feeds at once.

## First-look checks (≤ 2 min)

- Grafana → IIC-003-Data-Freshness → "Bias balance" panel.
- `apps/agent_intelligence/sources.yaml` — recent diffs?
- `redis-cli KEYS "circuit_breaker:open:*"` — any source paused?

## Resolution paths

- Path A — failing feed: fix the crawler error, lower the breaker
  threshold for that source temporarily.
- Path B — manifest imbalance: lower `region_weight` on US/EU sources
  in `sources.yaml` to compensate.
- Path C — escalation: emit a brief footer noting the imbalance so the
  principal is aware while we fix it.

## Verification

- 7-day rolling region share < 0.55 again.
- Alert clears.

## Postmortem hook

Open one if the imbalance persisted >7 days.
