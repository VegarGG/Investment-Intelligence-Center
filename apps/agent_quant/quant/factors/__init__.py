"""Factor library (workflow 12 §2.1). Each module exposes a pure
`compute(history, asof)` returning {ticker: raw_value}."""

from .insider import insider_cluster_score
from .mean_reversion import mean_reversion_5d
from .momentum import momentum_12_1
from .vol_risk_premium import vol_risk_premium

__all__ = [
    "insider_cluster_score",
    "mean_reversion_5d",
    "momentum_12_1",
    "vol_risk_premium",
]
