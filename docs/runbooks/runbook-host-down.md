# Runbook — HOST_DOWN

`last_verified: 2026-05-07`

## What it means

Prometheus has been unable to scrape `node_exporter` for >3 minutes. The
mini-PC is either off, has lost network, or the exporter binary crashed.

## Likely causes (most → least likely)

1. Power loss (UPS exhausted or unplugged).
2. Tailscale / LAN outage masking the host from Prometheus.
3. `prometheus-node-exporter` service crashed.
4. NVMe failure that took the host filesystem with it.

## First-look checks (≤ 2 min)

- From a phone on cellular: `tailscale ping iic-host`
- From a Tailscale device: `ssh iic-host uptime`
- `systemctl status prometheus-node-exporter`
- Grafana → IIC-002-Host: any temps still recording?

## Resolution paths

- Path A — power: confirm UPS state, plug back in, watch `apcaccess STATUS`
  return to ONLINE; the alert clears once node_exporter scrape succeeds.
- Path B — node_exporter crashed: `systemctl restart prometheus-node-exporter`,
  collect the previous unit log with `journalctl -u prometheus-node-exporter -n 200`.
- Path C — disk failed: escalate to the DR drill in
  `workflows/31_PRODUCTION_HARDENING.md` §5.

## Verification

- `curl http://iic-host:9100/metrics | head` returns 200.
- Alert resolves in Grafana within 5 min.

## Postmortem hook

If the host was down >15 min OR a brief was missed, open a postmortem.
