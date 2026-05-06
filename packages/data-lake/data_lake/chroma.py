"""ChromaDB client + collection helpers (workflow 02 §5.6).

GROUND TRUTH collections:
  - news                  (bge-m3)
  - filings               (bge-m3)
  - persona_memory_<slug> (bge-m3)
  - me                    (reserved for post-v2.1)
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chromadb.api.models.Collection import Collection
    from chromadb.api.types import HttpClient as HttpClientType

from data_lake.config import get_config

CANONICAL_COLLECTIONS: tuple[str, ...] = ("news", "filings", "me")
"""Always-on collections. Persona memory collections are created lazily by slug."""


@dataclass(frozen=True, slots=True)
class Hit:
    doc_id: str
    text: str
    score: float
    metadata: dict[str, Any]


@lru_cache(maxsize=1)
def client() -> HttpClientType:
    import chromadb

    cfg = get_config()
    return chromadb.HttpClient(host=cfg.chroma_host, port=cfg.chroma_port)


def get_or_create(name: str, metadata: dict[str, Any] | None = None) -> Collection:
    return client().get_or_create_collection(
        name=name,
        metadata={"embedding_model": "bge-m3", **(metadata or {})},
    )


def upsert_doc(
    collection_name: str, doc_id: str, text: str, meta: dict[str, Any]
) -> None:
    coll = get_or_create(collection_name)
    coll.upsert(ids=[doc_id], documents=[text], metadatas=[meta])


def query(
    collection_name: str,
    text: str,
    k: int = 8,
    where: dict[str, Any] | None = None,
) -> list[Hit]:
    coll = get_or_create(collection_name)
    res = coll.query(query_texts=[text], n_results=k, where=where)
    ids = (res.get("ids") or [[]])[0]
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    distances = (res.get("distances") or [[]])[0]
    out: list[Hit] = []
    for i, doc in enumerate(docs):
        out.append(
            Hit(
                doc_id=ids[i],
                text=doc,
                score=1.0 - float(distances[i]) if distances else 0.0,
                metadata=metas[i] if metas else {},
            )
        )
    return out


def bootstrap_collections(persona_slugs: tuple[str, ...] = ()) -> list[str]:
    """Idempotently create the canonical collections + persona-memory ones.
    Returns the list of names actually present after the call."""
    created: list[str] = []
    for name in CANONICAL_COLLECTIONS:
        get_or_create(name)
        created.append(name)
    for slug in persona_slugs:
        coll_name = f"persona_memory_{slug}"
        get_or_create(coll_name, metadata={"persona_slug": slug})
        created.append(coll_name)
    return created
