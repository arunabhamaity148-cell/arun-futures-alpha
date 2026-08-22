"""Order Book Imbalance — ratio of bid depth to total depth at the top of book."""
from __future__ import annotations

import math

from ..core.rolling import RollingVariance
from ..core.types import OrderBookSnapshot


class OBICalculator:
    """Top-of-book and depth-weighted OBI.

    OBI = (bid_size - ask_size) / (bid_size + ask_size) ∈ [-1, +1]
    Also tracks 5%-depth OBI for absorption detection.
    """

    __slots__ = ("_levels", "_z_window")

    def __init__(self, levels: int = 10) -> None:
        self._levels = int(levels)
        self._z_window = RollingVariance(maxlen=120)

    def compute(self, book: OrderBookSnapshot) -> dict[str, float]:
        if not book.bids or not book.asks:
            return {"obi_top": 0.0, "obi_depth5": 0.0, "obi_z": 0.0}
        n = self._levels
        bid_top = sum(s for _, s in book.bids[:n])
        ask_top = sum(s for _, s in book.asks[:n])
        obi_top = (bid_top - ask_top) / (bid_top + ask_top) if (bid_top + ask_top) > 0 else 0.0

        bid_usd, ask_usd = book.depth_within_pct(0.05)
        obi_depth5 = (bid_usd - ask_usd) / (bid_usd + ask_usd) if (bid_usd + ask_usd) > 0 else 0.0

        self._z_window.update(obi_top)
        s = self._z_window.std
        obi_z = (obi_top - self._z_window.mean) / s if (math.isfinite(s) and s > 0) else 0.0

        return {
            "obi_top": obi_top,
            "obi_depth5": obi_depth5,
            "obi_z": obi_z,
            "bid_depth5_usd": bid_usd,
            "ask_depth5_usd": ask_usd,
        }
