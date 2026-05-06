# ADR-0003 — Host: single Linux mini-PC with NAS-ready storage layout

- **Status:** Accepted
- **Date:** 2026-05-06

## Context

ADR-0001 removed the GPU requirement. That makes the home box an orchestration host, not a model host — CPU, RAM, NVMe, and 24×7 reliability matter; a GPU does not. We considered:

1. **Cloud VM.** Recurring spend; data egress for backups; less control over physical security.
2. **Existing PC.** Free start. Not 24×7-rated; consumer power supply.
3. **Used business mini-PC** (HP EliteDesk / Dell OptiPlex / Lenovo ThinkCentre).
4. **New consumer mini-PC** (Beelink SER8 / Minisforum UM870).
5. **NAS as compute.** Convenient storage but weak CPUs and limited Docker support.

We also considered the storage shape: do we buy a NAS at launch, or wait?

## Decision

**Single Linux mini-PC at launch — Beelink SER8 (Ryzen 7 8845HS, 32 GB DDR5, 1 TB NVMe), $700.** Plus a $110 external 4 TB USB-C HDD and a $120 UPS. Ubuntu 24.04 LTS Server, native Docker, no VM tax. Total ≈ $930.

**No NAS at launch — but everything is NAS-ready.** Every persistent volume in `docker-compose.yml` is a bind mount under `/srv/iic/<service>` (workflow 01 §2.6). Switching to a NAS later is:

```
sudo systemctl stop iic.service
rsync -aHAX /srv/iic/ nas:/volume1/iic/
echo "nas:/volume1/iic /srv/iic nfs vers=4.1,_netdev,hard,timeo=600,retrans=2 0 0" >> /etc/fstab
sudo mount /srv/iic
sudo systemctl start iic.service
```

The compose file is **never touched.** A dry-run of `infra/nas/migrate.sh` runs on every CI commit so the migration story stays valid as the system grows.

## Consequences

- ✅ Lowest reasonable total cost of ownership at launch (≈$930 hardware vs ~$1,500 with a NAS).
- ✅ ~10 W idle, fits in a drawer, sub-second container startup off NVMe.
- ✅ NAS upgrade is one evening — and CI proves it stays one evening.
- ⚠️ Single-disk failure mode at launch. Mitigated: nightly restic to external HDD + offsite to Backblaze B2; cold restore < 60 min (success metric R6).
- ⚠️ Consumer NVMe wear. SMART monitoring + Grafana alert at 70% wear, replace at 80%.
- ⚠️ Non-ECC RAM. `memtester` 2 h at install + yearly during DR drill.

## Re-evaluation trigger

NAS upgrade fires when (a) NVMe is > 70% full, or (b) retention pressure on `lake.timeseries` / `objects` exceeds 5 yr at current rates, or (c) a second user joins the watchlist.
