# Workflow 31 — Production Hardening

> **Depends On:** every prior workflow doc.
> **Owns:** secrets management deep dive, DR drill rehearsal, NAS migration validation, security review, secrets rotation cadence, runbook authoring.
> **Status:** Final.

---

## 1. Purpose

Final pass before the system carries weight. Everything here is *recovery* and *reduction-of-blast-radius* work — not new features.

Five concerns:

1. **Secrets at rest.** sops + age, rotation cadence, recovery paths.
2. **DR drill.** Restore from B2 to a scratch box end-to-end in under 60 minutes.
3. **NAS migration validation.** Dry-run on every commit; full rehearsal once before any real cutover.
4. **Security review.** Threat model walk-through; close known-class issues.
5. **Runbook completeness.** Every alert code from `30_OBSERVABILITY_AND_EVAL.md` §2.3 has a runbook entry.

---

## 2. Ground Truth

### 2.1 Hard constraints carried from the plan

- **No real-money trading.** No broker keys in the system. Verified by grep on every PR.
- **Personal data minimization.** No PII in events. Watchlist is the most sensitive object; encrypted by sops.
- **Source verification.** Every advice carries citations; backtester rejects uncited.
- **Persona ethics.** Disclaimer required; never claim to be the real person.
- **Network.** Tailscale-only remote access. No public ports, no port-forwarding. Cloudflare Tunnel optional for the dashboard.
- **WeChat enclave.** WeCom OAuth callback verifies signatures; only whitelisted user-ids may issue commands.
- **Compliance.** Personal research system. **Not a registered investment advisor.** Footer disclaimer on every brief.

### 2.2 Secrets rotation cadence

| Class | Cadence | Owner | Notes |
|-------|---------|-------|-------|
| API keys (DeepSeek, Polygon, Tiingo, Tushare) | quarterly | Ziwei | CI gate fails if any key in `.env.sops.yaml` is older than 120 d |
| WeCom corp_id / app_secret | yearly | Ziwei | Coordinated with WeCom admin |
| age key (master) | yearly | Ziwei | Stored offline (paper wallet + USB) |
| Postgres role passwords | quarterly | rotation script | ALTER ROLE ... PASSWORD with rolling restart |
| Tailscale auth keys | quarterly | tagged auth keys, rotated through admin | |
| B2 application key | yearly | Ziwei | Backblaze console |
| SMTP App Password | yearly | Ziwei | Mailbox provider console |

📌 **CI gate.** `.github/workflows/secret-age-check.yml` reads age timestamps from sops metadata and fails on > 120 d.

### 2.3 DR drill scope

A clean-room restore must succeed end-to-end inside **60 minutes**. The drill is rehearsed:
- Once during initial setup, before going live.
- Quarterly thereafter.
- After any major dependency upgrade (Postgres major version, ChromaDB minor version).

📌 **Drill artifact.** Each rehearsal records elapsed time and any deviation in `docs/runbooks/dr-YYYY-MM-DD.md`.

### 2.4 NAS migration gating

`infra/nas/migrate.sh --dry-run` runs in CI on every push (see `01_INFRASTRUCTURE_AND_HOST.md` §5.6). A real apply is gated on:
- A successful dry-run on a Synology VirtualDSM in a VM (rehearsed once).
- A snapshot of `/srv/iic` taken just before apply.
- A two-person sign-off (Ziwei × the runbook checklist; the runbook is the second person).

### 2.5 Threat model

| Vector | Likelihood | Impact | Mitigation |
|--------|-----------:|-------:|------------|
| Compromised LLM API key | low | medium | sops + rotation; circuit breaker on cost spike |
| Lost laptop with Tailscale auth | low | high | Tailscale node auth + ACL; admin can revoke |
| WeCom callback spoof | low | medium | signature verification + user whitelist |
| Malicious crawl target serving exploit | medium | low | crawler runs in an isolated container, no shell exec on payloads |
| Prompt-injection in news articles | medium | low–medium | dispatch with system role; Pro caller limited to digesting events, not executing tasks |
| Cookie-based scraper auth | low | low | scrapers are read-only; no credentials stored except for X bearer if used |
| Family member running unauthorized command | low | low | WeCom whitelist + slash-command allowlist |
| RAM bit-flip on non-ECC | low | varies | yearly memtester; chain-integrity audit catches corruption |
| Restic key loss | low | catastrophic | age key duplicated offline + paper-wallet record |
| Backblaze credential leak | low | high | bucket scoped to single key; alert on impossible-traffic |

---

## 3. Secrets Management Deep Dive

### 3.1 sops + age workflow

1. Generate the master age key on the host: `age-keygen -o /etc/iic/age.key` (root, 600). **Back up this file** to two physical locations.
2. Create `.sops.yaml` at the repo root:

```yaml
creation_rules:
  - path_regex: \.env(\.sops)?$
    age: age1xxxxxxxxxxxxxxxxxxxxxxxxxxx
```

3. Encrypt prod `.env`: `sops --encrypt --in-place .env`. Commit the encrypted version.
4. The host's `iic.service` uses `ExecStartPre=/usr/local/bin/iic-decrypt-secrets.sh` to decrypt `.env.sops` to `/run/iic/.env` (tmpfs, never on disk in plaintext).
5. Compose's `env_file: /run/iic/.env`.

### 3.2 Recovery if the age key is lost

- Without the age key, `.env.sops` is unrecoverable.
- Recovery = re-issue every API key from each provider's console. Bring up a fresh `.env` from `.env.example`, encrypt with a new age key.
- Postgres data, ChromaDB data, etc. are recoverable from restic regardless — they're separate.

📌 **Annual ritual:** verify the offline backup of the age key works by decrypting a test file. Document in `docs/runbooks/age-backup-verify.md`.

### 3.3 Per-service secrets

Some services need their own secrets in addition to env vars:

- **MinIO:** root creds in env; per-service IAM keys generated at boot via `infra/minio/init-buckets.sh` (already in `02_DATA_LAYER.md` §7.5).
- **Postgres:** role passwords in env; pg_hba.conf restricted to localhost + Docker bridge.
- **WeCom callback:** `WECOM_TOKEN` and `WECOM_AES_KEY` in `.env`; verified by callback handler.

---

## 4. Eval Harness as a Production Gate

(Implemented in `04_PROMPT_REGISTRY.md` §5; deployed here.)

- **PR gate:** prompt-version bumps run the affected callers' eval. Fail the PR on regression > §2.4 bands.
- **Weekly drift watch:** Monday cron; emits `PROMPT_EVAL_REGRESSION` on > 10% drop.
- **Quarterly judge audit:** every quarter, Ziwei manually reviews 20 random judge gradings to ensure the judge isn't itself drifting. If judge bias is suspected, freeze a new judge prompt and bump `eval.judge` major version.

---

## 5. DR Drill — Step-by-Step

📌 **Target: < 60 min total.** Stopwatch starts at step 1.

1. Acquire scratch hardware (a second mini PC, a VM, or a USB-bootable Ubuntu).
2. Boot Ubuntu 24.04 Server. Run `bash bootstrap.sh` from a USB stick that has the IIC repo.
3. Sync the age key from the offline backup to `/etc/iic/age.key`.
4. Place encrypted `.env.sops` in `/opt/iic/`.
5. `restic restore --repo b2:iic-restic --target /srv/iic latest`.
6. `systemctl start iic.service`.
7. Wait for `docker compose ps` all `Up`.
8. Confirm: WeCom briefs bot delivers a test brief (kick `POST /run/morning_brief`); orchestrator heartbeat present; leaderboard renders on the dashboard.

**Stop the stopwatch.** Record elapsed time in `docs/runbooks/dr-YYYY-MM-DD.md` along with any pain points.

If any step took > 10 min, file an issue.

---

## 6. NAS Migration Rehearsal

Before any production NAS cutover:

1. Spin up Synology VirtualDSM in a VM (or a real NAS in a sandbox).
2. Configure NFS share `/volume1/iic` with squash to UID/GID matching `iic`.
3. From the IIC host, run `infra/nas/migrate.sh --apply` with `NAS_HOST=<vm.ip>` `NAS_PATH=/volume1/iic`.
4. Wait for `iic.service` to come back up.
5. Run a smoke check: `curl localhost:8080/health` healthy; one synthetic advice round-trips through the bus.
6. Roll back: `infra/nas/rollback.sh` (restores the local `/srv/iic` mount).
7. Document the test in `docs/runbooks/nas-rehearsal-YYYY-MM-DD.md`.

⚠️ Postgres on NFS is fine in NFSv4.1+ with `hard,nolock` semantics, but if performance suffers, run hybrid mode (Postgres stays on local NVMe; everything else on NAS) per `01_INFRASTRUCTURE_AND_HOST.md` §5.6.

---

## 7. Security Review Checklist

Run this every quarter and after any dependency upgrade. Pass criteria: zero critical, ≤ 2 high.

- [ ] No public ports on the box (`nmap` from a phone on cellular returns no open ports).
- [ ] Tailscale ACLs scoped: only the principal's devices can SSH.
- [ ] No broker, payment, or trading API keys in `.env.example` or `.env.sops`.
- [ ] Persona disclaimer present in 100% of last 30 d's `advice.persona.*.v1` (SQL spot check).
- [ ] Backtester ledger chain integrity intact for every agent (run `verify_chain` for each).
- [ ] No PII in `lake.events.body` (sample 100 random rows, manual scan; if any phone numbers/emails detected, redact-on-ingest rule added).
- [ ] sops files have not been committed in plaintext anywhere in git history (`git log --all --source --remotes -p -S "DEEPSEEK_API_KEY="`).
- [ ] WeCom whitelist matches `SECRETARY_ALLOWED_USERS` env (no orphaned users).
- [ ] Cost burn budget within bounds (≤ $160/mo all-in).
- [ ] Restic snapshots exist for the last 7 daily, 4 weekly, 12 monthly cycles in B2.
- [ ] Eval drift dashboard shows no caller regressed > 10% in the last 4 weeks.
- [ ] Bias balance metric within bounds (no region > 0.55 for 7-day rolling avg).
- [ ] Disk wear < 70% on NVMe.

---

## 8. Runbook Set

📌 **Every alert code in `30_OBSERVABILITY_AND_EVAL.md` §2.3 has a runbook in `docs/runbooks/`.** Each follows this template:

```markdown
# Runbook — <ALERT_CODE>

## What it means
…

## Likely causes (most → least likely)
1. …
2. …

## First-look checks (≤ 2 minutes)
- `docker compose logs <service> --tail 100`
- `curl http://localhost:9090/...`
- …

## Resolution paths
- Path A (most common): …
- Path B: …
- Path C (escalation): …

## Verification
- `curl http://localhost:.../health`
- Alert clears within …

## Postmortem template hook
If this caused user-visible impact (brief missed, alert not delivered), open a postmortem at `docs/postmortems/YYYY-MM-DD-<slug>.md`.
```

Initial set of mandatory runbooks:

- `runbook-host-down.md`
- `runbook-nvme-wear-high.md`
- `runbook-ups-battery-low.md`
- `runbook-disk-free-critical.md`
- `runbook-llm-cost-breaker-open.md`
- `runbook-agent-heartbeat-missed.md`
- `runbook-prompt-eval-regression.md`
- `runbook-bias-balance-skew.md`
- `runbook-mark-feed-stale.md`
- `runbook-advice-ledger-broken.md`
- `runbook-backup-failed.md`
- `runbook-wecom-callback-failing.md`
- `runbook-deepseek-api-down.md`

---

## 9. Workflow Steps

### Step 9.1 — Author secrets stack

Generate age key. Encrypt `.env`. Wire `iic-decrypt-secrets.sh`. Test that `iic.service` starts cleanly with the encrypted file and not the plaintext.

### Step 9.2 — Author the secret-age CI gate

`.github/workflows/secret-age-check.yml` reads `.env.sops` metadata via sops and fails the build if any key is > 120 d old.

### Step 9.3 — Author runbooks

For each alert code in §8, write the runbook by walking through the cause-analysis tree at least once on the live system (induce the alert, follow the runbook, refine).

### Step 9.4 — Run DR drill

Per §5. Document. File issues for any >10 min step.

### Step 9.5 — NAS rehearsal

Per §6. Document.

### Step 9.6 — Security review

Per §7. File issues for any failures. Re-run after fixes.

### Step 9.7 — Postmortem template

Author `docs/postmortems/TEMPLATE.md`:

```markdown
# Postmortem — <Title> — YYYY-MM-DD

## Impact
- Window:
- Visible to user:

## Timeline (UTC)
- HH:MM …

## Detection
…

## Resolution
…

## Root cause
…

## What worked
…

## What didn't work
…

## Action items
- [ ] …
```

---

## 10. Vibe Prompts (paste-ready)

🧪 **sops bootstrap:**
> Author `infra/linux/iic-decrypt-secrets.sh` per §3.1. Reads `/opt/iic/.env.sops`, decrypts with `sops --decrypt`, writes to `/run/iic/.env` (tmpfs, mode 600). Refuses to run if `/run/iic` isn't a tmpfs. Add a self-test that decrypts a fixture file in CI.

🧪 **Secret-age CI gate:**
> Author `.github/workflows/secret-age-check.yml`. Reads sops metadata for every encrypted file in the repo (`*.sops`, `.env.sops`). Fails the workflow if any key's `lastmodified` is older than 120 days. Outputs a Markdown summary listing each key's age.

🧪 **DR drill script:**
> Author `infra/linux/dr-drill.sh` that automates §5 steps 5–8 (everything except the human-driven hardware setup). Idempotent. Outputs elapsed seconds at the end. Can run unattended in the rehearsal VM.

🧪 **Runbook scaffolder:**
> For each alert code in §8, generate a stub `docs/runbooks/<slug>.md` from the template. Pre-populate with at least 3 likely causes and the relevant `docker compose logs` / `curl` commands. Leave the resolution paths blank for human authoring.

---

## 11. Acceptance Criteria

- [ ] sops-encrypted `.env.sops` in repo; plaintext `.env` is `.gitignored` and absent from git history.
- [ ] CI `secret-age-check` runs on every PR and main; passes today.
- [ ] DR drill rehearsed once; elapsed time recorded; any > 10 min step has an open issue or has been fixed.
- [ ] NAS rehearsal completed in a VM; `infra/nas/migrate.sh --apply` succeeded against VirtualDSM; rollback worked.
- [ ] Security review: zero critical, ≤ 2 high findings.
- [ ] All runbooks in §8 exist and are non-empty.
- [ ] Postmortem template at `docs/postmortems/TEMPLATE.md`.
- [ ] Quarterly check is scheduled (calendar reminder + Grafana annotation).

---

## 12. Risks & Gotchas

⚠️ **Documenting age key recovery without leaking it.** Don't put recovery instructions on the same physical paper as the key. Two locations, two artifacts.

⚠️ **DR drill tests both backup and restore.** A drill that only tests the backup is half a drill. Always exercise the restore on real scratch hardware.

⚠️ **Synology VirtualDSM caveat.** It's free for development but legally limited; don't rely on it for production-like load testing.

⚠️ **Quarterly fatigue.** Treat the quarterly checklist like brushing teeth, not like an audit. The minute it starts feeling theatrical, simplify it.

⚠️ **Postgres major upgrades.** TimescaleDB pinned to a specific Postgres major. Plan upgrades quarterly with a rehearsal — the DB upgrade itself is the highest-risk operation in the system.

⚠️ **Compliance creep.** This system is personal research. If usage shifts toward giving advice to non-family-members, the legal posture changes and a different doc set applies. The disclaimer rule + family-only WeCom whitelist exist to keep that boundary visible.

⚠️ **Runbook accuracy decays.** When the underlying system changes, runbooks lie. Tag every runbook with `last_verified` and re-walk during the quarterly review.

---

## 13. Cross-References

- All alert codes: `30_OBSERVABILITY_AND_EVAL.md` §2.3.
- NAS migrate script: `01_INFRASTRUCTURE_AND_HOST.md` §5.6.
- Restore commands: `01_INFRASTRUCTURE_AND_HOST.md` §5.5.
- Eval harness: `04_PROMPT_REGISTRY.md` §5.
- Persona disclaimer enforcement: `13_AGENT_PERSONA.md` §5.5.
- Cost breaker: `03_LLM_CLIENT.md` §7.

---

## Changelog

- **v1.0** — Extracted from `PLAN_v2.1` §13 + DR sections of §8 and §9. Threat model formalized; rotation cadence promoted to a table; runbook set enumerated.

— end of workflow set —
