# Runbook — ADVICE_LEDGER_BROKEN

`last_verified: 2026-05-07`

**SEVERITY: critical.** Pages immediately.

## What it means

The hash-chain audit on `lake.advice` failed for one or more agents. Either
(a) the chain was tampered with, (b) a write bypassed the trigger, or
(c) a row was UPDATEd/DELETEd despite the revoke. Until resolved, the
backtester pauses leaderboard publication.

## Likely causes (most → least likely)

1. A migration accidentally touched `lake.advice` rows (regression bug).
2. A DBA action that the audit role caught.
3. Hardware corruption (very rare; chain integrity is the canary).

## First-look checks (≤ 2 min)

- `SELECT * FROM lake.advice_chain_audit ORDER BY ts DESC LIMIT 5;`
- `SELECT data_lake.advice_ledger.verify_chain('<agent>')` for each agent.
- `SELECT agent, count(*) FROM lake.advice GROUP BY 1;` — any missing rows?

## Resolution paths

- Path A — find the first broken row id from `verify_chain`; check
  `pg_audit` (if enabled) or `pg_stat_user_tables` last-modified delta.
- Path B — restore the affected agent's slice from the most recent
  restic backup, then re-replay `advice.*` events from the bus's
  retention window to catch up.
- Path C — escalate: this is a ground-truth integrity break. Open a
  postmortem AND an issue. Consider freezing publication until reviewed.

## Verification

- All agents return `verify_chain: ok`.
- Leaderboard publication resumes.

## Postmortem hook

Mandatory.
