"""MinIO client + bucket helpers (workflow 02 §5.7).

GROUND TRUTH buckets and lifecycle:

  iic-filings              hot 90d, cold thereafter
  iic-news-html            expire after 365d
  iic-snapshots-parquet    forever (factor matrices)
  iic-charts               expire after 180d (WeChat brief charts)
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from minio import Minio as MinioClient

from data_lake.config import get_config


@dataclass(frozen=True, slots=True)
class BucketSpec:
    name: str
    expire_days: int | None  # None means forever
    transition_days: int | None = None  # days until "cold" tier (filings only)


CANONICAL_BUCKETS: tuple[BucketSpec, ...] = (
    BucketSpec("iic-filings", expire_days=None, transition_days=90),
    BucketSpec("iic-news-html", expire_days=365),
    BucketSpec("iic-snapshots-parquet", expire_days=None),
    BucketSpec("iic-charts", expire_days=180),
)


@lru_cache(maxsize=1)
def client() -> MinioClient:
    from minio import Minio

    cfg = get_config()
    host, _, port = cfg.minio_endpoint.partition(":")
    return Minio(
        endpoint=f"{host}:{port or '9000'}",
        access_key=cfg.minio_access_key,
        secret_key=cfg.minio_secret_key,
        secure=cfg.minio_secure,
    )


def ensure_bucket(name: str) -> None:
    c = client()
    if not c.bucket_exists(name):
        c.make_bucket(name)


def put_object_bytes(
    bucket: str, key: str, data: bytes, content_type: str = "application/octet-stream"
) -> None:
    from io import BytesIO

    c = client()
    c.put_object(bucket, key, BytesIO(data), length=len(data), content_type=content_type)


def get_object_bytes(bucket: str, key: str) -> bytes:
    c = client()
    response = c.get_object(bucket, key)
    try:
        data: bytes = response.read()
        return data
    finally:
        response.close()
        response.release_conn()
