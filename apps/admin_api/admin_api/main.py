"""FastAPI app for the admin / configuration API (P3.1).

Routes (`/admin/...`):
  - GET  /admin/health                 - liveness
  - GET  /admin/files                  - list editable YAML paths
  - GET  /admin/files/{rel}            - read one YAML file
  - POST /admin/files/{rel}/propose    - dry-run a YAML write (returns diff)
  - POST /admin/files/{rel}/apply      - commit a YAML write
  - GET  /admin/secrets                - list secrets (presence only)
  - POST /admin/secrets/{name}/rotate  - replace a sops-sealed secret
  - GET  /admin/connectors             - list connectors + cached status
  - POST /admin/connectors/{name}/test - live handshake
  - GET  /admin/schedules              - read cron schedules
  - POST /admin/schedules/apply        - replace cron schedules YAML
  - GET  /admin/crons                  - return CRON_JOBS as seen by the orchestrator
  - GET  /admin/audit/head             - return current lake.config_audit chain hash

The default actor for writes is the bearer token's subject (when auth is
on) or the literal ``"unauthenticated"`` (when ``IIC_ADMIN_OPEN=1`` is set,
which is the default in dev).
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import Body, FastAPI, HTTPException

from . import audit as audit_mod
from . import brokers, config_io, connectors, schedules, secrets

log = logging.getLogger(__name__)
SERVICE = "admin_api"
PORT = int(os.environ.get("PORT", "8090"))

app = FastAPI(title=f"iic.{SERVICE}", version="0.1.0")

# Bound at startup; replaced by tests via `set_audit_sink`.
_audit_sink: audit_mod.AuditSink = audit_mod.InMemoryAuditSink()


def set_audit_sink(sink: audit_mod.AuditSink) -> None:
    global _audit_sink
    _audit_sink = sink


def _actor() -> str:
    # Auth lands in P9. For now, dev installs accept everything and tag
    # the audit row with `unauthenticated`. Production binds an auth
    # middleware that overrides this via request.state.actor.
    return os.environ.get("IIC_ADMIN_DEFAULT_ACTOR", "unauthenticated")


@app.get("/admin/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": SERVICE,
        "editable_paths": [p for p, _ in config_io.editable_paths()],
        "secrets_known": list(secrets.known_secret_names()),
    }


# ---- editable YAML files ---------------------------------------------------
@app.get("/admin/files")
async def list_files() -> list[dict[str, str]]:
    return [{"prefix": prefix, "name": name} for prefix, name in config_io.editable_paths()]


@app.get("/admin/files/{rel:path}")
async def read_file(rel: str) -> dict[str, Any]:
    try:
        snap = config_io.read(rel)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"path": rel, "content": snap.content, "sha256": snap.sha256}


@app.post("/admin/files/{rel:path}/propose")
async def propose_file(rel: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    new_content = str(body.get("content", ""))
    try:
        return config_io.propose(rel, new_content)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/admin/files/{rel:path}/apply")
async def apply_file(rel: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    new_content = str(body.get("content", ""))
    reason = body.get("reason")
    try:
        before = config_io.read(rel)
        snap = config_io.apply(rel, new_content)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    row = await _audit_sink.append(
        actor=_actor(),
        path=rel,
        before_hash=before.sha256,
        after_hash=snap.sha256,
        reason=reason,
    )
    return {
        "path": rel,
        "after_sha256": snap.sha256,
        "audit_id": row.id,
        "chain_hash": row.chain_hash,
    }


# ---- secrets ----------------------------------------------------------------
@app.get("/admin/secrets")
async def list_secrets() -> dict[str, Any]:
    return {"secrets": secrets.list_secrets()}


@app.post("/admin/secrets/{name}/rotate")
async def rotate_secret(name: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    plaintext = body.get("value")
    if not isinstance(plaintext, str) or not plaintext:
        raise HTTPException(status_code=400, detail="missing 'value'")
    try:
        path = secrets.rotate(name, plaintext)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    row = await _audit_sink.append(
        actor=_actor(),
        path=f"secrets/sealed/{name}",
        before_hash=None,
        after_hash="rotated",
        reason="secret rotation via admin UI",
    )
    return {"name": name, "path": str(path), "audit_id": row.id, "chain_hash": row.chain_hash}


# ---- connectors -------------------------------------------------------------
@app.get("/admin/connectors")
async def list_connectors() -> dict[str, Any]:
    return {"connectors": list(connectors.known_connectors())}


@app.post("/admin/connectors/{name}/test")
async def test_connector(name: str) -> dict[str, Any]:
    status = await connectors.test_connector(name)
    return {"name": status.name, "state": status.state, "detail": status.detail}


# ---- schedules --------------------------------------------------------------
@app.get("/admin/schedules")
async def get_schedules() -> dict[str, Any]:
    entries = schedules.load()
    return {
        "schedules": [
            {
                "job_id": e.job_id,
                "enabled": e.enabled,
                "cron": e.cron,
                "timezone": e.timezone,
            }
            for e in entries.values()
        ]
    }


@app.post("/admin/schedules/apply")
async def apply_schedules(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    raw = body.get("schedules")
    if not isinstance(raw, list):
        raise HTTPException(status_code=400, detail="missing 'schedules' list")
    entries = {
        item["job_id"]: schedules.ScheduleEntry(
            job_id=item["job_id"],
            enabled=bool(item.get("enabled", True)),
            cron=item.get("cron"),
            timezone=item.get("timezone"),
        )
        for item in raw
        if isinstance(item, dict) and "job_id" in item
    }
    serialized = schedules.dump(entries)
    before = config_io.read(schedules.SCHEDULES_REL)
    snap = config_io.apply(schedules.SCHEDULES_REL, serialized)
    row = await _audit_sink.append(
        actor=_actor(),
        path=schedules.SCHEDULES_REL,
        before_hash=before.sha256,
        after_hash=snap.sha256,
        reason="schedules update via admin UI",
    )
    return {"path": schedules.SCHEDULES_REL, "audit_id": row.id, "chain_hash": row.chain_hash}


# ---- audit ------------------------------------------------------------------
@app.get("/admin/audit/head")
async def audit_head() -> dict[str, Any]:
    head = await _audit_sink.head()
    return {"head": head}


# ---- brokers (FUTU) (P4.2) -------------------------------------------------
@app.get("/admin/brokers")
async def list_brokers() -> dict[str, Any]:
    return {
        "brokers": [
            {
                "id": b.id,
                "host": b.host,
                "port": b.port,
                "tls_cert": b.tls_cert,
                "quotation_tier": b.quotation_tier,
                "max_subscriptions": b.max_subscriptions,
                "notes": b.notes,
            }
            for b in brokers.load()
        ]
    }


@app.post("/admin/brokers/{broker_id}/verify")
async def verify_broker(broker_id: str) -> dict[str, Any]:
    return await brokers.verify(broker_id)


@app.post("/admin/brokers/apply")
async def apply_brokers(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    raw = body.get("brokers")
    if not isinstance(raw, list):
        raise HTTPException(status_code=400, detail="missing 'brokers' list")
    cfgs = [
        brokers.BrokerCfg(
            id=str(item["id"]),
            host=str(item.get("host", "127.0.0.1")),
            port=int(item.get("port", 11111)),
            tls_cert=item.get("tls_cert") or None,
            quotation_tier=str(item.get("quotation_tier", "free")),
            max_subscriptions=int(item.get("max_subscriptions", 100)),
            notes=str(item.get("notes", "")),
        )
        for item in raw
        if isinstance(item, dict) and "id" in item
    ]
    serialized = brokers.dump(cfgs)
    before = config_io.read(brokers.BROKERS_REL)
    snap = config_io.apply(brokers.BROKERS_REL, serialized)
    row = await _audit_sink.append(
        actor=_actor(),
        path=brokers.BROKERS_REL,
        before_hash=before.sha256,
        after_hash=snap.sha256,
        reason="brokers update via admin UI",
    )
    return {"path": brokers.BROKERS_REL, "audit_id": row.id, "chain_hash": row.chain_hash}


@app.get("/admin/crons")
async def list_crons() -> dict[str, Any]:
    """List cron jobs the orchestrator has registered. Source of truth =
    orchestrator's ``CRON_JOBS`` table (imported lazily so the admin API
    can run without the orchestrator package on PYTHONPATH)."""
    try:
        from orchestrator.triggers.cron import CRON_JOBS  # type: ignore[import-not-found]
    except ImportError:
        return {"crons": [], "note": "orchestrator package not importable in this admin_api install"}
    return {
        "crons": [
            {"name": name, "trigger": cron_kwargs}
            for name, cron_kwargs in CRON_JOBS
        ]
    }
