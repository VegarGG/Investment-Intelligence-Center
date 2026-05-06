# Workflow 20 — Notifier (WeChat-First Push)

> **Depends On:** `01_INFRASTRUCTURE_AND_HOST.md`, `05_DATA_BUS_AND_SCHEMAS.md`, `15_AGENT_SECRETARY.md`.
> **Owns:** `packages/notifier/` — adapters for WeCom group bots, WeCom self-built app, Server酱, ntfy, SMTP. Priority/fallback chain.
> **Status:** Final.

---

## 1. Purpose

Single, prioritized push pipeline. WeChat-native by design — for the principal and family on phones — with deep fallbacks for resilience.

The Secretary publishes `secretary.notify.v1` to the bus; this package consumes it and decides which adapter(s) get it, with a fall-through chain on failure.

---

## 2. Ground Truth — Channels

📌 **Stable.** Order is the priority order.

| # | Channel | Direction | Use case | Cost | Failure → falls back to |
|---|---------|-----------|----------|------|-------------------------|
| 1 | **WeCom group bot** | outbound | morning brief, alerts, fills | free | Server酱 |
| 2 | **WeCom self-built app** | bidirectional | conversational chat with Secretary | free | web UI |
| 3 | **Server酱 Turbo** | outbound | personal-WeChat fallback when WeCom is unreachable | ¥18/yr (~$3) | ntfy |
| 4 | **ntfy** | outbound | tertiary push (self-hosted on the box) | free | SMTP |
| 5 | **SMTP email** | outbound | last resort + weekly digest | ~$0 | none |

📌 **Three group bots:** `briefs`, `alerts`, `fills`. Each has its own webhook key.

```
WECOM_BOT_BRIEFS_KEY=...
WECOM_BOT_ALERTS_KEY=...
WECOM_BOT_FILLS_KEY=...
```

📌 **WeCom self-built app:** `corp_id`, `agent_id`, `app_secret`, plus `WECOM_TOKEN` and `WECOM_AES_KEY` for callback signature.

---

## 3. Architecture

```
   apps/agent_secretary ──► secretary.notify.v1 ──► packages/notifier
                                                           │
                                                           ▼
                                                    severity router
                                                    (chooses channels)
                                                           │
                              ┌──────────┬───────┬─────────┬────────┐
                              ▼          ▼       ▼         ▼        ▼
                          WeCom bot   WeCom app  Server酱  ntfy   SMTP
                              │          │         │       │        │
                              └──── on success: stop. on failure: cascade ──►
```

---

## 4. Module Layout

```
packages/notifier/
├── pyproject.toml
├── notifier/
│   ├── __init__.py
│   ├── types.py              # Notification, Severity, ChannelHint
│   ├── router.py             # severity → channel set; fallback chain
│   ├── adapters/
│   │   ├── base.py           # Adapter ABC
│   │   ├── wecom_bot.py
│   │   ├── wecom_app.py      # outbound to a specific WeCom user
│   │   ├── serverchan.py
│   │   ├── ntfy.py
│   │   └── smtp.py
│   ├── markdown_normalizer.py # WeCom-compatible markdown cleanup
│   └── ratelimit.py
└── tests/
    ├── test_router_severity.py
    ├── test_fallback_cascade.py
    ├── test_wecom_bot_adapter.py
    └── test_markdown_normalizer.py
```

---

## 5. Public Surface

```python
# notifier/types.py
class Severity(StrEnum):
    INFO = "info"
    WARN = "warn"
    ALERT = "alert"
    CRITICAL = "critical"

class ChannelHint(StrEnum):
    BRIEFS = "briefs"
    ALERTS = "alerts"
    FILLS = "fills"
    CHAT  = "chat"

class Notification(BaseModel):
    severity: Severity
    channel_hint: ChannelHint
    language: Literal["en", "zh"] = "en"
    markdown: str
    mentioned_list: list[str] | None = None
    target_user: str | None = None        # for wecom_app

# notifier/router.py
async def notify(n: Notification) -> NotifyResult: ...
```

`NotifyResult` records which adapters were tried, which succeeded, latency, errors.

---

## 6. Routing Rules

📌 **Severity → channel mapping:**

| Severity | Primary | Fallbacks |
|----------|---------|-----------|
| `info` (default briefs) | WeCom bot (channel from hint) | Server酱 → ntfy → SMTP |
| `warn` | WeCom bot `alerts` | Server酱 → ntfy → SMTP |
| `alert` | WeCom bot `alerts` + Server酱 | ntfy → SMTP |
| `critical` | WeCom bot `alerts` + Server酱 + ntfy + SMTP (all in parallel) | n/a |

`channel_hint` selects which group bot for non-critical severities.

`chat` hint goes to WeCom self-built app, addressed to `target_user`. Web UI also receives it via SSE.

---

## 7. Adapter Specifications

### 7.1 WeCom group bot

```python
# notifier/adapters/wecom_bot.py
async def send(channel: Literal["briefs","alerts","fills"],
               markdown: str,
               mentioned_list: list[str] | None = None) -> None:
    key = os.environ[f"WECOM_BOT_{channel.upper()}_KEY"]
    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={key}"
    payload = {
        "msgtype": "markdown",
        "markdown": {"content": markdown_normalizer.clean(markdown)},
    }
    if mentioned_list:
        payload["mentioned_list"] = mentioned_list
    # POST with retry on 5xx, sleep on 429 until window resets
    # WeCom limit: 20 msgs/min/bot
```

### 7.2 WeCom self-built app (outbound)

Different from the group bot. Requires OAuth-style token from `corp_id` + `agent_id` + `app_secret`. Posts to `https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token=...` with `touser`. Used when the Secretary needs to reply to a specific user's question.

### 7.3 Server酱 Turbo

```python
url = f"https://sctapi.ftqq.com/{SERVERCHAN_SENDKEY}.send"
data = {"title": title, "desp": markdown_body}
# POST application/x-www-form-urlencoded
```

Cost ¥18/yr (Turbo plan). Markdown body limit ~32 KB.

### 7.4 ntfy

Self-hosted via Docker on the same box (lightweight). Endpoint: `http://ntfy:80/iic-<channel>`. Requires no auth on the LAN; expose via Tailscale only.

### 7.5 SMTP email

Use a transactional provider (Postmark, Mailgun, or Gmail SMTP with App Password). Subject mirrors `severity` and `channel_hint`. HTML body is the markdown rendered to HTML.

---

## 8. Markdown Normalizer

WeCom's markdown is opinionated. The normalizer:

1. Strips HTML.
2. Demotes headings deeper than `h2` (WeCom renders only `#` / `##`).
3. Limits list nesting to 2 levels.
4. Replaces `> ` block quotes with bold prefix lines (WeCom doesn't render `> `).
5. Truncates to 4096 characters with a CJK-aware splitter and appends `更多见仪表板 → <link>` / `more on dashboard → <link>` based on language.
6. Keeps inline `code spans` and fenced ``` blocks (these render).
7. Replaces emojis that don't render reliably with text equivalents.

---

## 9. Fallback Cascade

`router.notify(n)` runs the channels in priority order:

```python
async def notify(n):
    primary, fallbacks = severity_to_channels(n)
    for adapter in [primary, *fallbacks]:
        try:
            await rate_limiter.acquire(adapter.name)
            await adapter.send(n)
            return NotifyResult(...success...)
        except (AdapterDown, AdapterRateLimit) as exc:
            log.warning(...)
            continue
    raise NotifyExhausted(n)
```

For `severity=critical`, run all adapters in parallel; record per-adapter success.

---

## 10. WeCom Setup (one-time, runbook)

📌 **Steps** (also in `docs/runbooks/wecom_setup.md`):

1. Sign up for free 企业微信 (WeCom). A single-person corp is fine.
2. In Corporation Admin → 应用管理:
   - Create three group bots: briefs, alerts, fills. Copy webhook URLs.
   - Create a self-built app **IIC-Secretary**. Record `corp_id`, `agent_id`, `app_secret`.
3. Set the self-built app's "可信域名" to the Tailscale or Cloudflare-Tunnel hostname of the mini PC.
4. Implement `/notifier/wecom/callback` (signature-verified) — handled by `15_AGENT_SECRETARY.md` §5.5.
5. Add the env vars to `.env`:

```
WECOM_BOT_BRIEFS_KEY=...
WECOM_BOT_ALERTS_KEY=...
WECOM_BOT_FILLS_KEY=...
WECOM_CORP_ID=...
WECOM_AGENT_ID=...
WECOM_APP_SECRET=...
WECOM_TOKEN=...
WECOM_AES_KEY=...
SERVERCHAN_SENDKEY=...
NTFY_BASE_URL=http://ntfy:80
NTFY_TOPIC_PREFIX=iic
SMTP_HOST=smtp.fastmail.com
SMTP_PORT=587
SMTP_USER=...
SMTP_PASSWORD=...
SMTP_FROM=iic@watter008.com
SMTP_TO=watter008@gmail.com
```

---

## 11. Workflow Steps

### Step 11.1 — Build adapters

Each adapter is small (≤ 150 lines). All implement the `Adapter` protocol from `notifier/adapters/base.py`.

### Step 11.2 — Build the router and rate limiter

Per-channel rate limits stored in Redis. WeCom bot: 20/min/bot. Server酱: 5 msgs/min. ntfy: unlimited (LAN). SMTP: 50/hour to avoid spam reputation hit.

### Step 11.3 — Wire the bus subscription

A small `notifier_listener.py` runs as part of `apps/agent_secretary` (not a separate container — keep coupled with Secretary, since the Secretary owns the message content). Subscribes to `secretary.notify.v1` and calls `notifier.notify(n)`.

### Step 11.4 — Tests

- Mock each adapter's HTTP target.
- Test severity routing (info → 1 channel, critical → 4 channels in parallel).
- Test fallback cascade (force WeCom 500; expect Server酱 to succeed).
- Test markdown normalizer with sample inputs.
- Test rate limiter: 25 messages to briefs in 60 s → only 20 sent + 5 deferred.

---

## 12. Vibe Prompts (paste-ready)

🧪 **Notifier package:**
> Implement `packages/notifier/` per `20_NOTIFIER_WECHAT.md`. Adapters for WeCom group bot, WeCom self-built app, Server酱 Turbo, ntfy, SMTP. Router maps severity → channel set per §6 and applies the fallback cascade per §9. Markdown normalizer per §8 — CJK-aware character truncation, WeCom-compatible. Tests use httpx-mock to simulate provider responses including 5xx and 429.

🧪 **WeCom bot adapter:**
> Implement `notifier/adapters/wecom_bot.py:send(channel, markdown, mentioned_list=None)`. POST to the webhook URL with `{"msgtype":"markdown","markdown":{"content":...},"mentioned_list":...}`. Retry with exponential back-off on 5xx; on 429 sleep until rate-limit window resets (WeCom is 20 msgs/min/bot). On hard failure, raise `AdapterDown` so the router can cascade.

🧪 **Markdown normalizer:**
> Implement `notifier/markdown_normalizer.py:clean(text, language="en", max_chars=4096) -> str`. Strip HTML; demote H3+ to bold lines; limit list nesting to 2; replace `> ` with bold prefix; CJK-aware truncate with language-correct "more on dashboard" suffix. Tests cover: a 5000-char zh input produces ≤ 4096 chars correctly truncated at a character boundary; H4 demotes to bold; nested-3-deep list collapses.

---

## 13. Acceptance Criteria

- [ ] `pytest packages/notifier -q` is green.
- [ ] Sending a `severity=info` notification reaches WeCom briefs bot and stops there (no Server酱 hit).
- [ ] Forcing WeCom to 503 routes the same notification through Server酱 successfully.
- [ ] Sending a `severity=critical` notification fires all four adapters in parallel; ≥ 1 succeeds.
- [ ] WeCom bot rate limiter throttles correctly: posting 25 messages in 60 s sends 20, defers 5, succeeds eventually.
- [ ] WeCom self-built app callback signature verification rejects a tampered payload (covered also in `15_AGENT_SECRETARY.md`).
- [ ] Markdown normalizer truncation never splits a CJK character mid-codepoint.
- [ ] One end-to-end production test: `secretary.notify.v1` → real WeCom briefs bot → message visible in WeChat.

---

## 14. Risks & Gotchas

⚠️ **WeCom corp_id and verification.** WeCom requires the "可信域名" (trusted domain) to verify a callback. Tailscale Funnel / Cloudflare Tunnel both work, but the domain must serve a static `MP_verify_<random>.txt` from the Secretary's HTTP server. Document in the runbook.

⚠️ **Server酱 latency.** Server酱's WeChat 服务号 push can lag 30–60 s during peak periods. Don't rely on it for time-sensitive alerts; that's why WeCom bot is primary.

⚠️ **ntfy on iOS.** ntfy on iOS requires a paid (or self-paid) APNs path. Fine for the principal who has the iOS app; family members may not bother. Consider it a backup, not a primary push.

⚠️ **SMTP spam reputation.** Sending from `iic@watter008.com` requires SPF + DKIM. Use a transactional provider where possible.

⚠️ **Markdown rendering surprises.** WeCom drops `__bold__` (single underscore syntax). Use `**bold**`. Normalizer enforces.

⚠️ **Critical-fanout cost.** Critical severity hits all 4 channels — only use for actual critical alerts (chain integrity, cost breaker, host down). Don't promote routine errors to critical.

⚠️ **Channel hint vs severity precedence.** If `channel_hint=fills` and `severity=warn`, send to fills bot (hint wins for non-critical). For `severity=critical`, hint is ignored — all channels.

⚠️ **Encoding inconsistencies.** Server酱 expects UTF-8 in form-encoded body; ensure `requests`/`httpx` content-type header is correct. Test with a zh body that includes emojis.

---

## 15. Cross-References

- Secretary publishes `secretary.notify.v1`: `15_AGENT_SECRETARY.md` §5.
- WeCom callback (inbound) handled by Secretary: `15_AGENT_SECRETARY.md` §5.5.
- Trusted domain via Cloudflare Tunnel: `01_INFRASTRUCTURE_AND_HOST.md` §5.8.
- Disclaimer footer convention: `10_AGENT_INTELLIGENCE.md` §5.9.

---

## Changelog

- **v1.0** — Extracted from `PLAN_v2.1` §12. Severity routing table promoted to GROUND TRUTH; markdown normalizer rules made explicit; CJK-aware truncation specified.
