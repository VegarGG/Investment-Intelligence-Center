# Runbook — LLM provider outage

**Triggered by:** Alertmanager rule `LlmProviderErrorRateHigh` (provider 5xx rate > 5% over 5 min) or repeated `outcome='error'` in `lake.llm_calls`.

## 1. Detect
- Dashboard: Grafana `iic-001-ops` → "LLM error rate by provider" panel.
- CLI:
  ```bash
  docker exec iic-postgres psql -tA -U iic_app -d iic -c \
    "SELECT model, outcome, count(*) FROM lake.llm_calls
     WHERE ts > now() - interval '15 min' GROUP BY 1,2 ORDER BY 3 DESC;"
  ```

## 2. Mitigate
- If only one provider is failing, flip its router preference: edit `flags.yaml` to set the affected tier's `llm.fallback_preferred=true` (the fallback chain will take over).
- If both primary and fallback are 5xx-ing, set `cost_breaker.enabled=true` to short-circuit non-critical callers; critical callers (`secretary.brief.morning`, `board.chair`) will surface as errors.
- Notify the user via `/notify` with severity ALERT.

## 3. Verify
- Watch the `outcome='ok'` rate climb in `lake.llm_calls`.
- Confirm `morning_brief` succeeds on the next cron tick.
- Once stable, undo flag flips.
