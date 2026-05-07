# Runbook — DeepSeek API down

`last_verified: 2026-05-07`

## What it means

DeepSeek (primary Pro + Flash provider) is failing. The fallback chain
(Anthropic for Pro, Groq for Flash) takes over automatically; `DeepSeekDown`
exceptions in logs are expected. If both primary and fallback fail, briefs
degrade to templated mode and `LLM_COST_BREAKER_OPEN` may also fire from
fallback cost overage.

## Likely causes (most → least likely)

1. DeepSeek upstream incident.
2. Local network / DNS issue from the box to api.deepseek.com.
3. Quota / billing issue on the DeepSeek account.

## First-look checks (≤ 2 min)

- `curl -fsS https://api.deepseek.com/v1/models -H "Authorization: Bearer $DEEPSEEK_API_KEY"`
- DeepSeek status page (bookmarked).
- Loki: `{service="agent_secretary"} |= "DeepSeekDown"` count last 15 min.

## Resolution paths

- Path A — upstream incident: nothing to do; fallback already engaged.
  Watch the cost meter; raise the breaker if Anthropic spend will exceed
  the $5/day fallback cap (workflow 03 §7).
- Path B — local network: `dig api.deepseek.com`, restart the IIC host
  network stack.
- Path C — billing: top up the account; fallback continues until the
  primary is back.

## Verification

- A `chat()` call to the `intel.synth` caller returns from DeepSeek again.
- `fallback_used` count drops back to zero.

## Postmortem hook

Open one if briefs went templated for >2 h.
