# Workflow 42 — FUTU Phase B Real OpenD (v2.5 N3.6)

**Owner:** agent_futu · **Plan ref:** `plan/D5_IIC_Prototype_Review_and_Next_Iteration.md` §N3.6 · **Sibling docs:** [41_FUTU_READONLY_INTEGRATION.md](41_FUTU_READONLY_INTEGRATION.md) · **Security review:** [`docs/security/FUTU_readonly_review.md`](../docs/security/FUTU_readonly_review.md)

> **Status:** scaffolding shipped; light-up gated on Ziwei sign-off of the
> security-review doc §5. The `agent_futu.enabled` feature flag stays
> OFF until sign-off.

## 1. Ground truth

The Phase B integration runs a **real** Futu OpenD container per
Futu ID against a **paper account** (`TrdEnv.SIMULATE`). Every layer of
the read-only safety story is exercised end-to-end:

```
Wrapper (FutuReadOnlyClient.__getattr__)
  → Static-import check (CI)
  → unlock_trade is NEVER called (FUTU rejects orders without it)
  → Outbound nftables firewall (deny trade endpoints, allow market)
  → Postgres-backed audit log (hash chain + UPDATE/DELETE revoked)
  → Daily OpenTimestamps anchor of the chain head
```

## 2. Module + infra layout

| Path | Role |
|------|------|
| `infra/linux/iic-opend@.service` | systemd template, one instance per Futu ID. |
| `infra/linux/scripts/iic-opend-start.sh` | Refuses any `OPEND_TRD_ENV != SIMULATE`. |
| `infra/linux/iptables/futu.rules` | nftables ruleset; allow market, deny trade. |
| `packages/data-lake/data_lake/migrations/versions/0005_futu_audit.py` | `lake.futu_audit` table + chain trigger + revoke. |
| `apps/agent_futu/futu/audit.py` | `InMemoryFutuAuditLog` + `PgFutuAuditLog` behind a Protocol. |
| `infra/linux/scripts/futu-audit-anchor.sh` | Daily OpenTimestamps anchor of chain head. |
| `infra/linux/scripts/iic-futu-audit-anchor.{service,timer}` | Cron @ 04:00 local. |
| `tests/penetration/test_futu_readonly_pentest.py` | Tries every plausible bypass. |
| `tests/chaos/test_futu_audit_anchor.py` | Synthetic-mode anchor script test. |
| `tests/chaos/test_audit_chain_otp_anchor.py` | 7-day OTS verification (live mode gated). |

## 3. Workflow steps (Phase B light-up)

1. **Pre-flight**: confirm `lake.futu_audit` migration applied (`alembic upgrade head`).
2. **Provision**: `tools/futu/add_id.sh <futu_id>` → sops-encrypted credentials
   land at `/srv/iic/futu/<hash>/openD-config/`.
3. **Start**: `systemctl start iic-opend@<hash>.service`. The wrapper script
   rejects start unless `OPEND_TRD_ENV=SIMULATE`.
4. **Firewall**: `nft -f infra/linux/iptables/futu.rules` then
   `nft list ruleset` to verify.
5. **Smoke test**: `IIC_RUN_FUTU_LIVE=1 pytest tests/penetration/`
   (every bypass attempt must fail).
6. **OTS anchor**: `systemctl start iic-futu-audit-anchor.service`
   then verify with `tests/chaos/test_audit_chain_otp_anchor.py`.
7. **Sign-off**: Ziwei initials + dates `docs/security/FUTU_readonly_review.md` §5.
8. **Flip**: set `agent_futu.enabled: true` in `flags.yaml`.
9. **Verify**: one full morning_brief run with FUTU portfolio context attached
   to every persona's `AdviceV1`.

## 4. Acceptance gates

- `tests/penetration/test_futu_readonly_pentest.py` (synthetic) — every bypass green.
- `tests/penetration/test_futu_readonly_pentest.py::test_real_opend_refuses_live_env` (live) — refuses `LIVE`.
- `tests/chaos/test_futu_audit_anchor.py` — synthetic anchor produces `.head` + `.head.ots`.
- `tests/chaos/test_audit_chain_otp_anchor.py` — 7-day live OTS verification.
- Security-review doc §5 has Ziwei's initials + date.

## 5. Failure-mode runbook

If the audit chain fails verification:

1. STOP: `systemctl stop iic-opend@*.service`.
2. Inspect `lake.futu_audit` for the broken entry; cross-check against
   the most recent OpenTimestamps anchor.
3. File a CRITICAL alert (severity=CRITICAL → ntfy on Tailscale).
4. Roll back `agent_futu.enabled` to false in `flags.yaml`.

## 6. Cross-references

- 41 — [FUTU read-only integration (Phase A / B3.3a)](41_FUTU_READONLY_INTEGRATION.md)
- 02 — Data Lake (advice ledger, hash-chain trigger pattern)
- ADR-0004 — Single-host acceptance (RPO/RTO budget)
