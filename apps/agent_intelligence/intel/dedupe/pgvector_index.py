"""pgvector-backed SemanticIndex (P2.3).

Uses ``lake.intel_embeds(event_id, embedding VECTOR(N), ts)`` populated
by the pipeline. Cosine similarity is computed server-side via the
``<=>`` operator (pgvector) and converted to similarity in [0, 1] for
the gate's threshold comparison.

The default embedding dimension is 1536 (OpenAI ``text-embedding-3-small``).
Override with ``IIC_EMBED_DIM`` if a different embed model is wired.
"""

from __future__ import annotations

import os
from datetime import datetime

from .semantic_gate import SemanticIndex


class PgvectorSemanticIndex(SemanticIndex):
    """SemanticIndex backed by Postgres + pgvector."""

    __slots__ = ("_sm", "_dim")

    def __init__(self, sessionmaker, *, dim: int = 1536) -> None:
        self._sm = sessionmaker
        self._dim = dim

    @classmethod
    def from_env(cls) -> "PgvectorSemanticIndex":
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        url = os.environ.get(
            "IIC_PG_DSN",
            "postgresql+asyncpg://iic_app@iic-postgres:5432/iic",
        )
        engine = create_async_engine(url, pool_pre_ping=True)
        sm = async_sessionmaker(engine, expire_on_commit=False)
        dim = int(os.environ.get("IIC_EMBED_DIM", "1536"))
        return cls(sm, dim=dim)

    @staticmethod
    def _vec_literal(vec: list[float]) -> str:
        """Render a Python list as a pgvector literal `'[v1,v2,...]'`."""
        return "[" + ",".join(f"{v:.7f}" for v in vec) + "]"

    async def search(
        self, vector: list[float], *, k: int, since: datetime
    ) -> list[tuple[str, float, datetime]]:
        from sqlalchemy import text

        if len(vector) != self._dim:
            raise ValueError(
                f"pgvector index dim={self._dim} but got vector of {len(vector)}"
            )

        sql = text(
            """
            SELECT event_id::text AS event_id,
                   1 - (embedding <=> CAST(:vec AS vector)) AS cos_sim,
                   ts
              FROM lake.intel_embeds
             WHERE ts >= :since
             ORDER BY embedding <=> CAST(:vec AS vector)
             LIMIT :k
            """
        )
        params = {"vec": self._vec_literal(vector), "since": since, "k": k}
        async with self._sm() as session:
            res = await session.execute(sql, params)
            rows = res.all()
        return [(row.event_id, float(row.cos_sim), row.ts) for row in rows]

    async def insert(self, doc_id: str, vector: list[float], indexed_at: datetime) -> None:
        from sqlalchemy import text

        if len(vector) != self._dim:
            raise ValueError(
                f"pgvector index dim={self._dim} but got vector of {len(vector)}"
            )
        sql = text(
            """
            INSERT INTO lake.intel_embeds (event_id, embedding, ts)
            VALUES (gen_random_uuid(), CAST(:vec AS vector), :ts)
            """
        )
        async with self._sm() as session:
            await session.execute(
                sql, {"vec": self._vec_literal(vector), "ts": indexed_at}
            )
            await session.commit()
