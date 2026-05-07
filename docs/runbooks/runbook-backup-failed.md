# Runbook — BACKUP_FAILED

`last_verified: 2026-05-07`

## What it means

`iic_restic_last_success_seconds` exposes a >36 h gap. We have no fresh
off-host snapshot — DR window grows hour by hour.

## Likely causes (most → least likely)

1. Backblaze B2 credential expired or rotated without env update.
2. NVMe pressure prevented the local snapshot stage.
3. restic repo lock left behind from an interrupted run.
4. Network outage to B2.

## First-look checks (≤ 2 min)

- `journalctl -u iic-backup.service -n 200`
- `restic --repo "$RESTIC_REPOSITORY" snapshots | tail`
- `restic unlock` if a stale lock exists.
- B2 console: any auth errors logged?

## Resolution paths

- Path A — auth: re-issue the B2 application key, update `.env.sops`,
  encrypt, redeploy.
- Path B — stale lock: `restic --repo ... unlock --remove-all` (after
  confirming no concurrent restic runs).
- Path C — disk pressure: see `runbook-disk-free-critical.md` first.

## Verification

- `restic --repo ... backup` succeeds end-to-end.
- `iic_restic_last_success_seconds` gauge resets.

## Postmortem hook

Open one if the gap exceeded 72 h.
