# Runbook — AGENT_HEARTBEAT_MISSED

`last_verified: 2026-05-07`

## What it means

A service has not published `ops.heartbeat.v1` for ≥ 5 minutes. Either
its container is down, the bus connection is broken, or the heartbeat
loop crashed.

## Likely causes (most → least likely)

1. Container OOM-killed.
2. NATS connection lost; reconnect logic failing.
3. Code regression after a recent deploy.
4. Postgres writes blocked (heartbeat depends on the bus, not PG, but
   downstream symptoms can mask).

## First-look checks (≤ 2 min)

- `docker compose ps <service>` — is it running?
- `docker compose logs <service> --tail 200`
- `nats-top` (or `nats stream report OPS`) — incoming heartbeats?
- `curl http://<service>:<port>/health`

## Resolution paths

- Path A — OOM kill: check `dmesg` for `Killed process`; raise the memory
  limit in compose (typically the persona container needs 512 MB).
- Path B — NATS reconnect stuck: `docker compose restart <service>`.
- Path C — code bug: `git log --oneline -20` to find the recent deploy,
  open a PR rolling back.

## Verification

- New `ops.heartbeat.v1` row from the service in the bus within 60 s.
- Alert clears.

## Postmortem hook

Open one if user-visible features (briefs, fills, chat) lagged.
