# Workflow 15 — Secretary Agent

> **Depends On:** `03_LLM_CLIENT.md`, `04_PROMPT_REGISTRY.md`, `05_DATA_BUS_AND_SCHEMAS.md`, `10_AGENT_INTELLIGENCE.md`, `14_AGENT_BACKTEST.md`, `20_NOTIFIER_WECHAT.md`.
> **Owns:** `apps/agent_secretary/` — the chief-of-staff. Outbound briefs + alerts; inbound chat (web + WeChat); explain-mode with multi-agent disagreement surfacing; family-friendly tone.
> **Status:** Final.

---

## 1. Purpose

Be the human-facing layer. Two faces:

1. **Outbound (push).** Compose the morning brief, mid-day check, evening recap, and significant-fill alerts. Push primarily through WeCom; fall back through Server酱 → ntfy → email.
2. **Inbound (chat).** Take user questions in WeChat or the dashboard. Plan the answer, gather data from agents/lake, present results — including disagreements between agents as first-class content.

The Secretary is the only agent whose outputs a non-technical family member should ever see directly.

---

## 2. Ground Truth

### 2.1 Outbound schedule

| Brief | Time (PT) | Tier | Channel |
|-------|-----------|------|---------|
| Morning brief | 06:30 | Pro | WeCom briefs bot |
| Mid-day check | 12:00 | Flash | WeCom briefs bot |
| Evening recap | 16:30 | Flash | WeCom briefs bot |
| Significant fill | event-driven | Flash | WeCom alerts bot |
| Weekly leaderboard | Sunday 19:00 | Flash | WeCom briefs bot |
| `ops.alert.v1 severity=critical` | event-driven | none (templated) | WeCom alerts bot + Server酱 |

### 2.2 Tone modes

- `terse` — for the principal in trading hours. Numbers-first, no analogies.
- `conversational` — default. Plain language, light explanations.
- `educational` — for family. Analogies, no acronyms, ticker → company name.

Tone is set per recipient via a slider in the dashboard and per-message override via WeCom slash command (`/tone family`).

### 2.3 Languages

`zh` and `en`, auto-detected from the inbound message's character set / language detection. Outbound briefs default to Ziwei's preference (set via env `SECRETARY_DEFAULT_LANG=en`).

### 2.4 Inbound channels

- **WeCom self-built app** (primary). Inbound messages hit `/notifier/wecom/callback` (signature-verified) → routed to `secretary.chat`.
- **Web UI** (secondary). `/chat` SSE-streamed endpoint for deep dives at the laptop.

### 2.5 Slash commands (WeCom inbound)

```
/leaderboard               → publishes the latest leaderboard as a markdown table
/explain <advice_id>       → "explain mode" deep dive on one advice
/why <ticker>              → all currently-open advices for ticker, with thesis snippets
/disagree <ticker>         → render the agent-disagreement table
/quiet <minutes>           → mute outbound non-critical pushes for N minutes
/tone <terse|conv|edu>     → set the conversation's tone
/help                      → list commands
```

### 2.6 Authorization

Only whitelisted WeCom user-ids may issue slash commands. Whitelist in `.env` as `SECRETARY_ALLOWED_USERS=ziwei,family_member_1,...`.

---

## 3. Architecture

```
                     Outbound triggers (cron + events)
                                  │
                                  ▼
                       Secretary brief composer
                                  │
                                  ▼
                       packages/notifier (WeCom → fallback chain)
                                  │
                                  ▼
                          User's WeChat / email

                            Inbound message
                  (WeCom callback / dashboard SSE)
                                  │
                                  ▼
                    secretary.chat (Flash default)
                                  │
                ┌─────────────────┼─────────────────┐
                ▼                 ▼                 ▼
           lake reads     agent HTTP queries   prompt registry
                                  │
                                  ▼
                            response stream
                                  │
                                  ▼
                          User's WeChat / web UI
```

---

## 4. Module Layout

```
apps/agent_secretary/
├── pyproject.toml
├── Dockerfile
├── secretary/
│   ├── __init__.py
│   ├── main.py                       # FastAPI app
│   ├── outbound/
│   │   ├── morning_brief.py          # Pro
│   │   ├── midday_check.py           # Flash
│   │   ├── evening_recap.py          # Flash
│   │   ├── significant_fill.py       # event-driven
│   │   ├── weekly_leaderboard.py
│   │   ├── ops_critical_alert.py     # templated
│   │   └── compose_helpers.py
│   ├── inbound/
│   │   ├── chat.py                   # SSE handler
│   │   ├── wecom_callback.py         # signature-verified inbound
│   │   ├── slash_commands.py
│   │   ├── intent_router.py          # picks the right plan
│   │   └── deep_explain.py           # multi-agent fan-out
│   ├── tone.py
│   ├── language.py                   # zh/en detection
│   ├── auth.py                       # WeCom user whitelist
│   └── publish.py                    # secretary.notify.v1 → notifier
└── tests/
    ├── test_morning_brief.py
    ├── test_slash_commands.py
    ├── test_disagreement_table.py
    └── test_wecom_signature.py
```

---

## 5. Workflow Steps

### Step 5.1 — Compose the morning brief (Pro)

Triggered by orchestrator DAG A. Inputs:
- `intel.brief.v1` (from Intelligence) — already a 200–400 word draft.
- The day's `advice.*.v1` events ranked by confidence × novelty.
- Previous evening's leaderboard delta.

Steps:
1. Load tone from KV (`secretary.tone.<recipient>`).
2. Load language preference.
3. Render the prompt `secretary.brief.morning` from the registry with the inputs.
4. Pro call. Output is WeCom-markdown.
5. Validate ≤ 4096 chars (truncate with "more on dashboard →" link).
6. Validate footer disclaimer present.
7. Publish `secretary.notify.v1 channel_hint="briefs"` → notifier sends to WeCom briefs bot.

### Step 5.2 — Significant fill alert

Event-driven on `backtest.fill.v1` with `pnl_r >= 1.5` OR `exit_reason="stop" AND |pnl_r| >= 0.8`. Templated, fast (Flash narrative call), pushed to WeCom alerts bot. Includes a one-line "what to learn" remark.

### Step 5.3 — Inbound chat handler

`inbound/chat.py` accepts SSE-streamed messages.

```python
async def handle(message: ChatRequest) -> AsyncIterator[Token]:
    intent = await intent_router.classify(message.text)
    plan   = intent_to_plan(intent)
    async for token in plan.stream(message):
        yield token
```

`intent_router` is a Flash classifier with a small set of intents:

| Intent | Plan |
|--------|------|
| `slash_command` | dispatch via `slash_commands.py` |
| `single_ticker_query` | gather all open advices for the ticker; render as table |
| `agent_question` | route to a specific agent's HTTP `/explain` endpoint |
| `macro_question` | summarize latest digest `macro_thesis` |
| `meta_system` | uptime / cost / health snapshot |
| `chitchat` | brief polite response |

### Step 5.4 — Deep explain mode

Trigger: user says "explain deeply" OR types `/explain <advice_id>` OR asks a multi-step question.

Plan:
1. Retrieve the advice from `lake.advice`.
2. Pull its evidence references (digest events, filings, factor matrix rows).
3. Pull contemporaneous advices from other agents on the same ticker.
4. Compose a Pro response with a "step-by-step trace": *Retrieve → Reason → Answer*, citations inline.
5. If multiple agents disagree on the same ticker, render the disagreement as a table — NOT a single answer.

🧪 **VIBE-PROMPT — secretary deep explain (also seeded into prompt registry):**
> *System:* Translate the user question into an internal plan: which agent or which data table answers it? Produce a step-by-step trace `→ retrieve → reason → answer` with citations. If multiple agents disagree, present the disagreement as a table, not a single answer.

### Step 5.5 — WeCom callback

`wecom_callback.py` implements WeCom's official inbound message protocol:

1. Verify URL signature on first GET (echo `echostr`).
2. On POST: verify signature using `WECOM_TOKEN` and `WECOM_AES_KEY`; decrypt; parse XML.
3. Authorize sender against `SECRETARY_ALLOWED_USERS`.
4. Dispatch to `chat.handle` (or `slash_commands.dispatch` if message starts with `/`).
5. Reply via WeCom outbound message API (different endpoint from group bots).

### Step 5.6 — Tone and language

`tone.py` maps the active tone to a prompt suffix. `language.py` runs a small `langdetect`-based check on the inbound text and picks the response language. Stored per-conversation in Redis (`session:<user_id>` with 30-min TTL).

### Step 5.7 — Cost-breaker awareness

When `iic_state.cost_breaker_state == "OPEN"`:
- Outbound briefs: skip Pro composition; emit a templated message: *"系统已暂停 LLM 推理（成本上限）。本日简报省略 / LLM paused at monthly cap; brief omitted today."*
- Inbound chat: respond Flash-only. Slash commands still work.

---

## 6. HTTP API

```
POST /chat                    → SSE stream for the dashboard chatbot
POST /notifier/wecom/callback → WeCom inbound (signature-verified)
POST /run/morning_brief       → manual kick (admin)
POST /run/midday_check
POST /run/evening_recap
GET  /leaderboard             → markdown table for embedding
GET  /health
```

---

## 7. Vibe Prompts (paste-ready)

🧪 **Scaffold the Secretary:**
> Implement `apps/agent_secretary/` per `15_AGENT_SECRETARY.md`. FastAPI + SSE for `/chat`. Subscribe to `intel.brief.v1`, `advice.*.v1`, `backtest.fill.v1`, `backtest.leaderboard.v1`, `ops.alert.v1`. Outbound briefs use Pro for morning and Flash for the rest. Tone modes per §2.2. Slash commands per §2.5. WeCom callback signature-verified per WeCom official spec (use `wechatpy` if it speaks WeCom; otherwise hand-roll). Tests: morning brief composes correctly under each tone × language combo with mocked LLM; significant-fill alert fires on a synthetic fill with `pnl_r=1.6`; signature verification rejects a tampered message.

🧪 **Disagreement table renderer:**
> Implement `secretary/inbound/deep_explain.py` to detect when multiple agents have produced conflicting `advice.v1` for the same `asset.ticker` within a 7-day window (e.g., quant LONG vs persona.burry SHORT). Render a markdown table with columns: agent, direction, entry_band, target_band, confidence, key_thesis_phrase. End with one sentence stating which agent has the better recent leaderboard score on this asset class.

🧪 **WeCom callback:**
> Implement `secretary/inbound/wecom_callback.py` per §5.5. URL verification handler answers GET with echostr decrypted. POST handler verifies signature using `WECOM_TOKEN` and decrypts using `WECOM_AES_KEY`. Reject any message from a sender not in `SECRETARY_ALLOWED_USERS`. Tests use a captured XML fixture from WeCom's docs and assert end-to-end decrypt + dispatch.

🧪 **Cost-breaker fallback brief:**
> Add a templated "system paused" brief in §5.7. No LLM call. Bilingual (zh + en in the same message body). Include a link to the dashboard's cost panel.

---

## 8. Acceptance Criteria

- [ ] `pytest apps/agent_secretary -q` is green.
- [ ] Morning brief delivered to WeCom briefs bot ≥ 95% of trading days within 5 minutes of 06:30 PT (measured over 30 days).
- [ ] Inbound `/leaderboard` from a whitelisted WeCom user returns the latest leaderboard within 5 s.
- [ ] Inbound from a non-whitelisted user is silently dropped (no DOS-amplification reply).
- [ ] Family-mode brief in zh: a non-technical reader can understand it (qualitative; verified once with a real family member).
- [ ] When `cost_breaker_state` is forced OPEN, the morning trigger emits the templated message instead of calling Pro.
- [ ] Disagreement table renders for INTC when quant says LONG and persona.burry says SHORT (synthetic fixture).
- [ ] Tone slider in the dashboard persists per-recipient and survives a Secretary restart.

---

## 9. Risks & Gotchas

⚠️ **WeCom signature gotcha.** Empty echostr on first verify if you re-deploy the corp_id. Document recovery: re-issue token in the WeCom admin, then re-verify.

⚠️ **Markdown rendering quirks.** WeCom drops some markdown features (no nested lists deeper than 2 levels, no inline images in `markdown` msgtype — use `news` msgtype for cards). The brief composer normalizes through a renderer that knows WeCom's quirks.

⚠️ **CJK char counting.** `len("你好")` returns 2 in Python — but WeCom counts characters, not bytes. We're fine. Test with a 4096-char zh brief that hits the boundary.

⚠️ **Inbound rate limiting.** A user spamming `/leaderboard` 100x in a row would saturate Flash. Per-user rate-limit: max 30 messages/min, 200/hour. Slash commands count.

⚠️ **Multilingual code-mixing.** Users send "今天 INTC 怎么样?" — half zh half en. Set Pro temperature low when responding to mixed-language queries; the model can over-translate ticker symbols ("Intel 公司") which is awkward.

⚠️ **Trace IDs leaking into chat.** Don't print `trace_id` in user-facing outputs. Logs are fine.

⚠️ **Authorization drift.** When a family member is removed, also revoke the WeCom user's app membership in WeCom admin — env var alone won't stop them from sending if WeCom still routes them in.

⚠️ **Significant-fill spam.** A volatile day could fire 50+ "significant" fills. Throttle to max 5 per hour to the alerts bot; aggregate the rest into the next scheduled brief.

---

## 10. Cross-References

- Notifier fanout: `20_NOTIFIER_WECHAT.md`.
- Brief composition source materials: `10_AGENT_INTELLIGENCE.md` §5.9 (intel.brief.v1) and `14_AGENT_BACKTEST.md` (leaderboard).
- Disagreement detection input: `lake.advice` queries.
- Tone storage in KV: `05_DATA_BUS_AND_SCHEMAS.md` §2 (`iic_state` bucket).
- Cost breaker source: `03_LLM_CLIENT.md` §7.

---

## Changelog

- **v1.0** — Extracted from `PLAN_v2.1` §4.6 + §12. Slash command catalog formalized; cost-breaker fallback message added; per-user rate limit specified.
