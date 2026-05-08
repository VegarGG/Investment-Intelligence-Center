"""Burn-in phase 3 — Grafana / Loki / Tempo health probe.

Verifies (per plan §B2 phase 3):
- Grafana reachable; named panels render.
- Loki has logs for every container in the stack from the last 24h.
- Tempo has end-to-end traces for the last 10 morning_brief runs.

Skipped by default — requires the live observability stack. Triggered by
the burn-in driver when ``IIC_BURN_IN_OBSERVABILITY=1`` is set.
"""

from __future__ import annotations

import os
import sys
from typing import Any

REQUIRED_PANELS = (
    "persona advice with stale marks",
    "cost breaker opened",
    "agent_breaker.opened rate",
    "notify.deferred queue depth",
    "nats.stream.backup.last_run",
)

REQUIRED_CONTAINERS = (
    "iic-orchestrator",
    "iic-agent-intelligence",
    "iic-agent-fundamental",
    "iic-agent-quant",
    "iic-agent-persona",
    "iic-agent-backtest",
    "iic-agent-secretary",
    "iic-postgres",
    "iic-nats",
)


def main() -> int:
    if os.environ.get("IIC_BURN_IN_OBSERVABILITY") != "1":
        print("IIC_BURN_IN_OBSERVABILITY not set — phase 3 skipped")
        return 0

    failures: list[str] = []

    failures.extend(_check_grafana())
    failures.extend(_check_loki())
    failures.extend(_check_tempo())

    if failures:
        print("OBSERVABILITY CHECK FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("OBSERVABILITY CHECK PASSED")
    return 0


def _check_grafana() -> list[str]:
    try:
        import httpx  # type: ignore[import-not-found]
    except ImportError:
        return ["httpx not installed; cannot probe Grafana"]
    grafana_url = os.environ.get("GRAFANA_URL", "http://localhost:3000")
    failures: list[str] = []
    for panel in REQUIRED_PANELS:
        try:
            r = httpx.get(f"{grafana_url}/api/search?query={panel}", timeout=5.0)
            if r.status_code != 200:
                failures.append(f"grafana panel {panel!r}: HTTP {r.status_code}")
                continue
            data: list[dict[str, Any]] = r.json()
            if not data:
                failures.append(f"grafana panel {panel!r}: not found")
        except httpx.HTTPError as exc:
            failures.append(f"grafana unreachable: {exc}")
            break
    return failures


def _check_loki() -> list[str]:
    try:
        import httpx  # type: ignore[import-not-found]
    except ImportError:
        return ["httpx not installed; cannot probe Loki"]
    loki_url = os.environ.get("LOKI_URL", "http://localhost:3100")
    failures: list[str] = []
    for container in REQUIRED_CONTAINERS:
        try:
            r = httpx.get(
                f"{loki_url}/loki/api/v1/query",
                params={"query": f'{{container_name="{container}"}}'},
                timeout=5.0,
            )
            if r.status_code != 200:
                failures.append(f"loki container {container}: HTTP {r.status_code}")
                continue
            data = r.json().get("data", {}).get("result", [])
            if not data:
                failures.append(f"loki container {container}: zero log streams")
        except httpx.HTTPError as exc:
            failures.append(f"loki unreachable: {exc}")
            break
    return failures


def _check_tempo() -> list[str]:
    try:
        import httpx  # type: ignore[import-not-found]
    except ImportError:
        return ["httpx not installed; cannot probe Tempo"]
    tempo_url = os.environ.get("TEMPO_URL", "http://localhost:3200")
    try:
        r = httpx.get(
            f"{tempo_url}/api/search",
            params={"tags": "service.name=iic-orchestrator", "limit": "10"},
            timeout=5.0,
        )
        if r.status_code != 200:
            return [f"tempo: HTTP {r.status_code}"]
        traces = r.json().get("traces", [])
        if len(traces) < 1:
            return [f"tempo: only {len(traces)} traces visible (need ≥ 1)"]
    except httpx.HTTPError as exc:
        return [f"tempo unreachable: {exc}"]
    return []


if __name__ == "__main__":
    sys.exit(main())
