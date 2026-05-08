# FUTU read-only — security review (Phase B3.3b)

> **Status:** Draft, awaiting Ziwei sign-off before phase B3.3b ships.
> **Plan:** `plan/IIC_Development_Plan_v2.5_Combined.md` §T2.7.
> **Tracks:** B3.3a (mock OpenD, this iteration) → B3.3b (real OpenD, next iteration).

## 1. Threat model

The FUTU integration is the only IIC service that talks to a third-party with
potential to mutate state (place / modify / cancel orders, deposit / withdraw
funds). The dreadful failure mode is **placing an unauthorised order** on
Ziwei's real account. Every layer below either (a) eliminates the affordance
for that mode or (b) detects it after the fact.

In-scope threats:

| # | Threat | Defense |
|---|--------|---------|
| T1 | A future commit accidentally calls `place_order()` on the wrapper. | `FutuReadOnlyClient.__getattr__` raises `FutuReadOnlyError` for every name in `FORBIDDEN_METHODS`. Bandit/regex CI checks any `.place_order(` pattern outside `tests/`. |
| T2 | A new method is added to the SDK that ends up exposed by accident. | `ALLOWED_METHODS` is an explicit allow-list. Adding to it requires editing `readonly_client.py` AND this document. |
| T3 | Compromised dep imports `futu.OpenSecTradeContext.place_order` directly. | Outbound firewall rules (B3.3b): allow market endpoints only; deny trade endpoints at the container level. |
| T4 | An attacker calls `unlock_trade(password)` with a guessed/leaked password. | `unlock_trade` is in `FORBIDDEN_METHODS`. Without it, FUTU **physically** rejects every order placement at the gateway — this is the load-bearing safeguard. |
| T5 | Audit log is tampered with after the fact. | Every entry hash-chains to its predecessor; chain head is anchored to OpenTimestamps daily (C10). |
| T6 | Credentials leak from disk. | Stored under `/srv/iic/futu/<hash>/openD-config/credentials.yaml.sops` — sops + age. Plaintext is never written; the `.sops.age.pub` policy is enforced via `.sops.yaml`. |

Out of scope:

- Adversarial FUTU-side staff. Out of scope (we trust the broker).
- Memory-dump attacks against the running OpenD process. Out of scope on a single-host deployment.

## 2. Defense layers

```
┌─────────────────────────────────────────────────────────┐
│ 1. Wrapper class — refuses every non-allowlisted method │
│    (FutuReadOnlyClient.__getattr__, B3.3a)               │
├─────────────────────────────────────────────────────────┤
│ 2. CI static check — non-test code may not import any   │
│    forbidden method by name (test_readonly_enforcement)  │
├─────────────────────────────────────────────────────────┤
│ 3. unlock_trade is NEVER called                          │
│    Without it, FUTU rejects orders at the gateway        │
├─────────────────────────────────────────────────────────┤
│ 4. Outbound firewall (B3.3b)                             │
│    ALLOW: openapi.futu market endpoints                  │
│    DENY:  openapi.futu trade-route endpoints             │
├─────────────────────────────────────────────────────────┤
│ 5. Audit log                                             │
│    Every call hash-chained → OpenTimestamps daily        │
└─────────────────────────────────────────────────────────┘
```

## 3. Acceptance gates

### B3.3a (THIS iteration — shipped)

- [x] `FutuReadOnlyClient` rejects every name in `FORBIDDEN_METHODS`.
- [x] CI static check: non-test code references no forbidden method.
- [x] Audit chain verifies after a representative call sequence.
- [x] Aggregator produces a schema-valid `portfolio.snapshot.v1`.
- [x] `tools/futu/add_id.sh` provisions credentials via sops template
       (no plaintext touches disk).
- [x] `agent_futu.enabled` feature flag stays OFF by default; `_is_enabled()`
       gate on every public endpoint.

### B3.3b (NEXT iteration — gated by Ziwei sign-off)

- [ ] Real OpenD container per Futu ID, port 11111+, separate bind-mount per ID.
- [ ] `TrdEnv.SIMULATE` (paper account) ONLY for the first real-OpenD light-up.
- [ ] Outbound firewall rule (table below) verified on the host.
- [ ] Penetration test: attempt to call `place_order` via every plausible bypass:
  - Direct attribute access on the underlying SDK context.
  - Dynamic `getattr` against the wrapper.
  - Raw socket to the OpenD port.
  - Each path must fail (wrapper rejects, firewall blocks, or FUTU rejects
    because `unlock_trade` was never called).
- [ ] Daily OpenTimestamps anchor of the audit-chain head verified for 7 consecutive days.
- [ ] Ziwei reads + signs the bottom of this document.

### Outbound firewall rule table (B3.3b)

| Direction | Action | Endpoint | Note |
|-----------|--------|----------|------|
| outbound  | allow  | `openapi.futunn.com:443` (market) | quote / position queries |
| outbound  | deny   | `openapi.futunn.com:443` (trade) | order-route endpoint |
| outbound  | allow  | `openapi.futu.market:443` (market alt) | regional fallback |
| outbound  | deny   | any other futu host | catch-all |

## 4. Failure-mode runbook

If the audit chain fails verification (`/audit/head` returns
`chain_verified=false`):

1. **STOP**: bounce `agent_futu` to a known-good restic snapshot.
2. Inspect `lake.futu_audit` for the broken entry; compare against
   the OpenTimestamps anchor.
3. File a CRITICAL alert via the notifier (severity=CRITICAL → ntfy
   on Tailscale fallback per T1.4).

## 5. Sign-off

- [ ] Ziwei has read this document end-to-end.
- [ ] Ziwei agrees that `TrdEnv.SIMULATE` is the only acceptable env for
      first real-OpenD light-up.
- [ ] Ziwei agrees the firewall rule table above is the production posture.

Ziwei's date + initials: `__________`
