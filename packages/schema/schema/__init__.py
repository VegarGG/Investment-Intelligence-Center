"""IIC schema package — Pydantic + TS shared types for every IIC event (workflow 05)."""

from .advice import AdviceV1, Asset, Direction, Evidence
from .backtest import (
    AgentDailyPnL,
    BacktestDailyV1,
    BacktestFillV1,
    BacktestLeaderboardV1,
    BenchmarkDailyPnL,
    LeaderboardEntry,
)
from .canonical import canonical_json
from .intel import (
    BiasBalance,
    IntelBriefV1,
    IntelDashboardV1,
    IntelDigestV1,
    IntelEvent,
    IntelEventSource,
    MacroRegime,
)
from .ops import OpsAlertV1, OpsHeartbeatV1
from .secretary import SecretaryNotifyV1

__version__ = "0.1.0"
__all__ = [
    # advice
    "AdviceV1",
    "Asset",
    "Direction",
    "Evidence",
    # canonical
    "canonical_json",
    # intel
    "BiasBalance",
    "IntelBriefV1",
    "IntelDashboardV1",
    "IntelDigestV1",
    "IntelEvent",
    "IntelEventSource",
    "MacroRegime",
    # backtest
    "AgentDailyPnL",
    "BacktestDailyV1",
    "BacktestFillV1",
    "BacktestLeaderboardV1",
    "BenchmarkDailyPnL",
    "LeaderboardEntry",
    # secretary + ops
    "SecretaryNotifyV1",
    "OpsAlertV1",
    "OpsHeartbeatV1",
]
