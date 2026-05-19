# Runbook — Brief failed to send

**Triggered by:** Alertmanager rule `MorningBriefMissed` (no `secretary.outbound.brief` event in the last 24 h on a weekday) or the secretary's WeCom push returns non-200.

## 1. Detect
- Dashboard: Health → Schedules → `cron:morning_brief` last-fire time.
- CLI:
  ```bash
  curl -s http://iic-secretary:8086/health | jq .
  ```

## 2. Mitigate
- Confirm WeCom bot URL via `/admin/secrets` → `wecom_bot_url` is present.
- Manually trigger: `curl -X POST http://iic-secretary:8086/run/morning_brief` and read the response.
- If `agent_intelligence` or `orchestrator` returned `_error`, follow `provider_outage.md` first.
- For WeCom rate limits, set `notifier.durable_redelivery.enabled=true` (flag) and retry from the durable queue.

## 3. Verify
- WeCom receives the brief markdown.
- `/health` reports `last_brief_at` advanced.
