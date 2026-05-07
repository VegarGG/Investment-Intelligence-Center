# Runbook — LLM_COST_BREAKER_OPEN

`last_verified: 2026-05-07`

## What it means

The LLM cost meter passed `LLM_MONTHLY_BUDGET_USD`. The breaker is OPEN —
all Pro and Flash calls are paused. Briefs degrade to templated mode.

## Likely causes (most → least likely)

1. Genuine cost burn from real workload (check the week-over-week trend).
2. A prompt regression that 10x'd token use without raising scores.
3. A broken cache (every Flash call missing).
4. A runaway agent looping `llm_client.chat`.

## First-look checks (≤ 2 min)

- Grafana → IIC-001-Ops → "LLM cost burn" panel.
- `SELECT caller_id, sum(cost_usd) FROM lake.llm_calls WHERE ts > now() - interval '24 h' GROUP BY 1 ORDER BY 2 DESC;`
- `redis-cli KEYS "cache:llm:*" | wc -l` — non-zero means cache populated.

## Resolution paths

- Path A — genuine spend: raise `LLM_MONTHLY_BUDGET_USD` (deliberate
  decision, document in `docs/postmortems/`); re-deploy.
- Path B — prompt regression: roll back to the previous prompt version
  via the registry (`packages/prompts/registry/<caller>/<prev>.md`) and
  bump caller_id back.
- Path C — broken cache: check `cache:llm:*` TTL; if PromptCache returns
  miss for known-deterministic Flash callers, redeploy llm-client.

## Verification

- Cost-meter spend drops below cap within the next billing cycle.
- Breaker state returns to CLOSED.

## Postmortem hook

Always — cost spikes are visible to the principal and warrant a
postmortem with action items.
