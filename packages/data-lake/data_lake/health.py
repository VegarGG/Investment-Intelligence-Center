"""Per-store health probes (workflow 02 §7.7).

Each probe returns a small dict the orchestrator can render at /health/<store>.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from data_lake.exceptions import StoreUnavailable
from data_lake.postgres import session


async def pg_health() -> dict[str, Any]:
    try:
        async with session("ro") as s:
            ping = (await s.execute(text("SELECT 1"))).scalar_one()
            advice_n = (await s.execute(text("SELECT count(*) FROM lake.advice"))).scalar_one()
        return {"status": "ok", "ping": int(ping), "advice_rows": int(advice_n)}
    except Exception as exc:
        raise StoreUnavailable(f"postgres: {exc}") from exc


async def chroma_health() -> dict[str, Any]:
    try:
        from data_lake.chroma import CANONICAL_COLLECTIONS, client

        c = client()
        c.heartbeat()
        names = [coll.name for coll in c.list_collections()]
        missing = [name for name in CANONICAL_COLLECTIONS if name not in names]
        return {
            "status": "ok" if not missing else "degraded",
            "collections_present": names,
            "missing_canonical": missing,
        }
    except Exception as exc:
        raise StoreUnavailable(f"chroma: {exc}") from exc


async def minio_health() -> dict[str, Any]:
    try:
        from data_lake.minio import CANONICAL_BUCKETS, client

        c = client()
        present = []
        missing = []
        for spec in CANONICAL_BUCKETS:
            if c.bucket_exists(spec.name):
                present.append(spec.name)
            else:
                missing.append(spec.name)
        return {
            "status": "ok" if not missing else "degraded",
            "buckets_present": present,
            "missing": missing,
        }
    except Exception as exc:
        raise StoreUnavailable(f"minio: {exc}") from exc


async def redis_health() -> dict[str, Any]:
    try:
        import inspect

        from data_lake.redis import client

        result = client().ping()
        ok = await result if inspect.isawaitable(result) else bool(result)
        return {"status": "ok" if ok else "degraded"}
    except Exception as exc:
        raise StoreUnavailable(f"redis: {exc}") from exc
