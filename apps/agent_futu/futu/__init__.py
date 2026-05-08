"""agent_futu — read-only multi-account FUTU integration (v2.5 T2.7 / B3.3).

Phase 1 (B3.3a, this iteration): mock OpenD against the real `futu-api`
SDK shape. Read-only enforcement is real (the wrapper class refuses to
re-export `place_order` etc.); the broker connection is fake.

Phase 2 (B3.3b, next iteration): real OpenD against a real paper FUTU
account, real network firewall rules, real penetration test. Until
phase 2 ships, `agent_futu.enabled` stays OFF in production.
"""

from .audit import FutuAuditEntry, FutuAuditLog, in_memory_audit_log
from .readonly_client import (
    FORBIDDEN_METHODS,
    FutuReadOnlyClient,
    FutuReadOnlyError,
    PortfolioSnapshotV1,
    PositionState,
    AccountState,
)

__all__ = [
    "FORBIDDEN_METHODS",
    "FutuAuditEntry",
    "FutuAuditLog",
    "FutuReadOnlyClient",
    "FutuReadOnlyError",
    "PortfolioSnapshotV1",
    "PositionState",
    "AccountState",
    "in_memory_audit_log",
]
