# Feature flags

> Workflow 32 / v2.5 T0.1. Every IIC v2.5 item ships behind a flag. Rollback = flag flip, not redeploy.

## How they work

- YAML-backed at `/srv/iic/featureflags/flags.yaml` (overridable via `IIC_FEATUREFLAGS_PATH`).
- Mtime-cached on read; flag flip propagates within ≤ 2 s of file write.
- A flag must be `register()`'d before `flag()` will return True. Unregistered names always resolve False (typo guard).
- Test overrides use `featureflags.set_for_test(name, value)` and `reset_for_test()`.

## Sample `flags.yaml`

```yaml
persona.live_mark.enabled: true
notifier.durable_redelivery.enabled: false
orchestrator.agent_breaker.enabled: true
orchestrator.use_nats_for_agent_calls: false
trading_room.event_triage.enabled: false
trading_room.investment_board.enabled: false
agent_futu.enabled: false
```

## Registry

Edit `packages/featureflags/featureflags/registry.py` to add a flag. Keep the description, `added_in`, and `owner` fields populated — the `/featureflags` admin route + Grafana panel surface them.

| Flag | Default | Added | Owner | Purpose |
|---|---|---|---|---|
| `iic.featureflags.bootstrap` | false | v2.5-T0.1 | platform | Acceptance gate flag for T0.1 chaos test. |
| `persona.live_mark.enabled` | true | v2.5-T1.1 | persona | Use `data_lake.quotes.get_mark` instead of the `100.0` placeholder. |
| `notifier.durable_redelivery.enabled` | false | v2.5-T1.4 | notifier | Redis retry queue with severity-TTL on `NotifyExhausted`. |
| `orchestrator.agent_breaker.enabled` | true | v2.5-T1.6 | orchestrator | Per-agent breaker; opens after 5 failures, half-open every 60 s. |
| `orchestrator.use_nats_for_agent_calls` | false | v2.5-T2.0 | orchestrator | NATS request-reply fan-out instead of HTTP. |
| `trading_room.event_triage.enabled` | false | v2.5-T2.1 | trading_room | Promote `intel.event.candidate.v1` → `high_impact.v1`. |
| `trading_room.investment_board.enabled` | false | v2.5-T2.4 | board | Bull/Bear → 3-way Risk → Chair sub-system. |
| `agent_futu.enabled` | false | v2.5-T2.7 | agent_futu | Read-only OpenD across N Futu IDs. |

## Adding a flag

1. `register(name, description, added_in, default, owner)` in `registry.py`.
2. Add a row to the table above (or run `tools/featureflags/sync_doc.sh` if it exists).
3. Reference the flag from the call site with `flag("...")`.
4. Default OFF for new behaviour; flip ON in YAML once the chaos test green-lights it.

## Observability

Flag flips emit `featureflag.changed{name=...}` to Prometheus (panel: `iic-007 — Feature flags`). Grafana shows current value + last-flipped timestamp per flag.
