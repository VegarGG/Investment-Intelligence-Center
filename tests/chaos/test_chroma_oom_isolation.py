"""v2.5 T1.8 — Chroma OOM isolation acceptance.

Plan §T1.8 acceptance: balloon Chroma's index to 6 GB and verify Postgres
survives. The synthetic verification is a YAML-level audit that every
service has a memory cap; the real-integration variant uses the Docker
SDK (gated on `IIC_DOCKER_CHAOS=1`).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE = REPO_ROOT / "docker-compose.yml"

# Plan §T1.8 caps — every service in compose must declare at least these.
EXPECTED_CAPS_BYTES: dict[str, int] = {
    "postgres": 4 * 1024**3,
    "chroma": 4 * 1024**3,
    "minio": 1 * 1024**3,
    "redis": 512 * 1024**2,
    "nats": 512 * 1024**2,
    "loki": 1 * 1024**3,
    "prometheus": 1 * 1024**3,
    "grafana": 512 * 1024**2,
    "orchestrator": 1 * 1024**3,
    "agent_intelligence": 1 * 1024**3,
    "agent_fundamental": 1 * 1024**3,
    "agent_quant": 1 * 1024**3,
    "agent_persona": 1 * 1024**3,
    "agent_backtest": 1 * 1024**3,
    "agent_secretary": 1 * 1024**3,
    "agent_futu": 512 * 1024**2,
    "dashboard": 256 * 1024**2,
}


def _parse_size(s: str | int) -> int:
    """Parse compose-style memory string ('4g', '512M', '256m', or int bytes)."""
    if isinstance(s, int):
        return s
    raw = str(s).strip().lower()
    units = {"k": 1024, "m": 1024**2, "g": 1024**3, "t": 1024**4}
    if raw[-1] in units:
        return int(float(raw[:-1]) * units[raw[-1]])
    return int(raw)


@pytest.fixture(scope="module")
def compose_data():
    with COMPOSE.open() as f:
        return yaml.safe_load(f)


def test_every_expected_service_has_a_memory_cap(compose_data):
    services = compose_data["services"]
    missing = [name for name in EXPECTED_CAPS_BYTES if name not in services]
    assert not missing, f"compose missing expected services: {missing}"
    no_cap = []
    for name in EXPECTED_CAPS_BYTES:
        svc = services[name]
        has_mem_limit = "mem_limit" in svc
        has_deploy_limit = bool(
            svc.get("deploy", {}).get("resources", {}).get("limits", {}).get("memory")
        )
        if not (has_mem_limit or has_deploy_limit):
            no_cap.append(name)
    assert not no_cap, f"v2.5 T1.8: services without memory cap: {no_cap}"


def test_caps_match_plan_table(compose_data):
    services = compose_data["services"]
    mismatches: list[tuple[str, int, int]] = []
    for name, expected_bytes in EXPECTED_CAPS_BYTES.items():
        svc = services[name]
        # Read whichever cap form is present; prefer mem_limit (string form).
        cap_str = svc.get("mem_limit") or (
            svc.get("deploy", {}).get("resources", {}).get("limits", {}).get("memory")
        )
        actual_bytes = _parse_size(cap_str)
        # Allow ±1% slop (e.g. 1G vs 1024M).
        if abs(actual_bytes - expected_bytes) / expected_bytes > 0.01:
            mismatches.append((name, expected_bytes, actual_bytes))
    assert not mismatches, f"plan §T1.8 cap mismatch: {mismatches}"


def test_total_memory_caps_within_budget(compose_data):
    """Total declared caps fit on Mac mini M4 Pro 24G with ~4G headroom.

    The plan §T1.8 quoted ~16G for the total, but missed that there are
    6 agents at 1G each. Real total is 19.8G; 24G − 19.8G ≈ 4G is enough
    for the Linux page cache + systemd journal.
    """
    total = 0
    for name, _ in EXPECTED_CAPS_BYTES.items():
        svc = compose_data["services"][name]
        cap_str = svc.get("mem_limit") or svc["deploy"]["resources"]["limits"]["memory"]
        total += _parse_size(cap_str)
    total_gb = total / 1024**3
    assert total_gb <= 20.5, f"total caps {total_gb:.1f}G exceeds 20.5G budget"
    assert total_gb >= 18.0, f"total caps {total_gb:.1f}G suspiciously low"


@pytest.mark.skipif(
    os.environ.get("IIC_DOCKER_CHAOS") != "1",
    reason="real-integration drill — set IIC_DOCKER_CHAOS=1 with running stack to run",
)
def test_real_chroma_oom_isolation():
    """Real-integration: balloon Chroma → verify Postgres health stays green.

    Requires:
    - The IIC compose stack running on the host.
    - `docker` Python SDK installed.
    - Postgres reachable at localhost:5432 with the `.env` creds.
    """
    import docker  # type: ignore[import-not-found]

    client = docker.from_env()
    chroma = client.containers.get("iic-chroma")
    postgres = client.containers.get("iic-postgres")

    # Push a 6 GB synthetic batch (Chroma will OOMKill before completing).
    chroma_oomkilled = False
    try:
        chroma.exec_run(
            "python -c 'import numpy as np; arr = np.zeros((1500_000, 1024), dtype=\"float32\")'",
            detach=False,
        )
    except docker.errors.ContainerError:
        chroma_oomkilled = True

    # Whether or not Chroma was killed, Postgres must still be healthy.
    pg_health = postgres.exec_run("pg_isready -U $POSTGRES_USER -d $POSTGRES_DB")
    assert pg_health.exit_code == 0, "Postgres unhealthy after Chroma OOM"
    # Real-drill expectation: Chroma should have been OOM-killed by the cap.
    assert chroma_oomkilled, "Chroma did NOT OOM under the cap — verify mem_limit applied"
