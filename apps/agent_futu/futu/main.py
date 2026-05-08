"""FastAPI service for agent_futu (v2.5 T2.7 / B3.3a).

Read-only multi-account FUTU integration. **Phase 1 (this iteration)**
runs against `FakeOpenD` so the service shape, audit chain, and aggregator
are all testable without a live OpenD container. **Phase 2 (next
iteration)** wires real OpenD per Futu ID with firewall-enforced read-only
posture.

Endpoints:
- ``GET /health``                 — liveness; reports OpenD count.
- ``GET /portfolio/snapshot``     — current aggregate snapshot.
- ``GET /audit/head``             — current audit chain head + verification.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import FastAPI, HTTPException

from .aggregator import aggregate_snapshot
from .audit import FutuAuditLog
from .fake_opend import make_fake_openD_pair
from .readonly_client import FutuReadOnlyClient

log = logging.getLogger(__name__)
SERVICE = "agent_futu"
PORT = int(os.environ.get("PORT", "8087"))

app = FastAPI(title=f"iic.{SERVICE}", version="0.1.0")

_state: dict[str, Any] = {
    "clients": [],
    "audit": FutuAuditLog(),
}


def _is_enabled() -> bool:
    """Feature-flag gate. agent_futu is OFF by default until B3.3b ships."""
    try:
        import featureflags
        import featureflags.registry  # noqa: F401
    except ImportError:
        return False
    return featureflags.flag("agent_futu.enabled")


@app.on_event("startup")
async def _startup() -> None:
    """Wire FakeOpenD for B3.3a; B3.3b will replace with real OpenD."""
    if os.environ.get("FUTU_AUTOSTART") != "1":
        return

    audit = _state["audit"]
    clients: list[FutuReadOnlyClient] = []

    # Phase 1: deterministic fakes. Production lighting up real OpenD is
    # gated on the B3.3b security review.
    fake_a, fake_b = make_fake_openD_pair()
    clients.append(FutuReadOnlyClient(openD=fake_a, futu_id_hash="fid_primary", audit=audit))
    clients.append(FutuReadOnlyClient(openD=fake_b, futu_id_hash="fid_family", audit=audit))

    _state["clients"] = clients


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": SERVICE,
        "openD_count": len(_state.get("clients", [])),
        "audit_entries": len(_state["audit"].entries),
        "audit_head": _state["audit"].head,
        "feature_flag_on": _is_enabled(),
    }


@app.get("/portfolio/snapshot")
async def portfolio_snapshot() -> dict[str, Any]:
    if not _is_enabled():
        raise HTTPException(503, "agent_futu.enabled flag is off")
    clients = _state.get("clients") or []
    if not clients:
        raise HTTPException(503, "no OpenD clients registered (set FUTU_AUTOSTART=1)")
    snapshot = aggregate_snapshot(clients)
    return snapshot.model_dump(by_alias=True)


@app.get("/audit/head")
async def audit_head() -> dict[str, Any]:
    audit: FutuAuditLog = _state["audit"]
    return {
        "head": audit.head,
        "entries": len(audit.entries),
        "chain_verified": audit.verify_chain(),
    }
