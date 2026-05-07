# Runbook — WeCom callback failing

`last_verified: 2026-05-07`

## What it means

The Secretary's `/notifier/wecom/callback` is rejecting WeCom verification
or inbound messages. Slash commands and chat replies stop working; outbound
group-bot pushes (briefs, alerts, fills) are unaffected.

## Likely causes (most → least likely)

1. `WECOM_TOKEN` or `WECOM_AES_KEY` rotated in the WeCom admin UI but
   not in `.env.sops`.
2. The 可信域名 (trusted domain) re-verification fell out of sync.
3. Secretary container restart cleared the in-memory token cache and
   the new token fetch is failing.
4. Sender user-id not on `SECRETARY_ALLOWED_USERS`.

## First-look checks (≤ 2 min)

- `docker compose logs agent_secretary --tail 200 | grep wecom`
- WeCom admin → 应用管理 → IIC-Secretary → check 接收消息 status.
- `curl -fsS https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid=...&corpsecret=...`

## Resolution paths

- Path A — token mismatch: copy fresh `WECOM_TOKEN`/`WECOM_AES_KEY` from
  the WeCom admin, encrypt into `.env.sops`, restart Secretary.
- Path B — trusted-domain reverify: re-place `MP_verify_<random>.txt` on
  the Cloudflare Tunnel hostname, click 验证 in WeCom admin.
- Path C — whitelist drift: confirm sender id is in
  `SECRETARY_ALLOWED_USERS`; add if intended.

## Verification

- A `/help` slash command from the principal returns the help text.
- A whitelisted user receives an echo response within 2 s.

## Postmortem hook

Only if outbound briefs were also affected (rare — they don't share
callback infrastructure).
