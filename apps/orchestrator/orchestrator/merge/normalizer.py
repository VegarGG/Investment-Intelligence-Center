"""Asset normalization — canonical ticker resolution (workflow 06 §6.5).

For v0 we trust the agent-supplied ticker and apply only string hygiene.
The Polygon symbol-master integration (workflow 02 §7.3) lands in a
follow-up PR — at that point this module will look up
lake.symbol_master and resolve dual-listed CN tickers, ADRs, etc.
"""

from __future__ import annotations

import re

_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


def canonical_ticker(raw: str) -> str:
    """String-hygiene normalization. Uppercase + trim. Reject obvious junk."""
    cleaned = raw.strip().upper()
    if not _TICKER_RE.match(cleaned):
        raise ValueError(f"ticker {raw!r} does not match canonical format")
    return cleaned
