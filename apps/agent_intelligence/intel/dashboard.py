"""Dashboard JSON snapshot (workflow 10 §5.11). Workflow 21 owns the inner
shape; we keep it open and add the headline ticker + bias balance + macro
regime so the dashboard can render the basic widgets out of the box."""

from __future__ import annotations

from datetime import UTC, datetime

from schema import IntelDashboardV1, IntelDigestV1


def from_digest(digest: IntelDigestV1) -> IntelDashboardV1:
    payload = {
        "macro_regime": digest.macro_regime,
        "macro_thesis": digest.macro_thesis,
        "headline_ticker": [
            {
                "rank": ev.rank,
                "headline": ev.headline,
                "regime_change_score": ev.regime_change_score,
            }
            for ev in digest.events[:10]
        ],
        "bias_balance": digest.bias_balance.model_dump(),
        "events_count": len(digest.events),
    }
    return IntelDashboardV1(issued_at=datetime.now(UTC), payload=payload)
