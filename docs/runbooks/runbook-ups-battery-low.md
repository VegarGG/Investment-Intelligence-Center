# Runbook — UPS_BATTERY_LOW

`last_verified: 2026-05-07`

## What it means

UPS is on battery AND charge dropped below 50%. We have minutes, not hours.

## Likely causes (most → least likely)

1. House power outage.
2. Cleaner / pet unplugged the UPS by accident.
3. UPS battery aging out (replace every ~3 years).

## First-look checks (≤ 2 min)

- `apcaccess STATUS` (should be ONBATT vs ONLINE)
- `apcaccess BCHARGE TIMELEFT` (battery % and minutes remaining)
- Phone the household to confirm power is out.

## Resolution paths

- Path A — power outage: trigger graceful shutdown automatically when
  battery < 30% via `apcupsd` `BATTERYLEVEL` directive. The host's
  systemd `iic.service` will re-start when power returns.
- Path B — accidental unplug: re-seat the UPS plug; wait for ONLINE.
- Path C — failing battery: order replacement battery; the UPS unit is
  cheaper than a new IIC node.

## Verification

- `apcaccess STATUS` returns ONLINE.
- Battery charges back above 80% within 30 min.

## Postmortem hook

Required if the host shut down or a brief was missed.
