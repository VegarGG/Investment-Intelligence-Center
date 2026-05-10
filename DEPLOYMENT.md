# Deploying IIC on a fresh Ubuntu Desktop 26.04 LTS

> **Audience:** developers (junior or senior) standing up the prototype on a fresh box for the first time. The goal is **dashboard-in-a-browser in under 15 minutes**.
>
> **What this gets you:** the v2.5 substrate (Postgres + NATS + Redis + Chroma + MinIO), the orchestrator, the dashboard, and every agent (Intelligence, Fundamental, Quant, Persona, Backtest, Secretary, Investment Board). FUTU stays off; LLM agents boot but short-circuit until you add a DeepSeek key.
>
> **What this is not:** the production hardening posture (UFW, fail2ban, sops, Tailscale, restic offsite). That lives in [`infra/linux/bootstrap.sh`](infra/linux/bootstrap.sh) and is documented in [`workflows/31_PRODUCTION_HARDENING.md`](workflows/31_PRODUCTION_HARDENING.md).

---

## 0. Before you start

You need:

- **Ubuntu Desktop 26.04 LTS** (or 24.04 LTS) on a machine with:
  - **≥ 16 GB RAM** (the full stack is sized for this)
  - **≥ 30 GB free disk** on the partition where the repo lives
  - **internet access** (to pull Docker images and Python packages)
- A user account with **sudo** access (root login is not required and not recommended)
- About **15 minutes** for the first run; subsequent re-runs take seconds

You do **not** need:

- A DeepSeek / Anthropic / Polygon / WeChat API key — the stack boots without them. LLM calls cost-skip; market-data ingest stays idle.
- A FUTU account — the FUTU agent is profile-disabled in dev mode.
- Any production infrastructure (Tailscale, sops keys, NAS, UPS) — those are prod-only concerns.

---

## 1. The fast path (one command)

Open a terminal in the repo root and run:

```bash
make setup
```

That's it. `make setup` calls [`deploy/setup.sh`](deploy/setup.sh), which:

1. Checks you're on Ubuntu and have enough RAM/disk
2. Installs Docker Engine + Compose plugin (uses Docker's official apt repo when available, falls back to `docker.io` from universe)
3. Adds your user to the `docker` group (you may need to log out and back in once)
4. Creates the `/srv/iic/*` data tree owned by you
5. Generates a working `.env` with random passwords for the local datastores
6. Writes a default feature-flags file at `/srv/iic/featureflags/flags.yaml`
7. Builds every Docker image
8. Starts the substrate, waits for Postgres healthy, applies all database migrations
9. Starts the agents and the dashboard
10. Smoke-checks every `/health` endpoint
11. Prints the URLs you can open

When it finishes, open **http://localhost:4173** in Firefox / Chrome / your browser of choice.

> **Heads-up about the `docker` group.** The setup script adds your user to `docker` but the change only takes effect on a new login session. If `docker compose ps` says `permission denied`, log out and back in (or run `newgrp docker` in the same shell), then re-run `make up`.

---

## 2. What's running, in plain English

After setup completes, you have **15 containers** running. Here's the cheat sheet:

| What | Container | URL or port | Why it's there |
|------|-----------|-------------|----------------|
| **Dashboard** (the UI you actually use) | `iic-dashboard` | http://localhost:4173 | React app showing personas, intel, leaderboard, the new trading-room view |
| **Orchestrator** | `iic-orchestrator` | http://localhost:8080/health | Runs the cron + event-driven DAGs (morning brief, midday pulse, trading room) |
| Investment Board | `iic-agent-board` | http://localhost:8088/health | Bull/Bear → Risk → Chair pipeline. Off by default; flip the flag to enable. |
| Intelligence | `iic-agent-intelligence` | http://localhost:8081/health | News + macro digest. Idle until you add API keys. |
| Fundamental | `iic-agent-fundamental` | http://localhost:8082/health | Filing-based valuations. |
| Quant | `iic-agent-quant` | http://localhost:8083/health | Factor library + walk-forward. |
| Persona | `iic-agent-persona` | http://localhost:8084/health | 8 stylised investor personas. |
| Backtest | `iic-agent-backtest` | http://localhost:8085/health | Mark-to-market + leaderboard. |
| Secretary | `iic-agent-secretary` | http://localhost:8086/health | Brief composer + WeChat push. |
| Postgres | `iic-postgres` | localhost:5432 | The lake (`lake.advice`, `lake.events`, `lake.futu_audit`, etc.) |
| NATS | `iic-nats` | localhost:4222 | Event bus between agents |
| Redis | `iic-redis` | localhost:6379 | Idempotency cache + notifier retry queue |
| Chroma | `iic-chroma` | localhost:8000 | Embedding store for filings + persona memory |
| MinIO | `iic-minio` | http://localhost:9001 | S3-compatible blob store (briefs, backtest artifacts) |

If any of these is missing or unhealthy, run `make health` for a quick diagnostic and `make logs SVC=<name>` to see why.

---

## 3. Common operations

```bash
# Bring it up after a reboot
make up

# Stop everything (data preserved on disk)
make down

# Tail every container's logs
make logs

# Tail one service's logs
make logs SVC=orchestrator

# Re-run the smoke check
make health

# Re-run database migrations (idempotent)
make migrate

# Run the Python test suite locally
make test

# Open psql against the running Postgres
make shell-pg

# Open the dashboard in your default browser
make open
```

`make help` lists every target.

---

## 4. Adding API keys (optional)

The stack works fine with no third-party keys — agents boot, the dashboard renders, the test suite passes. To make it actually generate briefs, you'll want at least one LLM key.

### LLM (the most important)

The stack is built around **DeepSeek v4** as primary, with Anthropic and Groq as fallbacks. Get a DeepSeek key from <https://platform.deepseek.com>.

```bash
# Edit .env
sed -i 's|^DEEPSEEK_API_KEY=$|DEEPSEEK_API_KEY=sk-your-key-here|' .env

# Restart the orchestrator + agents that call the LLM
docker compose restart orchestrator agent_intelligence agent_secretary \
  agent_persona agent_fundamental agent_quant agent_board
```

### Market data (Intelligence agent)

For real news / market data, set any subset of:

| Provider | Env var | Use |
|----------|---------|-----|
| Polygon  | `POLYGON_API_KEY` | US equities + options |
| AlphaVantage | `ALPHAV_API_KEY` | Backup quote source |
| FRED | `FRED_API_KEY` | Macro releases |
| Tushare | `TUSHARE_TOKEN` | China equities |
| OpenBB | `OPENBB_PAT` | Aggregated free sources |

The Intelligence agent reads `INTEL_AUTOSTART` — it defaults to `0` in dev. Set it to `1` and restart the agent to start the ingest pipeline.

### WeChat push (Secretary agent)

If you want briefs pushed to WeChat group bots, fill in the `WECOM_*` vars. See [`workflows/20_NOTIFIER_WECHAT.md`](workflows/20_NOTIFIER_WECHAT.md). Skipping this just means briefs stay on the dashboard (and in `lake.advice`).

---

## 5. Toggling the v2.5 trading-room features

The new Investment Board + Trading-room DAG ship in this iteration but are **off by default**. To enable:

```bash
# Edit /srv/iic/featureflags/flags.yaml — change two lines:
#   trading_room.event_triage.enabled: true
#   trading_room.investment_board.enabled: true

# Bounce the orchestrator and the board to pick up the new flag values
docker compose restart orchestrator agent_board
```

The Trading Room view at <http://localhost:4173/trading-room> shows nothing until a `intel.event.high_impact.v1` event fires. To smoke-test the path locally without real news:

```bash
# Publish a synthetic high-impact event onto the NATS bus
docker compose exec nats nats pub intel.event.high_impact.v1 '{
  "event_id": "evt_smoke_001",
  "trace_id": "trace_smoke_001",
  "title": "Synthetic FOMC surprise — for testing only",
  "tickers": ["US.SPY"],
  "regime_change_score": 0.92,
  "surprise_factor": 0.88,
  "affected_universe_overlap": 0.7
}'
```

The Trading Room view should populate within ~5 seconds (the orchestrator polls NATS subscriptions, the Board synthesises a decision, the Secretary composes the brief).

---

## 6. Running the test suite

The Python test suite covers the orchestrator, the schema validators, every agent's logic, and the chaos drills:

```bash
make test
```

Expect **~553 tests pass + 16 skipped** (the skips are env-gated — Postgres-backed audit chain, real-DeepSeek cost cap, FUTU live drills). All those skips are intentional and documented in their respective test files.

To run just the new v2.5 N3 tests:

```bash
PYTHONPATH=packages/featureflags:packages/schema:packages/llm-client:packages/data-bus:packages/prompts:packages/notifier:packages/data-lake:apps/orchestrator:apps/agent_persona:apps/agent_quant:apps/agent_fundamental:apps/agent_futu:apps/agent_secretary:apps/agent_backtest:apps/agent_intelligence:apps/agent_board \
  pytest -q apps/agent_board/ \
            apps/orchestrator/tests/test_event_triage.py \
            apps/orchestrator/tests/test_trading_room_dag_e2e.py \
            tests/test_team_plan_e2e.py \
            tests/test_trading_room_brief_format.py
```

---

## 7. Troubleshooting

### "permission denied" running docker compose

The `setup.sh` script added your user to the `docker` group, but the change only takes effect in a new login session. Three fixes (pick one):

```bash
# 1) Open a new terminal tab/window
# 2) Run `newgrp docker` in the current shell
# 3) Log out + log back in
```

### Postgres won't start / "no space left on device"

The compose stack expects ≥ 30 G free on the partition where `/srv/iic` lives. If `df -h /srv/iic` shows you're tight, prune Docker:

```bash
docker system prune -a --volumes
```

If you want to start over completely, `make reset` will stop everything, wipe `/srv/iic`, delete `.env`, and let you re-run `make setup` cleanly.

### Migrations failed: "permission denied for schema lake"

This usually means `init-roles.sql` didn't apply (the `iic_app` / `iic_ro` / `iic_migration` roles are missing). Re-run:

```bash
make migrate
```

The migration script is idempotent — if roles already exist, it's a no-op; if not, it creates them.

### `make health` reports the dashboard 502s

The dashboard's nginx upstream needs the orchestrator to be up. Check:

```bash
make logs SVC=orchestrator | head -50
```

Most common cause: orchestrator can't reach Postgres because the migration didn't apply. Run `make migrate` once.

### Port 5432 (or 8080, 4173, ...) is already in use

You probably have another Postgres or another web server running. Either stop the other process or change the `ports:` mapping in `docker-compose.dev.yml`.

### "Docker has no apt release for ${codename}"

If you're on a brand-new Ubuntu version that Docker hasn't packaged yet, the script falls back to the `docker.io` / `docker-compose-v2` packages from Ubuntu universe. Slightly older but always available. Once Docker publishes for your codename, you can switch:

```bash
sudo apt remove docker.io docker-compose-v2
# Then re-run the docker step:
sudo rm /var/lib/iic-deploy/docker
make setup
```

### Containers crashloop with "no module named ..."

You're probably running `make test` instead of `make up` and hitting a stale Python install. The Docker images are self-contained — rebuild them:

```bash
make build
make up
```

### "I want to wipe everything and start over"

```bash
make reset      # confirms with a 10-second countdown
make setup
```

---

## 8. What's safe to commit

The repo's `.gitignore` already excludes:

- `.env` (your generated secrets)
- `.deploy/` (the cached postgres password file `run-migrations.sh` reads)
- `node_modules/`, `apps/dashboard/dist/`, all `__pycache__/`
- `/srv/iic/` (it's outside the repo anyway)

You can safely `git add -A` after running `make setup` — none of the secret material lands in the working tree.

---

## 9. Going further

- **Architecture overview:** [`README.md`](README.md), [`workflows/00_INDEX_AND_CONVENTIONS.md`](workflows/00_INDEX_AND_CONVENTIONS.md)
- **The v2.5 trading-room iteration:** [`plan/D5_IIC_Prototype_Review_and_Next_Iteration.md`](plan/D5_IIC_Prototype_Review_and_Next_Iteration.md)
- **Investment Board internals:** [`workflows/43_INVESTMENT_BOARD.md`](workflows/43_INVESTMENT_BOARD.md)
- **FUTU read-only safety story:** [`docs/security/FUTU_readonly_review.md`](docs/security/FUTU_readonly_review.md)
- **Production hardening:** [`infra/linux/bootstrap.sh`](infra/linux/bootstrap.sh) + [`workflows/31_PRODUCTION_HARDENING.md`](workflows/31_PRODUCTION_HARDENING.md)

---

## Disclaimer

IIC is a personal research tool. It is **suggestion-only** and does not place orders. Nothing emitted by the system is investment advice. The FUTU integration is read-only by construction (wrapper allowlist + nftables firewall + audit chain + revoked DB writes); see the security review for the defence-in-depth story.
