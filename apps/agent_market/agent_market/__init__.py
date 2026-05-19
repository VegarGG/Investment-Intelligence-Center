"""Non-FUTU market data writers (P4.7).

Crypto via ccxt (Binance / Coinbase). FX via FRED daily series. Both
write to ``lake.quotes`` with ``src`` distinct from FUTU so the
backtester can distinguish FUTU L1 from third-party prices.
"""

from .crypto import CryptoQuoteWriter
from .fx import FxQuoteWriter

__all__ = ["CryptoQuoteWriter", "FxQuoteWriter"]
