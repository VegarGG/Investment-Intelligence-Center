# Runbook — FUTU OpenD offline

**Triggered by:** Alertmanager rule `FutuOpenDOffline` (`get_global_state` failing for > 5 min) or `lake.futu_audit` chain head static for > 15 min.

## 1. Detect
- Dashboard: Settings → Brokers — Verify button against each FutuID returns red.
- `lake.futu_audit` tip query:
  ```sql
  SELECT futu_id_hash, max(issued_at) FROM lake.futu_audit
  GROUP BY 1 ORDER BY 2 DESC LIMIT 5;
  ```

## 2. Mitigate
- Restart the OpenD container locally; confirm port (default 11111) responds to `nc -z`.
- If multi-account, only the affected `futu_id_hash` is impacted — the others keep auditing.
- Quotes degrade gracefully: `lake.quotes` falls back to ccxt/FRED via the `CompositeQuotesFacade` (P4.6).

## 3. Verify
- `/admin/brokers/<id>/verify` returns `{ok: true}`.
- Audit chain advances within one ping cycle.
- `lake.quotes WHERE src='futu' AND ts > now() - 5min` non-empty.
