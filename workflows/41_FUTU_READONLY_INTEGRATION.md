# Workflow 41 — FUTU read-only integration

> **Source plan:** [`plan/IIC_Development_Plan_v2.5_Combined.md`](../plan/IIC_Development_Plan_v2.5_Combined.md) §T2.7
> **Status:** Phase B3.3a (mock OpenD) shipped. Phase B3.3b (real OpenD + paper account + penetration test + security review sign-off) NEXT iteration.
> **Owner:** Ziwei
> **Dreadful-limitation status:** Yes. Read-only is the load-bearing safety. Mocks here are forbidden in production code paths.

---

## 1. Purpose

`agent_futu` is the only IIC service that talks to a third-party with potential to mutate state. It's read-only by construction; this doc lists every defense layer + the test that exercises it.

## 2. Phase B3.3a — what's shipped

```
apps/agent_futu/futu/__init__.py
apps/agent_futu/futu/readonly_client.py        # FutuReadOnlyClient + ALLOWED/FORBIDDEN sets
apps/agent_futu/futu/audit.py                  # FutuAuditLog + hash chain
apps/agent_futu/futu/aggregator.py             # aggregate_snapshot across N OpenDs
apps/agent_futu/futu/fake_opend.py             # deterministic test fixture
apps/agent_futu/futu/main.py                   # FastAPI service
apps/agent_futu/tests/test_readonly_enforcement.py  # 11 cases
apps/agent_futu/tests/test_audit_chain.py           # 8 cases
tools/futu/add_id.sh                            # provisions sops-encrypted credential template
docs/security/FUTU_readonly_review.md           # phase B3.3b security-review scaffold
```

### Defense layers (shipped in B3.3a)

| # | Defense | File | Test |
|---|---------|------|------|
| 1 | Wrapper class refuses non-allowlisted methods | `readonly_client.py:FutuReadOnlyClient.__getattr__` | `test_readonly_enforcement.py::test_calling_*_raises_FutuReadOnlyError` |
| 2 | CI static check: non-test code references no forbidden method | `tests/test_readonly_enforcement.py::test_no_non_test_code_imports_forbidden_methods` | covered |
| 3 | `unlock_trade` is in `FORBIDDEN_METHODS` | `readonly_client.py:FORBIDDEN_METHODS` | covered |
| 4 | Audit chain | `audit.py:FutuAuditLog` | `test_audit_chain.py::test_chain_links_correctly_across_n_calls` etc. |
| 5 | Audit on errors | `readonly_client.py:_wrapped` | `test_audit_chain.py::test_error_calls_recorded_with_status_error` |

### Endpoints (FastAPI)

- `GET /health` — liveness; `openD_count` + `audit_entries` + `audit_head` + flag state.
- `GET /portfolio/snapshot` — aggregated `portfolio.snapshot.v1`. 503 if `agent_futu.enabled` flag is off.
- `GET /audit/head` — chain head + `chain_verified` boolean.

### Feature flag

`agent_futu.enabled` (default OFF). Stays OFF until the B3.3b security review is signed.

### Schema: `portfolio.snapshot.v1`

```python
class PortfolioSnapshotV1(BaseModel):
    schema_version: Literal["portfolio.snapshot.v1"]
    snapshot_at: datetime
    accounts: list[AccountState]
    aggregate: AggregateState
```

Each `AccountState` carries `futu_id` (hashed, never raw), `account_id`, `market`, `base_currency`, `nav_base_ccy`, `cash_base_ccy`, `purchasing_power_base_ccy`, `positions`. The aggregate exposes total NAV, cash, and the largest single-position concentration (so `plan.v1` can refuse to recommend overweight names).

## 3. Phase B3.3b — what's NEXT iteration (not shipped)

- Real OpenD container per Futu ID; `TrdEnv.SIMULATE` (paper account) only.
- Real `FutuReadOnlyClient` against real OpenD.
- Container-level outbound firewall: allow market endpoints, deny trade endpoints.
- Penetration test exercising every plausible bypass: direct attribute access, dynamic `getattr`, raw socket.
- Daily OpenTimestamps anchor of audit-chain head verified for 7 consecutive days.
- Ziwei reads + signs `docs/security/FUTU_readonly_review.md`.

**No production deployment of FUTU integration — even read-only — until B3.3b ships.**

## 4. Provisioning a new Futu ID

```sh
./tools/futu/add_id.sh ZW-PRIMARY    # creates /srv/iic/futu/<hash>/, sops template
# Edit the template, sops-encrypt, rename. agent_futu picks it up on bounce.
```

## 5. Acceptance

### B3.3a (this iteration)

- [x] `pytest apps/agent_futu/tests/` exits 0 (19 cases).
- [x] Static check refuses any non-test reference to `place_order` / `unlock_trade` / etc.
- [x] Aggregator produces a schema-valid `portfolio.snapshot.v1` from 2 FakeOpenDs (5 positions × 2 = 10 positions).
- [x] Audit chain verifies after a representative call sequence.
- [x] `tools/futu/add_id.sh` creates the bind-mount + sops template (no plaintext).

### B3.3b (next iteration)

See `docs/security/FUTU_readonly_review.md` §3 acceptance gates.

## 6. Risks & gotchas

- **`__getattr__` trap.** The wrapper relies on `__getattr__` only firing when normal attribute lookup fails. `FutuReadOnlyClient` is a frozen dataclass with no `place_order` member, so the trap fires; future maintainers must NOT add a real attribute to the dataclass that shadows a forbidden name.
- **`_summarise` vs full SDK return values.** The audit log stores a compact summary, not the full SDK return shape, to avoid spamming the log + leaking position data to the journal. Forensics may require pairing audit entries with the live MinIO snapshot.
- **`agent_futu.enabled` MUST stay OFF until B3.3b** even if every other test is green. The phase B3.3a code path is not safe to point at a real account.

## 7. Cross-references

- ADR-0004 — single-host SPOF acceptance.
- Workflow 33 — T1 finish + synthetic burn-in.
- Workflow 40 — Trading Room overview.
- `docs/security/FUTU_readonly_review.md`.

## Changelog

- **v0.1** — Initial B3.3a (mock OpenD + read-only enforcement + audit chain). B3.3b TBD.
