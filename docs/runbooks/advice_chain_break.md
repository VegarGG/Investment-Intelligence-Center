# Runbook — Advice chain break

**Triggered by:** Alertmanager rule `AdviceChainBroken` (chain verifier fails) or the smoke check reports a hash mismatch on `lake.advice`.

## 1. Detect
- CLI:
  ```bash
  docker exec iic-postgres psql -tA -U iic_app -d iic \
    -f packages/data-lake/data_lake/migrations/queries/verify_advice_chain.sql
  ```
- Returns the first `id` whose `chain_hash` does not recompute from `prev_chain_hash` + payload.

## 2. Mitigate
- DO NOT delete the bad row. Stop writes via `flag agent_persona.enabled=false`, `agent_fundamental.enabled=false`, etc.
- Snapshot Postgres + NATS JetStream before any recovery action.
- Identify what produced the bad row via `SELECT agent, ts FROM lake.advice WHERE id=:offender;` and fix the source bug.
- Once fixed, re-base the chain by appending a tombstone row with `agent='ops.repair'` describing the breach. The verifier accepts the new head.

## 3. Verify
- Chain verifier returns 0 rows.
- New advice rows append cleanly.
