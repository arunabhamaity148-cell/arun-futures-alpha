"""Cumulative Volume Delta — incremental, O(1) per update.

CVD = sum of (BUY-aggressor volume - SELL-aggressor volume).

Used to detect absorption (price flat + CVD extreme) and aggressive flow.
"""
from __future__ import annotations

import math
from collections import deque
from typing import Deque

from ..core.ringbuffer import RingBuffer
from ..core.rolling import RollingVariance
from ..core.types import Trade


class CVDCalculator:
    """Incremental CVD with bounded memory."""

    __slots__ = ("_cvd", "_buy_vol", "_sell_vol", "_recent_trades", "_window_sec", "_delta_window")

    def __init__(self, window_sec: float = 300.0, max_trades: int = 500) -> None:
        self._cvd = 0.0
        self._buy_vol = 0.0
        self._sell_vol = 0.0
        self._recent_trades: Deque[tuple[float, float, str]] = deque()  # (ts, size, side)
        self._window_sec = float(window_sec)
        self._delta_window = RollingVariance(maxlen=120)

    def update(self, trade: Trade) -> float:
        ts = trade.timestamp
        size = trade.size * trade.price  # USD notional
        self._recent_trades.append((ts, size, trade.side))
        if trade.side == "BUY":
            self._cvd += size
            self._buy_vol += size
        else:
            self._cvd -= size
            self._sell_vol += size
        self._prune(ts)
        # Track 5-min delta for z-score.
        self._delta_window.update(self._cvd)
        return self._cvd

    def _prune(self, current_ts: float) -> None:
        cutoff = current_ts - self._window_sec
        while self._recent_trades and self._recent_trades[0][0] < cutoff:
            ts, size, side = self._recent_trades.popleft()
            if side == "BUY":
                self._cvd -= size
                self._buy_vol -= size
            else:
                self._cvd += size
                self._sell_vol -= size

    @property
    def cvd(self) -> float:
        return self._cvd

    @property
    def buy_volume(self) -> float:
        return self._buy_vol

    @property
    def sell_volume(self) -> float:
        return self._sell_vol

    @property
    def total_volume(self) -> float:
        return self._buy_vol + self._sell_vol

    @property
    def delta_ratio(self) -> float:
        """(-1, +1): -1 = all sell, +1 = all buy."""
        total = self._buy_vol + self._sell_vol
        if total == 0:
            return 0.0
        return (self._buy_vol - self._sell_vol) / total

    def cvd_zscore(self) -> float:
        """Z-score of current CVD vs rolling window."""
        s = self._delta_window.std
        if not math.isfinite(s) or s == 0:
            return 0.0
        return (self._cvd - self._delta_window.mean) / s

    def reset(self) -> None:
        self._cvd = 0.0
        self._buy_vol = 0.0
        self._sell_vol = 0.0
        self._recent_trades.clear()
        self._delta_window.reset()
