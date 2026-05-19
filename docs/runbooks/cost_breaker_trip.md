# Runbook — Cost breaker tripped

**Triggered by:** `outcome='rate_limit'` rate > 0 in `lake.llm_calls` (when `cost_breaker.enabled=true`).

## 1. Detect
- Dashboard: LLM spend badge in the shell shows ≥ 100%.
- CLI:
  ```bash
  docker exec iic-postgres psql -tA -U iic_app -d iic \
    -c "SELECT date, sum(cost_usd) FROM lake.llm_spend_daily
        WHERE date >= now() - interval '30 days' GROUP BY 1 ORDER BY 1 DESC;"
  ```

## 2. Mitigate
- Verify the breaker should be enabled: P0 default is OFF.
- If a genuine overrun, raise the cap via env (`LLM_MONTHLY_CAP_USD=…`) and restart agents — or call `meter.reset()` if the spike was anomalous.
- If a billing surprise, tighten the per-caller concurrency cap via `llm.concurrency.default=2`.

## 3. Verify
- Subsequent `chat_or_skip` returns real responses, not `synthetic-skip:cost_breaker_open`.
- `outcome='rate_limit'` rate returns to 0.
