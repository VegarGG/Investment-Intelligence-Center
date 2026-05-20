# D9 — IIC System Re-baseline + Live Map Design (v2.7)

**Audience:** Ziwei (vibe-coder)
**Authors:** architect-reviewer agent + ai-engineer agent
**Date:** 2026-05-19
**Companion:** `D7.1_IIC_Hotfix_Plan_v2.6.1.md` (the wiring fixes that close D7)
**Supersedes for architecture sections:** `D6_Architecture_Review_Prototype_to_Product.md` §2 component map
**Branch in scope:** [`feat/v2.6-d7-prototype-to-product`](https://github.com/VegarGG/Investment-Intelligence-Center/tree/feat/v2.6-d7-prototype-to-product)

> **Decisions log (2026-05-19, post-publication).** The six "open questions" in §8 were resolved by Ziwei the same day. Summary:
>
> 1. **AGPL-3.0 vendoring is safe.** IIC is personal-use only, no commercial plans. Vendoring worldmonitor bits is fine *with* attribution; the LiveMap README must reference koala73/worldmonitor.
> 2. **Map route is `/map`** and IIC ships **flat map only**. The 3D globe (`EventGlobe.tsx`) is retired — see §5.9.
> 3. **Severity scale `1..5` confirmed** for `lake.geo_events.severity`.
> 4. **Demo mode (`IIC_DEMO=on`) is OK** to bake into `docker-compose.yml` defaults, but the dashboard / README must surface it explicitly as "demo mode is on".
> 5. **WeChat is deferred** from V3 scope. V3 ends at `lake.advice` persistence + a JSON brief artifact; no notifier send.
> 6. **Flat map only** (collapsed into decision 2).
>
> Every section below reflects these decisions inline. §8 retains the original open questions for traceability but each is now annotated with the resolution.

> **Why a numbering jump to D9.** D8 already exists in this folder as `D8_Executive_Summary_PrototypeReview_EN_ZH.pdf` (May 10, the bilingual executive summary of the prototype review). It is a summary, not a plan — but the slot is taken. D9 is the next planning slot. (If you'd rather call this v2.7 in commits and PRs, the doc is named accordingly: `_v2.7.md`.)

> **Reading order.** If you only have time for one section, read §3 (re-baselined component map) and §5 (Live Map design). §1–§2 are the postmortem. §4 is root-cause forensics for the bringup. §6 is the vibe-coding sprint plan.

---

## 0. TL;DR (one screen)

The v2.6 bringup proved one architectural truth that D6 only suspected: **the IIC has a build-time identity and a runtime identity, and the two have never been the same system.** Every gap the bringup found — router unbound, `/chat` auth mismatch, hypertable index collisions, missing nginx route for the map — is a different face of one root cause: *we kept adding code without an integration test that exercises the whole stack against real keys.*

D7.1 fixes the immediate symptoms. D9 fixes the design so the symptoms stop recurring. Specifically:

- **§3** — Re-derived component map. Single source of truth for boot order, who calls whom, who reads what from the lake.
- **§4** — Live map root cause. The `nginx/1.27` 404 is a routing problem, not an app problem. Fixable in 5 minutes; design discussion is the bigger lift.
- **§5** — Live Map design. Vendor a small set of files from `koala73/worldmonitor` (deck.gl + MapLibre flat-map layer) into `apps/dashboard/src/components/LiveMap.tsx`. Keep IIC's `lake.geo_events` contract. Personal-use-only confirmed (decision 1) — AGPL-3.0 vendoring is safe with attribution. Flat map only; 3D globe retired (§5.9).
- **§6** — Vibe-coding sprint V1→V6, each one self-contained, each ending with a CI-checkable acceptance.

The shape of the next 4–6 weeks: V1 wiring (D7.1) → V2 live map → V3 demo-able full loop (one real event → board decision → brief) → V4 secretary as router → V5 FUTU quotation → V6 observability + runbooks.

---

## 1. What the bringup actually told us

Five symptoms, **one** structural disease.

### 1.1 The five symptoms

| # | Symptom | Surface area | What the operator sees |
|---|---|---|---|
| **S1** | `lake.llm_calls = 0` after full smoke matrix | every agent | "the keys work but nothing actually calls them" |
| **S2** | `/chat` returns `user_id: anon` regardless of input | secretary | "the allowlist never matches" |
| **S3** | Map route returns literal `nginx/1.27` 404 page | dashboard | "the map is broken, I can't see geo intel" |
| **S4** | Migrations 0007 + 0010 fail with `relation already exists` | data-lake | "the database half-deploys" |
| **S5** | Notifier package fails `pip install -e` under PEP 517 | build | "fresh build fails on iic-base" |

### 1.2 The shared root cause

Each symptom lives at the boundary between two components that nobody owned during the patch that introduced them:

- **S1** lives between `llm_client` and every agent's `main.py`. The router exists. Agents exist. Nobody owned the *handshake*.
- **S2** lives between the dashboard / curl client and `routes_chat.py`. Both sides have a notion of "user". Neither one is documented as the source of truth.
- **S3** lives between Vite's SPA-routing assumption and nginx's `try_files` config. Both work in isolation. Neither is correct as a system.
- **S4** lives between alembic's `op.create_index(...)` and TimescaleDB's `create_hypertable(...)` auto-index. Both are correct in isolation. Together they collide on the same index name.
- **S5** lives between Poetry's `package-mode = false` and pip's PEP 517 expectations. Both work for a developer using `poetry shell`. Neither works when `iic-base` runs `pip install -e`.

The disease is: **no one is writing tests at boundaries**. We test what's inside `llm_client/`. We test what's inside `apps/agent_secretary/`. We do not test that the agent at boot binds the router. Until we do — boundary symptoms recur every release.

This is the architectural finding that drives the rest of the document. R1 in D7.1 plugs S1 specifically. §3 (boundary-first component map) and §6.V2 (LiveMap acceptance tests at the dashboard ↔ nginx ↔ lake boundary) plug the *class* of problem.

### 1.3 What's working (don't break it)

D6 was harsh because the prototype was very prototype. The bringup confirms most of D6's "real" column is still real:

- Substrate (Postgres + TimescaleDB + pg_partman + pgvector, NATS, Redis) — still real.
- Migration framework — still real (after the 0007/0010 fixes).
- Six-agent skeleton + DAG + advice ledger — still real.
- `admin_api` connector-test endpoints — **upgraded from absent to real** in D7. This is the one bright spot of the bringup: those `/admin/connectors/*/test` routes correctly validated three real keys.
- `iic-base` packaging — **upgraded from absent to real** in D7 + the in-session notifier fix.
- Dashboard build + EventGlobe TypeScript — **green after the in-session fix**.

D9 protects that surface. It does not redesign the substrate.

---

## 2. The "vibe coding" failure mode, named and bounded

Ziwei's framing in the user message: *"many issues found so far is due to the unclear design and some function missingness during vibe coding."*

That diagnosis is correct, and it's worth giving it a precise definition so we can defend against it.

**Vibe-coding gap (n.):** the class of bug introduced when an agent (or a human) writes code that is locally correct but globally unintegrated — passing every unit test in its own module while breaking a contract with a module on the other side of a boundary the agent didn't read.

Every bug in §1.1 is a vibe-coding gap. The defense against vibe-coding gaps is **not "more careful prompting"** (that's a fragile defense). The defense is:

1. **A canonical component map** that names every boundary and what crosses it. (§3.)
2. **A boot sequence diagram** that says explicitly what must be true at startup. (§3.4.)
3. **At least one integration test per boundary** that fails loudly if the contract drifts. (Per-phase in §6.)
4. **A demo-able end-to-end path** that exercises every boundary at least once. (§6.V3.)
5. **A naming convention for "the thing that connects two modules"** — a `bootstrap`, a `wire`, a `lifespan` — so future agents pattern-match on it. (§3.2.)

That's the architectural through-line of D9. Every vibe-prompt in §6 ends with the boundary contract its acceptance criterion must defend.

---

## 3. Re-baselined component map

This supersedes D6 §2 (which was correct as a snapshot but is now outdated). What follows is the v2.6 reality plus what D7.1 and D9 will land.

### 3.1 Logical layers (top-down)

```
┌─────────────────────────────────────────────────────────────────────┐
│                    OPERATOR INTERFACES (humans + apps)              │
│  WeChat / Telegram  •  Dashboard SPA  •  CLI / curl  •  admin UI    │
└────────────────────────────────┬────────────────────────────────────┘
                                 │ HTTP / WebSocket
┌────────────────────────────────┴────────────────────────────────────┐
│                    EDGE  ::  nginx + Vite static                    │
│  routes /api/*  → agents      routes /*  → SPA fallback (NEW §4)    │
│  routes /admin/* → admin_api  routes /map → SPA (FIX §4)            │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
┌──────────────┬──────────┬──────┴───────┬─────────────┬──────────────┐
│  secretary   │ persona  │  fundamental │   quant     │   board      │  ← strict-LLM
│  (front      │ (analyst │  (filings    │ (regime +   │ (Bull/Bear/  │
│   router)    │  daily)  │  cover-ltrs) │ factors)    │  Risk/Chair) │
└──────┬───────┴──────────┴──────────────┴─────────────┴──────┬───────┘
       │                                                       │
       │              ┌─────────────────────┐                  │
       └─────────────►│   orchestrator      │◄─────────────────┘
                      │   (rule-based       │
                      │    fanout DAG)      │
                      └──────┬──────────────┘
                             │
       ┌─────────────────────┴────────────────────┐
       │           agent_intelligence              │   ← optional-LLM
       │  RSS, GDELT, dedupe, embeddings, macro    │
       │  → produces lake.intel_embeds,            │
       │    lake.geo_events, lake.intel_briefs      │
       └─────────────────────┬─────────────────────┘
                             │
              ┌──────────────┴───────────────┐
              │   shared packages (no procs) │
              ├──────────────────────────────┤
              │  llm_client (router + cost)  │  ← NEW boundary owner (§3.2)
              │  schema (pydantic models)    │
              │  featureflags                │
              │  data_bus (NATS wrapper)     │
              │  data_lake (alembic + DSN)   │
              │  notifier (WeChat / email)   │
              │  prompts (jinja templates)   │
              └──────────────┬───────────────┘
                             │
              ┌──────────────┴───────────────┐
              │       SUBSTRATE              │
              ├──────────────────────────────┤
              │  Postgres + TimescaleDB +    │
              │   pg_partman + pgvector       │
              │  NATS JetStream + KV         │
              │  Redis                        │
              │  FUTU OpenD (read-only, B+)  │
              └──────────────────────────────┘
```

### 3.2 Boundary contracts (who owns the handshake)

This is the table that was missing from D6 and that the bringup made the case for. Every row is a vibe-coding-gap target.

| Boundary | Producer | Consumer | Contract | Owner | Tested by |
|---|---|---|---|---|---|
| **Env vars → LlmRouter** | docker-compose `.env` | every agent's `lifespan` | `bootstrap_router_or_die(name)` in `llm_client.bootstrap` (D7.1 §H0.1) | `packages/llm-client/` | `tests/llm_client/test_bootstrap.py` + smoke (D7.1 §H0.3) |
| **HTTP `/chat` → user_id** | dashboard / curl | secretary `routes_chat.py` | `X-User-Id` header preferred; body `user` accepted; `anon` fallback (D7.1 §H1.1) | `apps/agent_secretary/` | `tests/secretary/test_chat_auth.py` |
| **Secretary → orchestrator fanout** | secretary `morning_brief` | orchestrator `/route/*` | JSON `{intent, payload}` POST. Today returns 404 (bringup symptom). | `apps/orchestrator/` | new in §6.V4 |
| **Agents → lake.llm_calls** | router `_audit_call` | telemetry sink | every call writes a row with `caller_id`, `outcome`, `latency_ms` (D6 P0.6) | `packages/llm-client/telemetry.py` | smoke step 3 (D7.1 §H0.3) |
| **agent_intelligence → lake.geo_events** | intel pipeline | dashboard LiveMap (§5) | `{ts, lat, lon, severity, source, actor1, actor2, summary, url}` | `apps/agent_intelligence/intel/geo.py` | new in §6.V2 |
| **Dashboard /map route** | nginx | SPA `LiveMap.tsx` | SPA fallback via `try_files $uri /index.html` (§4) | `infra/nginx/dashboard.conf` | playwright smoke (§6.V2) |
| **alembic → TimescaleDB hypertable indexes** | migrations | timescale extension | don't create `<t>_<tcol>_idx` manually after `create_hypertable` (D7.1 §H2.4) | `packages/data-lake/.../migrations/` | `tools/lint_hypertable_indexes.py` |
| **iic-base → packages/notifier** | Dockerfile | `pip install -e` | every package under `packages/` must be installable under PEP 517 (D7.1 §H2.3) | `infra/iic-base/Dockerfile` | grep lint |
| **Dashboard build → react-globe.gl** | Dockerfile | `npm ci` | lockfile checked in, build uses `ci` not `install` (D7.1 §H2.5) | `apps/dashboard/Dockerfile` | per-PR build |

Every row above is a vibe-coding gap that has bitten us. The list is exhaustive **for what's been observed.** New rows get added as new gaps surface.

### 3.3 What changed vs. D6 §2

| Component | D6 status | D9 status | Note |
|---|---|---|---|
| admin_api | absent | **shipped** (port 8090) | connector-test endpoints validated 4 keys in bringup |
| iic-base image | absent | **shipped** | P1.1 from D7 |
| notifier | broken on PEP 517 | **fixed in-session** (`fb06e9d`) | lint added in D7.1 §H2.3 |
| EventGlobe.tsx | absent | **shipped with TS issues** (now fixed) | flat-map LiveMap is new in §5 |
| LLM router bootstrap | absent | **planned (D7.1 §H0)** | the load-bearing fix |
| `lake.geo_events` table | absent in D6 schema | **shipped in migration 0010** | LiveMap consumes this directly |
| Secretary as dispatcher | not implemented | not implemented | still §6.V4 work |
| Hypertable PK lint | shipped (P1.5) | shipped | + new index-collision lint (D7.1 §H2.4) |

### 3.4 Boot sequence (what must be true at agent startup)

This was never written down. The bringup happened because of it.

```
T0   docker compose up
T1   substrate containers up (postgres, nats, redis)        ← healthcheck
T2   migrations run                                         ← run-migrations.sh
T3   agent containers start
T4     for each agent main.py:
T4.1     read env vars
T4.2     bootstrap_router_or_die(SERVICE_NAME)              ← D7.1 §H0
T4.3     set_router(router)                                  ← global handle
T4.4     register routes, return app
T5   uvicorn listens on :PORT
T6   /health returns 200
T7   smoke-check.sh runs:
T7.1   structural: each agent /health == 200
T7.2   wiring:    /chat/echo returns llm_call_id            ← D7.1 §H0.3
T7.3   telemetry: lake.llm_calls has row                    ← D7.1 §H0.3
```

T4.2 is what doesn't happen today. T7.2 and T7.3 are what doesn't get asserted today. Both gaps are closed by D7.1.

---

## 4. The nginx 404 — root cause of the broken map

User report: *"the interactive map is not working and responding `<html>...nginx/1.27...</html>`."*

That HTML body is nginx's *default* 404 page. The string `nginx/1.27` is the server version. nginx is responding before any IIC code runs. There are three possible reasons:

### 4.1 The three candidate root causes

| # | Hypothesis | Why it's plausible | How to test |
|---|---|---|---|
| **N1** | **SPA route fallback missing.** nginx serves `apps/dashboard/dist/` as static, but no `try_files $uri $uri/ /index.html` directive. So `/map` resolves to a file that doesn't exist on disk → 404. | This is the textbook reason a Vite SPA breaks on direct-link to a sub-route on nginx. Default `try_files $uri =404;` is the worst possible default for an SPA. | `curl -i :PORT/map` returns 404 with `Server: nginx/1.27`. `curl -i :PORT/` returns the index.html. → confirms N1. |
| **N2** | **Map route not registered in React Router.** The route in `App.tsx` is, say, `/event-globe` not `/map`, and nginx is correctly falling through to index.html, which then renders a "not found" component for `/map` → React-rendered 404, not nginx. | Possible but inconsistent with the symptom: the user saw the nginx-shaped HTML, not a React-styled 404. | Source-view the response. If it has `<div id="root">` in the HTML, it's React. If it has only the nginx HTML, it's nginx. |
| **N3** | **Dashboard not actually built into the image.** The container is serving a stale `dist/` from before EventGlobe was added, or the build failed and nginx is serving an empty docroot. | Possible, given the bringup found the dashboard build was broken until `fb06e9d`. | `docker exec dashboard ls /usr/share/nginx/html` should show `index.html` + a hashed `assets/` bundle. |

The probability distribution, given the bringup context: **N1 most likely (≈60%), N3 next (≈25%), N2 last (≈15%).** N1 is the textbook bug for Vite-on-nginx and we have no evidence the dashboard nginx config has been re-tested since the LiveMap idea was added.

### 4.2 The fix that covers all three

**File:** `infra/nginx/dashboard.conf` (or wherever the dashboard's nginx config lives — bringup didn't enumerate it; grep for `listen 80` under `infra/`)

```nginx
server {
    listen 80;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    # API proxy — every /api/* request goes to the relevant agent.
    # (List is illustrative. Use the existing block as-is.)
    location /api/secretary/  { proxy_pass http://agent_secretary:8080/; }
    location /api/intel/      { proxy_pass http://agent_intelligence:8081/; }
    location /api/admin/      { proxy_pass http://admin_api:8090/admin/; }
    # ... etc ...

    # WebSocket for LiveMap streaming (§5.5):
    location /api/stream/ {
        proxy_pass http://agent_intelligence:8081/stream/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }

    # SPA fallback — THIS IS THE LINE THE BRINGUP IS MISSING.
    # Any non-API path falls through to index.html so React Router can resolve it.
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

Plus a build-time assertion that `index.html` exists in the docroot:

```dockerfile
# In apps/dashboard/Dockerfile, after the build stage:
RUN test -f /usr/share/nginx/html/index.html || (echo "no index.html in docroot" && exit 1)
```

That covers N1 (try_files), N3 (build assertion), and partially N2 (if the route isn't registered in React, it will render a React 404, which is at least a different problem with a different fix).

### 4.3 Why this wasn't found earlier

D6 §2 says the map dashboard was *absent*. D7 §P5 added it back. Between D7-merge and the bringup nobody clicked the `/map` URL on the live container. Add a playwright smoke (§6.V2) so this never re-recurs.

---

## 5. Live Map design

### 5.1 Goal

A single page in the dashboard at `/map` (or `/live-map`) that:

1. Renders a 2D world map (preferred over 3D globe for density of geopolitical events).
2. Plots events from `lake.geo_events` as markers, colored by severity, clustered at low zoom.
3. Streams new events in real time (WebSocket fanout from `agent_intelligence`).
4. Filters by `severity`, `category`, `time window`, `actor`, `keyword`.
5. Click-through to the underlying brief / source URL.

This is the dashboard surface for the geopolitical half of the IIC mission ("collect, analyze, visualize and brief the important geopolitical and financial event"). The Investment Board is the financial half; the LiveMap is the geopolitical half.

### 5.2 worldmonitor adoption: what to vendor, what to skip

`koala73/worldmonitor` (44.1k stars, AGPL-3.0) is a far larger system than the IIC needs. Its tech stack (per its README):
- Vanilla TypeScript + Vite (matches our Vite; not React, so we adapt rather than copy)
- **globe.gl + Three.js** for 3D globe
- **deck.gl + MapLibre GL** for the WebGL flat map
- Tauri 2 for native desktop builds
- Protobuf API contracts (92 protos, 22 services)
- 435+ curated news feeds across 15 categories
- 21 languages

The IIC does not need most of that. **What we vendor:**

| worldmonitor piece | IIC use | Why | Path target |
|---|---|---|---|
| **deck.gl `ScatterplotLayer` + `IconLayer` pattern over MapLibre GL** | the flat map + event markers | Production-tested with thousands of points; same stack we'd choose from scratch | `apps/dashboard/src/components/LiveMap/MapCanvas.tsx` |
| **Hex-cluster aggregation pattern (`HexagonLayer`)** | event density at low zoom | Makes 10k+ events legible without choking the browser | same file |
| **MapLibre style JSON** (basemap) | dark/light basemaps | Self-hostable tiles, no Mapbox token | `apps/dashboard/public/map-styles/` |
| **Time-window filter UI shape** | filter sidebar | Their interaction grammar is good | `apps/dashboard/src/components/LiveMap/FilterPanel.tsx` |

**What we explicitly do NOT vendor:**

- globe.gl integration — we are dropping the 3D globe entirely (decision 2 / §5.9). IIC ships flat map only.
- News-feed aggregation — IIC has its own pipeline (agent_intelligence).
- Tauri desktop builds — out of scope; IIC is browser-only.
- Country Intelligence Index UI — could be a future widget, not part of this slice.
- 21-language i18n — single-locale (English) for now.
- Protobuf contracts — we use OpenAPI/REST + JSON over the lake schema.

### 5.3 License posture — decision recorded

worldmonitor is **AGPL-3.0** ("Commercial license required for any commercial use" — per its README).

**Decision (Ziwei, 2026-05-19):** IIC is personal-use only, with no commercial plans. AGPL-3.0 vendoring is safe. The vibe-coding agent **must** add a worldmonitor reference in the IIC top-level README + the LiveMap component README.

**Concrete obligations the vibe agent must execute when vendoring (V2):**

1. **Isolate vendored code** under `apps/dashboard/src/components/LiveMap/_vendor_worldmonitor/`. This is the only directory in the repo where AGPL-3.0 applies.
2. **Drop `LICENSE.AGPL-3.0`** into that directory (verbatim text from <https://www.gnu.org/licenses/agpl-3.0.txt>).
3. **Add a per-file header** to every vendored file:
   ```ts
   // Adapted from koala73/worldmonitor (AGPL-3.0, © Elie Habib 2024-2026).
   // Source: https://github.com/koala73/worldmonitor
   // Modified by the IIC project under the same AGPL-3.0 terms for non-commercial use.
   ```
4. **Append to top-level `README.md`** a "Third-party attributions" section (or append to one if it exists):
   ```markdown
   ## Third-party attributions

   The Live Map (`apps/dashboard/src/components/LiveMap/`) adapts patterns from
   [koala73/worldmonitor](https://github.com/koala73/worldmonitor) (AGPL-3.0,
   © Elie Habib 2024–2026). Vendored bits live under
   `LiveMap/_vendor_worldmonitor/` and carry AGPL-3.0 headers; the surrounding
   IIC code is unaffected. IIC is operated as a personal/research project and
   makes no commercial use of worldmonitor's code.
   ```
5. **Add a LiveMap-component-level README** at `apps/dashboard/src/components/LiveMap/README.md` documenting which worldmonitor commit SHA was vendored from, which files are derived, and which are IIC-original. This is for future-us — if worldmonitor's license ever changes upstream, we want to know exactly what we have.

**Adapt rather than copy where possible.** worldmonitor is vanilla TypeScript; IIC is React. Most "vendoring" will inevitably be re-implementing the *pattern* (e.g. the hex-cluster layer config, the severity color ramp) rather than copy-pasting verbatim. That reduces obligation to courtesy attribution; we still do the full attribution above for safety.

**If commercial intent ever appears later:** stop vendoring immediately, rewrite the `_vendor_worldmonitor/` subtree from scratch using only public docs of deck.gl + MapLibre GL, then delete the worldmonitor LICENSE + attributions. Make this decision visible: track "commercial-intent" as a project-level flag that requires a re-licensing pass before flipping.

### 5.4 Component layout

```
apps/dashboard/src/
├── App.tsx                            # add <Route path="/map" element={<LiveMapPage/>} />
│                                      # ALSO: remove the EventGlobe route — see §5.9
├── pages/
│   └── LiveMapPage.tsx                # route entry
├── components/
│   ├── EventGlobe.tsx                 # ❌ DELETE in V2 — flat map only (§5.9)
│   └── LiveMap/
│       ├── index.ts                   # public exports
│       ├── LiveMap.tsx                # top-level container
│       ├── MapCanvas.tsx              # deck.gl + MapLibre GL canvas
│       ├── FilterPanel.tsx            # severity / category / time / actor
│       ├── EventDrawer.tsx            # right-side panel when you click a marker
│       ├── useGeoEventsStream.ts      # WS hook → lake.geo_events stream
│       ├── useGeoEventsQuery.ts       # initial historical fetch
│       ├── types.ts                   # GeoEvent type alias matching schema
│       └── _vendor_worldmonitor/      # AGPL-3.0 vendored bits
│           ├── LICENSE.AGPL-3.0
│           ├── hex-cluster-layer.ts
│           ├── map-styles/
│           │   ├── dark.json
│           │   └── light.json
│           └── README.md              # what's adapted and from where
```

### 5.5 Data contract: `lake.geo_events` → frontend

The table `lake.geo_events` already exists (migration 0010, per bringup). Schema (inferred from the index name `geo_events_ts_idx`):

```sql
-- Inferred shape — verify against migration 0010
CREATE TABLE lake.geo_events (
    id          uuid PRIMARY KEY,
    ts          timestamptz NOT NULL,     -- TimescaleDB hypertable on this
    lat         double precision NOT NULL,
    lon         double precision NOT NULL,
    severity    smallint NOT NULL,        -- 1..5
    category    text NOT NULL,            -- 'military', 'economic', 'disaster', etc.
    actor1      text,
    actor2      text,
    summary     text NOT NULL,
    source      text NOT NULL,            -- 'gdelt', 'rss:<feedname>', etc.
    url         text,
    raw         jsonb                     -- original event for forensics
);
SELECT create_hypertable('lake.geo_events', 'ts');
```

Frontend type:

```typescript
export type GeoEvent = {
  id: string;
  ts: string;          // ISO-8601
  lat: number;
  lon: number;
  severity: 1 | 2 | 3 | 4 | 5;
  category: 'military' | 'economic' | 'disaster' | 'political' | 'cyber' | 'other';
  actor1?: string;
  actor2?: string;
  summary: string;
  source: string;
  url?: string;
};
```

### 5.6 API surface (new endpoints in agent_intelligence)

| Endpoint | Method | Purpose |
|---|---|---|
| `GET /api/intel/geo_events?since=...&until=...&category=...&severity_gte=...` | GET | historical fetch with filters; default last 24h, cap 5000 rows |
| `WS /api/intel/stream/geo_events` | WebSocket | live push of new rows as they land in `lake.geo_events` |

Both routes belong in `apps/agent_intelligence/agent_intelligence/routes_geo.py`. The WebSocket uses NATS subscription on the existing intel-publish subject and forwards JSON to connected clients. Cap concurrent WS connections per-IP at 4 to avoid resource starvation.

### 5.7 deck.gl + MapLibre integration sketch

```tsx
// apps/dashboard/src/components/LiveMap/MapCanvas.tsx
import maplibregl from 'maplibre-gl';
import { DeckGL } from '@deck.gl/react';
import { ScatterplotLayer } from '@deck.gl/layers';
import { HexagonLayer } from '@deck.gl/aggregation-layers';
import { MapView } from '@deck.gl/core';
import type { GeoEvent } from './types';

const SEVERITY_COLOR: Record<number, [number, number, number]> = {
  1: [110, 200, 255],   // info — blue
  2: [255, 235, 80],    // notice — yellow
  3: [255, 165, 0],     // warning — orange
  4: [255, 80, 80],     // serious — red
  5: [180, 0, 200],     // critical — magenta
};

type Props = { events: GeoEvent[]; styleUrl: string; };

export function MapCanvas({ events, styleUrl }: Props) {
  const layers = [
    new HexagonLayer({
      id: 'hex',
      data: events,
      getPosition: (e: GeoEvent) => [e.lon, e.lat],
      radius: 50_000,
      elevationScale: 50,
      opacity: 0.4,
      pickable: false,
      visible: events.length > 500,   // only cluster when dense
    }),
    new ScatterplotLayer({
      id: 'points',
      data: events,
      getPosition: (e: GeoEvent) => [e.lon, e.lat],
      getRadius: (e: GeoEvent) => 20_000 + e.severity * 10_000,
      getFillColor: (e: GeoEvent) => SEVERITY_COLOR[e.severity],
      pickable: true,
      opacity: 0.7,
      stroked: true,
      visible: events.length <= 500,
    }),
  ];

  return (
    <DeckGL
      initialViewState={{ longitude: 0, latitude: 20, zoom: 1.5 }}
      controller={true}
      layers={layers}
      views={new MapView({ repeat: true })}
    >
      {/* MapLibre basemap underneath deck.gl layers */}
      <maplibregl.Map mapLib={maplibregl} mapStyle={styleUrl} />
    </DeckGL>
  );
}
```

(Per worldmonitor's pattern — adapted, not copied verbatim. The hex-cluster threshold + severity color scheme are IIC choices.)

### 5.8 Acceptance for the LiveMap slice

| # | Test | Method |
|---|---|---|
| **L1** | `/map` route resolves on a fresh deploy (no nginx 404) | `curl -i :PORT/map` returns 200 + HTML containing `<div id="root">` |
| **L2** | LiveMap renders with no events | Open `/map` in playwright with empty lake; assert canvas + "no events in window" empty-state |
| **L3** | Historical fetch | Seed 100 fake events via SQL; reload `/map`; assert deck.gl `ScatterplotLayer` reports 100 features |
| **L4** | Streaming | Open `/map`; INSERT a new row into `lake.geo_events`; assert it appears within 5s |
| **L5** | Filter by category | Toggle `military` off; assert military events disappear |
| **L6** | Click-through | Click a marker; assert EventDrawer opens with `summary` + clickable `source URL` |
| **L7** | Hex cluster engages at scale | Seed 5000 events; assert HexagonLayer renders and ScatterplotLayer is hidden |
| **L8** | LICENSE compliance | `grep -r "AGPL-3.0" apps/dashboard/src/components/LiveMap/_vendor_worldmonitor/` returns ≥ 1 hit, AND top-level `README.md` contains a "Third-party attributions" section mentioning worldmonitor (per §5.3) |
| **L9** | EventGlobe is gone | `grep -rn "EventGlobe" apps/dashboard/src/` returns nothing, AND `apps/dashboard/package.json` no longer lists `react-globe.gl` or `three` (per §5.9) |

### 5.9 Retiring `EventGlobe.tsx` (3D globe)

**Decision 2/6:** flat map only. EventGlobe goes away. Steps to execute in V2:

1. Delete `apps/dashboard/src/components/EventGlobe.tsx`.
2. Remove the `<Route>` for the globe from `App.tsx` (and any nav-bar links).
3. Strip `react-globe.gl`, `three`, `@types/three` from `apps/dashboard/package.json` and `package-lock.json`. These were added in-session as the `fb06e9d` fix (Class A2/A3 in the bringup) — they're now technical debt because we don't ship the globe.
4. Rebuild the dashboard image; verify `npm run build` is clean and the resulting bundle is smaller (rough expectation: ~1.5 MB smaller after Three.js drops out).
5. Update `DEPLOYMENT.md` §2 if it lists a globe route.

**Acceptance for §5.9:** L9 above. Plus `du -sh apps/dashboard/dist/` is meaningfully smaller after the removal (sanity check that Three.js actually left the bundle).

**Why now, not later:** Three.js is one of the largest deps in the dashboard bundle and the in-session typing fix (Class A3) is fragile against future `react-globe.gl` releases (D7.1 §H2.5 / R9 partially mitigates this with `npm ci`, but the better answer is to not depend on it at all).

---

## 6. Vibe-coding sprint plan (V1 → V6)

Each "V" is a self-contained chunk. Acceptance is CI-checkable. Vibe prompts are paste-ready.

### V1 — D7.1 lands (wiring + smoke)

**Output:** D7.1 §H0 + §H1 + §H2 all green.

**Acceptance:** D7.1's T1–T10 matrix passes. `lake.llm_calls ≥ 1` after fresh-bringup smoke.

**Vibe prompt:** *"Implement all items in D7.1_IIC_Hotfix_Plan_v2.6.1.md, phases H0 → H2, in the order they appear. After each phase, run the acceptance check listed under that phase. At the end, run the full T1–T10 matrix and post the output."*

### V2 — Live map (the user-visible win)

**Output:** `/map` route resolves, renders, streams, filters, click-throughs.

**Sub-tasks:**
1. Fix nginx config per §4.2. SPA fallback + WS proxy + build-time docroot assertion.
2. Add `GET /api/intel/geo_events` + `WS /api/intel/stream/geo_events` to `agent_intelligence` per §5.6.
3. Create the component layout per §5.4.
4. Implement `MapCanvas.tsx` per §5.7 (deck.gl + MapLibre).
5. Vendor the hex-cluster pattern + 2 map-style JSONs from worldmonitor per §5.3, with full AGPL-3.0 attribution (LICENSE.AGPL-3.0, per-file headers, top-level README "Third-party attributions" section, LiveMap component-level README with vendor SHA).
6. **Retire EventGlobe per §5.9** (delete file, strip 3D deps, drop the globe route).
7. Add the L1–L9 playwright smoke per §5.8 (note: L9 is new — EventGlobe-is-gone assertion).

**Acceptance:** L1–L9 all green. CI runs the playwright smoke on every PR that touches `apps/dashboard/` or `apps/agent_intelligence/routes_geo.py`. Top-level `README.md` contains the worldmonitor attribution.

**Vibe prompt (split into three):**

   - *Prompt A (nginx + route)*: *"Per D9 §4.2, fix `infra/nginx/dashboard.conf` to add SPA fallback (`try_files $uri $uri/ /index.html`), `/api/stream/` WebSocket proxy, and a docroot-has-index.html build-time assertion in `apps/dashboard/Dockerfile`. Add a playwright test at `tests/dashboard/test_map_route_resolves.spec.ts` that does `await page.goto('/map')` and asserts the response status is 200 and the HTML contains `id=\"root\"`."*

   - *Prompt B (LiveMap)*: *"Per D9 §5.4–§5.8, build the LiveMap component tree under `apps/dashboard/src/components/LiveMap/` and the `LiveMapPage` route. Add the two `agent_intelligence` endpoints (REST historical + WS stream). Vendor only the hex-cluster pattern and two basemap JSONs from koala73/worldmonitor — place them under `_vendor_worldmonitor/` with `LICENSE.AGPL-3.0`, per-file headers (template in §5.3 step 3), a component-level `README.md` recording the vendor SHA, and append the 'Third-party attributions' block to the top-level repo README per §5.3 step 4. Add playwright tests L1 through L8 from D9 §5.8."*

   - *Prompt C (retire globe)*: *"Per D9 §5.9, delete `apps/dashboard/src/components/EventGlobe.tsx`, remove its route from `App.tsx` and any nav links, and strip `react-globe.gl`, `three`, `@types/three` from `apps/dashboard/package.json` + `package-lock.json`. Run `npm ci && npm run build`; the build must succeed. Add playwright test L9 from §5.8."*

### V3 — One real end-to-end loop (terminates at `lake.advice`)

**Output:** A documented sequence where one real RSS / GDELT event flows: ingest → embed → dedupe → store → trigger persona daily → trigger board → produce advice → write to `lake.advice` → emit a JSON brief artifact at `/api/secretary/brief/{advice_id}`, with every LLM hop recorded in `lake.llm_calls`.

This is the "demo-able full loop" that D7 promised as its Definition of Done but never delivered (because the wiring gap blocked it).

**Note (decision 5):** the WeChat connector is deferred. V3 ends at `lake.advice` + JSON-brief endpoint. Notifier integration moves to a later sprint (post-V6 or whenever WeChat becomes a focus).

**Sub-tasks:**
1. Configure one RSS feed end-to-end against real provider in `agent_intelligence` factory (replace `InMemoryCrawler` with real RSS crawler — D6 §M-I1).
2. Wire `agent_intelligence` → orchestrator → secretary fanout for the morning_brief intent.
3. Replace `flag_disabled` on `agent_board` with the actual flag check + ensure board enabled in default flags for demo mode (`board.enabled=true` when `IIC_DEMO=on` — see §6.demo-mode below).
4. Add `GET /api/secretary/brief/{advice_id}` that returns the composed brief as JSON (no notifier send). This is the V3 deliverable surface.
5. ~~Connect `lake.advice` writes to `notifier` for WeChat send~~ — **deferred (decision 5)**.

**Acceptance:** a curl to `POST /run/demo_loop` (new) returns the final advice id. `lake.llm_calls` shows ≥ 5 rows (intel synth + persona digest + bull + bear + chair). `lake.advice` shows 1 new row. `GET /api/secretary/brief/{advice_id}` returns a JSON object with the brief text + citations.

### §6.demo-mode — bake `IIC_DEMO=on` defaults (decision 4)

`IIC_DEMO=on` (default) flips:
- `SECRETARY_DEMO_ENDPOINTS=on` → `/chat/echo` reachable
- `board.enabled=true` → board doesn't `flag_disabled`
- Seeds 50 historical `lake.geo_events` rows on first migration so the LiveMap isn't blank
- Banners "**Demo mode is on**" prominently in:
  - the dashboard top bar (component: `apps/dashboard/src/components/DemoBanner.tsx`)
  - the top-level `README.md` "Quick start" section
  - `DEPLOYMENT.md` §1 ("Fresh bring-up")
  - The startup log of every agent: `logger.warning("IIC_DEMO=on — demo defaults active, do NOT use these for production")`

To disable: set `IIC_DEMO=off` in `.env` and recreate (`docker compose up -d --force-recreate`). The banner disappears, the seed migration is skipped on fresh DBs, and all the above defaults flip closed.

**Acceptance:**
- Fresh deploy with `IIC_DEMO=on` (default): banner visible at `/`, `/map` shows 50 events, `/chat/echo` reachable, `/decide` runs.
- Fresh deploy with `IIC_DEMO=off`: no banner, `/map` empty, `/chat/echo` returns 404, `/decide` returns `flag_disabled`.

### V4 — Secretary as router (the original vision)

**Output:** `/chat` actually plans → dispatches to N agents → composes a response.

This is D7's P6 ("secretary as leader-router") realized. Today secretary is one-way; it should be N-way fanout with composition.

**Sub-tasks:** see D6 §M-S1 and D7 §P6 verbatim. D9 doesn't redesign this, it just unblocks it (V1 makes the LLM available; V3 makes the downstream agents non-stub).

### V5 — FUTU quotation (the financial real-time layer)

**Output:** read-only FUTU OpenD endpoints exposed for the dashboard. `agent_futu` profile on by default.

See D6 §FUTU and the v2.5 plan. The audit trigger blocker is gone after migrations 0008+, so Phase B can light up.

### V6 — Observability + runbooks

**Output:** Grafana boards for `lake.llm_calls`, `lake.geo_events` ingest rate, `lake.advice` outcomes; runbooks for each agent.

This is D7 §P9 verbatim. D9 doesn't redesign it, just sequences it last.

---

## 7. Risk register (post-bringup, post-decisions)

| Risk | P | Impact | Mitigation |
|---|---|---|---|
| ~~AGPL-3.0 contamination via worldmonitor vendoring~~ | — | — | **Closed by decision 1** (2026-05-19, personal-use confirmed). Re-open if commercial intent ever surfaces. |
| LiveMap WebSocket fan-out saturates `agent_intelligence` under burst load | L | UI lag for connected operators | per-IP cap at 4 WS, server-side cap at 200; in V2 acceptance |
| `bootstrap_router_or_die` failing at startup masks a legit "ingest-only" agent run mode | L | inability to run substrate-only smoke | strict-mode matrix in D7.1 §H0.2 — `agent_intelligence`, `agent_quant`, `agent_backtest`, `orchestrator` opt-in to optional mode |
| Real FRED / DeepSeek keys leak via `lake.llm_calls` or audit log | M | credential leak | redact `api_key` in audit sink; CI grep for `sk-` and `pk_live_` in any lake table (D7 §P9) |
| Vendor of worldmonitor (Elie Habib) changes license retroactively | L | rework required | pin worldmonitor commit SHA we vendored from; document it in `_vendor_worldmonitor/README.md` (§5.3 step 5) |
| Live map renders blank because `lake.geo_events` is empty on fresh deploy | H | poor first impression | V2 ships with a "seed 50 historical events" migration triggered when `IIC_DEMO=on` (§6.demo-mode) |
| nginx config drifts again because no playwright smoke runs | M | recurrence of the §4 bug | the §6.V2 L1 test is *mandatory* on every dashboard PR |
| Operator forgets `IIC_DEMO=on` is the default and demos turn into production by drift | M | wrong defaults in real use | banners in 4 places (§6.demo-mode), agent startup log warning, README first-paragraph callout |
| Three.js bundle bloat persists after globe retirement because someone re-adds a 3D component | L | bigger bundle, slower load | new ESLint rule disallowing import of `three` / `react-globe.gl`; lint added in V2 along with the deletion |

---

## 8. Decisions log (resolved 2026-05-19)

The six questions originally posted here were resolved the same day. Listed below with original question + resolution so future readers see the trace.

1. **AGPL-3.0 vs. commercial** (§5.3)
   → **Resolved: vendor with full attribution.** IIC is personal-use only, no commercial plans. Vibe agent must add worldmonitor reference to the top-level README (§5.3 step 4) + LiveMap component README (§5.3 step 5). If commercial intent ever appears, re-open and rewrite the vendored subtree from scratch.
2. **Map landing route**
   → **Resolved: `/map`.** Single flat-map route.
3. **Severity scale**
   → **Resolved: `1..5` is correct.** No further verification needed against migration 0010 for this iteration; if the actual column differs, V2 will reveal it at L3 acceptance and we'll adjust the frontend type only.
4. **Demo mode bake-in**
   → **Resolved: OK, with explicit "demo mode is on" disclosure.** Defaults flip per §6.demo-mode; banner in dashboard + README + DEPLOYMENT.md + agent startup logs.
5. **WeChat for V3**
   → **Resolved: deferred.** V3 ends at `lake.advice` + JSON-brief endpoint. No notifier send. Revisit post-V6.
6. **Globe vs. flat**
   → **Resolved: flat only; retire `EventGlobe.tsx`.** V2 includes deletion of the globe component + 3D deps (§5.9, §6.V2 Prompt C).

---

## 9. References

- Bringup session: `2026-05-19_v2.6_bringup_session.md`
- D6: `D6_Architecture_Review_Prototype_to_Product.md`
- D7: `D7_IIC_Development_Plan_Prototype_to_Product.md`
- D7.1 (companion): `D7.1_IIC_Hotfix_Plan_v2.6.1.md`
- worldmonitor repo: <https://github.com/koala73/worldmonitor> (AGPL-3.0)
- worldmonitor docs: <https://docs.worldmonitor.app>
- deck.gl: <https://deck.gl/docs>
- MapLibre GL: <https://maplibre.org/maplibre-gl-js/docs/>
- Branch in scope: <https://github.com/VegarGG/Investment-Intelligence-Center/tree/feat/v2.6-d7-prototype-to-product>
