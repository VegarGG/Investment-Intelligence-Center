"""Dedupe gates (workflow 10 §5.3): hash + semantic."""

from .hash_gate import HashGate, InMemoryHashStore
from .semantic_gate import InMemorySemanticIndex, SemanticGate

__all__ = ["HashGate", "InMemoryHashStore", "InMemorySemanticIndex", "SemanticGate"]
