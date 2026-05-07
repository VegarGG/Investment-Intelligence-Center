"""Deterministic JSON serialization for hash chains and golden-set diffing.

Workflow 05 §11 gotcha: Pydantic v2 serializes datetimes with microsecond
precision and timezone offsets that vary across producers. The advice
ledger's hash chain (workflow 02 §5.4) needs byte-stable bytes, so we
canonicalize to: sorted keys, no whitespace, ISO-8601 UTC seconds.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import orjson
from pydantic import BaseModel


def canonical_json(model: BaseModel | dict[str, Any]) -> bytes:
    """Stable JSON: sorted keys, no whitespace, naive datetimes treated as
    UTC, all datetimes serialized as `YYYY-MM-DDTHH:MM:SS[.ffffff]Z`.

    Returns bytes (the hash-chain input). Use .decode() for text storage.
    """
    if isinstance(model, BaseModel):
        payload = model.model_dump(by_alias=True, mode="json")
    else:
        payload = model

    return orjson.dumps(
        payload,
        default=_orjson_default,
        option=orjson.OPT_SORT_KEYS | orjson.OPT_NAIVE_UTC | orjson.OPT_UTC_Z,
    )


def _orjson_default(obj: Any) -> Any:
    """Fallback for types orjson can't natively encode (e.g., Pydantic
    secret strings, ulid.ULID)."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if hasattr(obj, "__str__"):
        return str(obj)
    raise TypeError(f"canonical_json: cannot encode {type(obj).__name__}")
