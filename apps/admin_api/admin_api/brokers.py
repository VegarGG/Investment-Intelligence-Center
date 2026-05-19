"""Brokers (FUTU) admin endpoint support (P4.2).

Stores a per-FutuID config under ``infra/futu/brokers.yaml`` and
provides a ``verify(id)`` action that performs a read-only
``get_global_state`` round-trip via the live FutuQuoteClient (or the
fake when ``FUTU_QUOTE_BACKEND=fake``).

Schema of ``infra/futu/brokers.yaml``::

    brokers:
      - id: futu-001
        host: 127.0.0.1
        port: 11111
        tls_cert: null
        quotation_tier: free      # free | level2 | level2_plus_a
        max_subscriptions: 100
        notes: "Primary HK + US account"
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from featureflags.paths import repo_root

log = logging.getLogger(__name__)

BROKERS_REL = "infra/futu/brokers.yaml"


@dataclass(slots=True)
class BrokerCfg:
    id: str
    host: str = "127.0.0.1"
    port: int = 11111
    tls_cert: str | None = None
    quotation_tier: str = "free"
    max_subscriptions: int = 100
    notes: str = ""


def path() -> Path:
    return repo_root() / BROKERS_REL


def load() -> list[BrokerCfg]:
    p = path()
    if not p.is_file():
        return []
    raw = yaml.safe_load(p.read_text()) or {}
    brokers = (raw.get("brokers") if isinstance(raw, dict) else None) or []
    out: list[BrokerCfg] = []
    for row in brokers:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        out.append(
            BrokerCfg(
                id=str(row["id"]),
                host=str(row.get("host", "127.0.0.1")),
                port=int(row.get("port", 11111)),
                tls_cert=row.get("tls_cert") or None,
                quotation_tier=str(row.get("quotation_tier", "free")),
                max_subscriptions=int(row.get("max_subscriptions", 100)),
                notes=str(row.get("notes", "")),
            )
        )
    return out


def dump(brokers: list[BrokerCfg]) -> str:
    return yaml.safe_dump(
        {
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
                for b in brokers
            ]
        },
        sort_keys=False,
    )


async def verify(broker_id: str) -> dict[str, Any]:
    """Read-only handshake — `get_global_state` against the configured OpenD.

    Returns ``{ok: True, ...}`` on success or ``{ok: False, error: ...}``
    on failure. Never raises so the UI can render the error inline.
    """
    cfg_list = load()
    cfg = next((b for b in cfg_list if b.id == broker_id), None)
    if cfg is None:
        return {"ok": False, "error": f"unknown broker id {broker_id!r}"}
    try:
        # Lazy import — quote_client is in the agent_futu package.
        from futu.quote_client import (  # type: ignore[import-not-found]
            FutuQuoteClient,
            RealQuoteCtx,
        )

        client = FutuQuoteClient(ctx=RealQuoteCtx(host=cfg.host, port=cfg.port))
        ret, data = client.get_global_state()
        return {"ok": ret == 0, "ret": ret, "data": data}
    except Exception as exc:  # noqa: BLE001
        log.warning("broker verify failed for %s: %s", broker_id, exc)
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
