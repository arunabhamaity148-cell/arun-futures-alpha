"""Trade cluster detector — burst of trades in a short window.

Used as a secondary indicator of informed/large-participant activity.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque

from ..core.types import Trade


@dataclass
class TradeCluster:
    score: float                    # 0–100
    cluster_count: int
    cluster_volume_usd: float
    dominant_side: str              # "BUY" | "SELL" | "FLAT"
    window_sec: float


class TradeClusterDetector:
    """Detect bursts of trades within `window_sec`."""

    __slots__ = ("_window_sec", "_trades", "_baseline_per_min", "_samples")

    def __init__(self, window_sec: float = 10.0, baseline_samples: int = 60) -> None:
        self._window_sec = float(window_sec)
        self._trades: Deque[Trade] = deque()
        # Rolling baseline of trades/min — used for cluster intensity.
        self._baseline_per_min: Deque[int] = deque(maxlen=baseline_samples)
        self._samples = 0

    def update(self, trades: list[Trade]) -> TradeCluster:
        # Add new trades.
        for t in trades:
            self._trades.append(t)
        # Prune old.
        if self._trades:
            cutoff = self._trades[-1].timestamp - self._window_sec
            while self._trades and self._trades[0].timestamp < cutoff:
                self._trades.popleft()

        cluster_count = len(self._trades)
        cluster_volume = sum(t.price * t.size for t in self._trades)

        buy_vol = sum(t.price * t.size for t in self._trades if t.side == "BUY")
        sell_vol = sum(t.price * t.size for t in self._trades if t.side == "SELL")
        if buy_vol + sell_vol == 0:
            dominant_side = "FLAT"
        elif buy_vol > sell_vol * 1.2:
            dominant_side = "BUY"
        elif sell_vol > buy_vol * 1.2:
            dominant_side = "SELL"
        else:
            dominant_side = "FLAT"

        # Update baseline every minute.
        self._samples += 1
        if self._samples >= 6:  # ~every minute if called every 10s
            self._baseline_per_min.append(cluster_count)
            self._samples = 0

        if self._baseline_per_min:
            baseline = sum(self._baseline_per_min) / len(self._baseline_per_min)
            if baseline > 0:
                intensity = cluster_count / (baseline * 3.0)  # 3x baseline = saturation
            else:
                intensity = 1.0 if cluster_count > 5 else 0.0
        else:
            intensity = min(1.0, cluster_count / 20.0)

        score = 100.0 * min(1.0, intensity)
        return TradeCluster(
            score=score,
            cluster_count=cluster_count,
            cluster_volume_usd=cluster_volume,
            dominant_side=dominant_side,
            window_sec=self._window_sec,
        )
