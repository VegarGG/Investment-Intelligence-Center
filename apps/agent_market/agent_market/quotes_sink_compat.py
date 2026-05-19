"""Compat re-export so ``agent_market`` doesn't need a hard dep on
``apps.agent_futu.futu.quote_writer`` at install time. The QuoteTick
dataclass lives there; we just expose it under our own namespace.

If you change QuoteTick's shape, update both modules in the same PR;
there is a unit test that asserts they're field-identical.
"""

from __future__ import annotations

# We deliberately re-export — no behaviour, just a stable import surface.
from futu.quote_writer import QuoteTick  # type: ignore[import-not-found]

__all__ = ["QuoteTick"]
