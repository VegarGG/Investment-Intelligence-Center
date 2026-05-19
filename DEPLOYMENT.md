# Deploying IIC on a fresh Ubuntu Desktop 26.04 LTS

> **Audience:** developers (junior or senior) standing up the prototype on a fresh box for the first time. The goal is **dashboard-in-a-browser in under 15 minutes**.
>
> **What this gets you:** the v2.5 substrate (Postgres + NATS + Redis + Chroma + MinIO), the orchestrator, the dashboard, the v2.6 admin API, and every agent (Intelligence, Fundamental, Quant, Persona, Backtest, Secretary, Investment Board). FUTU stays off; with no LLM key set, calls surface real errors (the cost gate is **off** by default in v2.6 — see P0 in [`plan/D7`](plan/D7_IIC_Development_Plan_Prototype_to_Product.md)).
>
> **What this is not:** the production hardening posture (UFW, fail2ban, sops, Tailscale, restic offsite). That lives in [`infra/linux/bootstrap.sh`](infra/linux/bootstrap.sh) and is documented in [`workflows/31_PRODUCTION_HARDENING.md`](workflows/31_PRODUCTION_HARDENING.md). For the v2.6 operational story (per-call OTel spans, restore drill, five P9 runbooks), see [`docs/runbooks/`](docs/runbooks/).

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

After setup completes, you have **16 containers** running (the v2.6 admin API is the new one). Here's the cheat sheet:

| What | Container | URL or port | Why it's there |
|------|-----------|-------------|----------------|
| **Dashboard** (the UI you actually use) | `iic-dashboard` | http://localhost:4173 | React app: trading room, personas, intel, leaderboard, geo **Map** (v2.6 P5), `/admin/*` Settings pages (v2.6 P3). |
| **Orchestrator** | `iic-orchestrator` | http://localhost:8080/health | Cron + event-driven DAGs (morning brief, midday pulse, trading room, intel pulls every 5/15/60 min — v2.6 P2.9). |
| **Admin API** | `iic-admin-api` | http://localhost:8090/admin/health | YAML editor, sops-sealed secret rotation, connector test, schedules, brokers, `lake.config_audit` chain head (v2.6 P3). |
| Investment Board | `iic-agent-board` | http://localhost:8088/health | Bull/Bear → Risk → Chair pipeline. Off by default; flip the flag to enable. |
| Intelligence | `iic-agent-intelligence` | http://localhost:8081/health | News + macro digest. After v2.6 P2: GDELT crawler, FRED macro, pgvector dedupe, `intel.context.v1` builder. |
| Fundamental | `iic-agent-fundamental` | http://localhost:8082/health | EDGAR filings + valuation; `/run/cover` + `/run/digest` wired in v2.6 P7. |
| Quant | `iic-agent-quant` | http://localhost:8083/health | Factor library + walk-forward + regime detector (v2.6 P7.5). |
| Persona | `iic-agent-persona` | http://localhost:8084/health | 8 stylised personas; `/run/daily` + `/run/weekly` + `/run/rerun` wired in v2.6 P8. |
| Backtest | `iic-agent-backtest` | http://localhost:8085/health | Mark-to-market + leaderboard. v2.6 P7 adds the `lake.bt_positions` book. |
| Secretary | `iic-agent-secretary` | http://localhost:8086/health | Leader-router (v2.6 P6): outbound dispatcher, `/chat`, `/rerun`, `/prefs/*`, real brief composition, WeChat push. |
| Postgres | `iic-postgres` | localhost:5432 | The lake. v2.6 adds migrations 0006–0013: pgvector embeds, config audit, quotes, geo events, user prefs, secretary thread, bt positions. |
| NATS | `iic-nats` | localhost:4222 | Event bus between agents. v2.6 subscribes to `intel.event.geo_cluster.v1`. |
| Redis | `iic-redis` | localhost:6379 | Idempotency cache + notifier retry queue + intel dedupe (v2.6 P2.2). |
| Chroma | `iic-chroma` | localhost:8000 | Embedding store for filings + persona memory. |
| MinIO | `iic-minio` | http://localhost:9001 | S3-compatible blob store (briefs, backtest artifacts). |

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

The stack boots cleanly with no third-party keys — agents start, the dashboard renders, the test suite passes. **v2.6 changes the failure posture:** the cost-breaker is **off** by default (P0), so missing credentials surface as real errors instead of being silently swallowed into a synthetic-skip placeholder. That's deliberate — you want to see what's wired and what's not.

### Recommended path: rotate via the admin API (v2.6)

The admin API (P3) stores credentials as sops-sealed YAML under `secrets/sealed/*.yaml.enc` and never returns plaintext to the dashboard after the initial paste. This is the production-supported path.

```bash
# One-time setup: install sops + an age key on the host (skip if already done)
# brew install sops age   /   apt install sops age
# age-keygen -o ~/.config/sops/age/keys.txt

# Rotate a key via the API
curl -s -X POST http://localhost:8090/admin/secrets/deepseek_api_key/rotate \
  -H 'Content-Type: application/json' \
  -d '{"value":"sk-your-key-here"}'

# Verify the connector
curl -s -X POST http://localhost:8090/admin/connectors/deepseek/test
```

Or use the dashboard: open <http://localhost:4173/admin/connectors>, click **Test** on any row, and use the rotate flow when prompted.

### Legacy path: edit .env directly (still works)

```bash
sed -i 's|^DEEPSEEK_API_KEY=$|DEEPSEEK_API_KEY=sk-your-key-here|' .env
docker compose restart orchestrator agent_intelligence agent_secretary \
  agent_persona agent_fundamental agent_quant agent_board
```

### LLM providers

The stack is built around **DeepSeek v4** as primary, with Anthropic and Groq as fallbacks. Sealed-secret slot names: `deepseek_api_key`, `anthropic_api_key`, `groq_api_key`, `openai_api_key` (for embeddings).

### Market data (Intelligence agent)

For real news / market data, set any subset of:

| Provider | Env var / secret slot | Use |
|----------|---------|-----|
| FRED | `FRED_API_KEY` / `fred_api_key` | Macro releases — drives the v2.6 P2.8 hourly FRED pull |
| GDELT | (no key needed) | Global event map (v2.6 P5); poll cadence 15 min via `cron:intel_gdelt_pull` |
| NewsAPI | `NEWSAPI_KEY` / `newsapi_key` | High-volume news (optional) |
| Polygon  | `POLYGON_API_KEY` | US equities + options |
| AlphaVantage | `ALPHAV_API_KEY` | Backup quote source |
| Tushare | `TUSHARE_TOKEN` | China equities |
| OpenBB | `OPENBB_PAT` | Aggregated free sources |

The intelligence agent reads:
- `INTEL_AUTOSTART=1` — start the live pipeline at boot
- `INTEL_CRAWLER_BACKEND=rss+gdelt` — drive both RSS and GDELT (default in v2.6)
- `INTEL_HASH_STORE_BACKEND=redis` / `INTEL_SEMANTIC_INDEX_BACKEND=pgvector` / `INTEL_EVENT_STORE_BACKEND=postgres` — pick real backends instead of in-memory defaults
- `INTEL_MACRO_BACKEND=fred` — turn on the FRED macro source
- `INTEL_EMBED_BACKEND=llm` — route the semantic-dedupe embedder through the LLM router

### WeChat push (Secretary agent)

If you want briefs pushed to WeChat group bots, rotate `wecom_bot_url` via the admin API or fill in the `WECOM_*` vars. See [`workflows/20_NOTIFIER_WECHAT.md`](workflows/20_NOTIFIER_WECHAT.md). Skipping this just means briefs stay on the dashboard (and in `lake.advice`).

### FUTU (multi-account, read-only)

The FUTU agent stays profile-disabled by default (`docker compose --profile futu up ...`). Once enabled, manage broker bindings via <http://localhost:4173/admin/brokers> — the **Verify** button performs a read-only `get_global_state` round-trip; the trade-unlock surface is permanently disabled at the [wrapper allow-list](apps/agent_futu/futu/readonly_client.py) + the `lake.futu_audit` chain trigger + revoked UPDATE/DELETE grants.

---

## 5. Toggling v2.5 trading-room and v2.6 feature flags

The Investment Board + Trading-room DAG (v2.5 N3.3) ship but are **off by default**. The cost-breaker (v2.6 P0) is also off by default. To enable / tune:

```bash
# Edit /srv/iic/featureflags/flags.yaml — relevant keys:
#   trading_room.event_triage.enabled: true       # v2.5
#   trading_room.investment_board.enabled: true   # v2.5
#   cost_breaker.enabled: false                   # v2.6 P0 — keep off until you have real spend data
#   llm.concurrency.default: 4                    # v2.6 P0.5 — per-caller_id concurrency cap

# Bounce affected services
docker compose restart orchestrator agent_board agent_intelligence agent_secretary
```

Or use the dashboard: <http://localhost:4173/admin/agents> for a flags YAML editor that chains a row to `lake.config_audit`.

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

The Trading Room view should populate within ~5 seconds. v2.6 P5.5 adds a second subject (`intel.event.geo_cluster.v1`) routed through the same trading-room DAG — useful for testing the geo-driven trigger path.

### v2.6 environment knobs (in addition to .env)

| Env var | Default | Effect |
|---|---|---|
| `IIC_REPO_ROOT` | (auto-detected) | Set in containers; replaces brittle `parents[N]` arithmetic (P1.6). |
| `LLM_MONTHLY_CAP_USD` | `inf` | Restore a monthly cap once `lake.llm_calls` has real spend data (P0.3). |
| `IIC_RATE_<PROVIDER>_<TIER>` | builtin | Override RPS per (provider, tier), e.g. `IIC_RATE_DEEPSEEK_PRO=8` (P0.4). |
| `IIC_PG_BASE_IMAGE` | `timescale/timescaledb-ha:pg16` | Pin Postgres by digest in production (P1.4). |
| `IIC_E2E_LIVE` | `0` | Set to `1` to run the gated end-to-end live-trace test (P9.6). |

---

## 6. Running the test suite

The Python test suite covers the orchestrator, the schema validators, every agent's logic, the chaos drills, and the v2.6 admin API + e2e topology gate:

```bash
make test
```

Expect (v2.6) the root-level sweep to report ~**324 passed, 9 skipped, 0 failed**; per-app suites add another ~250 passing tests when run individually. Skips are intentional and env-gated:

- `IIC_INTEGRATION=1` — Postgres-backed audit chain, NATS publish/subscribe smoke, Chroma smoke
- `IIC_RUN_COST_CHAOS=1` — real-DeepSeek cost-cap chaos
- `IIC_RUN_PG_AUDIT=1` — FUTU audit chain backend integration
- `IIC_E2E_LIVE=1` — v2.6 P9.6 first-live-trace gate (the definition of "no longer a prototype")

To run just the new v2.5 N3 tests:

```bash
PYTHONPATH=packages/featureflags:packages/schema:packages/llm-client:packages/data-bus:packages/prompts:packages/notifier:packages/data-lake:apps/orchestrator:apps/agent_persona:apps/agent_quant:apps/agent_fundamental:apps/agent_futu:apps/agent_secretary:apps/agent_backtest:apps/agent_intelligence:apps/agent_board \
  pytest -q apps/agent_board/ \
            apps/orchestrator/tests/test_event_triage.py \
            apps/orchestrator/tests/test_trading_room_dag_e2e.py \
            tests/test_team_plan_e2e.py \
            tests/test_trading_room_brief_format.py
```

To run just the new v2.6 D7 tests:

```bash
# P0 — cost-gate behaviour
pytest -q packages/llm-client/tests/test_cost_meter.py \
          packages/llm-client/tests/test_caller_concurrency.py \
          packages/llm-client/tests/test_telemetry_outcomes.py \
          packages/featureflags/tests/test_defaults.py \
          packages/featureflags/tests/test_paths.py

# P3 — admin API
(cd apps/admin_api && pytest -q tests/)

# P6 — secretary leader-router
(cd apps/agent_secretary && SECRETARY_ALLOWED_USERS=u1,u2 pytest -q tests/test_p6_router.py)

# P7 — quant regime detector
(cd apps/agent_quant && pytest -q tests/test_regime.py)

# P9 — e2e topology gate
pytest -q tests/e2e/
```

### CI gates (v2.6 P1.5 + P1.7)

- `.github/workflows/static-checks.yml` — `shellcheck` for `deploy/*.sh`, `hadolint` for every Dockerfile, the [`lint_hypertable_pk.py`](tools/lint_hypertable_pk.py) alembic-PK check, and a `parents[N>=2]` forbidden-pattern grep.
- `.github/workflows/fresh-bringup.yml` — daily clean Ubuntu re-runs `make setup` end-to-end so the bring-up bugs from [D6 §1](plan/D6_Architecture_Review_Prototype_to_Product.md) can't silently regress.

---

## 7. Troubleshooting

### "permission denied while trying to connect to the Docker daemon socket"

This was the most common first-run failure: `usermod -aG docker` only takes effect in a new login session, but you're still running `make setup` in the old session.

**`setup.sh` now handles this automatically** — it detects the case and re-execs itself under `sg docker` so the rest of the steps inherit the new group. If you saw this error on an older version, re-run `make setup` and it should now sail through.

If the auto-fix somehow doesn't kick in, three manual fixes (pick one):

```bash
# 1) Open a new terminal tab/window, then re-run `make setup`
# 2) In the current shell: `newgrp docker` then `make setup`
# 3) Log out + log back in, then re-run `make setup`
```

Either way the markers under `/var/lib/iic-deploy/` mean already-finished steps are skipped — you pick up exactly where it failed.

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

**What IS safe to commit:**

- `secrets/sealed/*.yaml.enc` — sops-encrypted, opens only with the host's age key. The whole point is that the encrypted blob lives in git.
- `.github/workflows/*.yml` — CI gates (v2.6 P1.5, P1.7).
- `docs/runbooks/*.md` — operational runbooks (v2.6 P9.5).
- `deploy/drills/*.sh` — restore drill (v2.6 P9.4).

You can safely `git add -A` after running `make setup` — none of the plaintext secret material lands in the working tree.

---

## 9. Going further

- **Architecture overview:** [`README.md`](README.md), [`workflows/00_INDEX_AND_CONVENTIONS.md`](workflows/00_INDEX_AND_CONVENTIONS.md)
- **The v2.5 trading-room iteration:** [`plan/D5_IIC_Prototype_Review_and_Next_Iteration.md`](plan/D5_IIC_Prototype_Review_and_Next_Iteration.md)
- **The v2.6 prototype-to-product audit + plan:** [`plan/D6`](plan/D6_Architecture_Review_Prototype_to_Product.md) + [`plan/D7`](plan/D7_IIC_Development_Plan_Prototype_to_Product.md)
- **Investment Board internals:** [`workflows/43_INVESTMENT_BOARD.md`](workflows/43_INVESTMENT_BOARD.md)
- **FUTU read-only safety story:** [`docs/security/FUTU_readonly_review.md`](docs/security/FUTU_readonly_review.md)
- **Production runbooks (v2.6 P9.5):** [`docs/runbooks/`](docs/runbooks/)
- **Production hardening:** [`infra/linux/bootstrap.sh`](infra/linux/bootstrap.sh) + [`workflows/31_PRODUCTION_HARDENING.md`](workflows/31_PRODUCTION_HARDENING.md)
- **Restore drill (v2.6 P9.4):** [`deploy/drills/restore_drill.sh`](deploy/drills/restore_drill.sh) — run weekly on the production box.

---

## Disclaimer

IIC is a personal research tool. It is **suggestion-only** and does not place orders. Nothing emitted by the system is investment advice. The FUTU integration is read-only by construction (wrapper allowlist + nftables firewall + audit chain + revoked DB writes); see the security review for the defence-in-depth story.
