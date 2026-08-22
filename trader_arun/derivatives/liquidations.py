"""Liquidation analyser — cascade index, exhaustion score, continuation score.

Mathematical definitions (research §13 V4):
    CASCADE_INDEX       = Σ|liq_vol_6h| / 30d_baseline_median
    LIQUIDATION_EXHAUSTION_SCORE = 100 * sigmoid(cascade_index - cascade_threshold)
    CONTINUATION_SCORE  = inverse — high if cascade still accelerating

We track liq volume over rolling windows. Memory is bounded by deques.
"""
from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque

from ..core.rolling import RollingVariance
from ..core.types import Liquidation, Side


@dataclass
class CascadeReport:
    cascade_index: float             # ratio of 6h liq vol to baseline
    exhaustion_score: float          # 0–100
    continuation_score: float        # 0–100
    long_liq_6h_usd: float
    short_liq_6h_usd: float
    dominant_side: Side              # which side got liquidated
    is_exhausting: bool              # cascade peaked and stabilising


class LiquidationAnalyser:
    """Per-pair liquidation cascade analyser."""

    __slots__ = (
        "_base", "_window_sec", "_baseline_sec",
        "_events", "_baseline_samples", "_z_window",
    )

    def __init__(
        self,
        base: str,
        window_sec: float = 6 * 3600,         # 6h cascade window
        baseline_sec: float = 30 * 86400,     # 30d baseline
    ) -> None:
        self._base = base
        self._window_sec = float(window_sec)
        self._baseline_sec = float(baseline_sec)
        # All liq events — bounded by baseline window size.
        # Each entry: (ts, size_usd, side)
        self._events: Deque[tuple[float, float, Side]] = deque(maxlen=10_000)
        # Rolling variance of 6h liq totals sampled every hour — for z-score.
        self._z_window = RollingVariance(maxlen=720)  # 30 days hourly

    def update(self, events: list[Liquidation], now: float | None = None) -> CascadeReport:
        ts_now = now or time.time()
        # Append new events.
        for e in events:
            self._events.append((e.timestamp, e.size_usd, e.side))
        # Prune old events beyond baseline window.
        cutoff = ts_now - self._baseline_sec
        while self._events and self._events[0][0] < cutoff:
            self._events.popleft()

        # Compute 6h window totals.
        win_cutoff = ts_now - self._window_sec
        long_vol = 0.0
        short_vol = 0.0
        for ts, size, side in self._events:
            if ts >= win_cutoff:
                if side == Side.LONG:
                    long_vol += size
                else:
                    short_vol += size
        total_vol = long_vol + short_vol

        # Baseline = median of past hourly totals (cheap approximation).
        baseline = self._estimate_baseline(ts_now)
        cascade_index = total_vol / baseline if baseline > 0 else 0.0

        # Exhaustion: high cascade_index + volume decelerating → exhaustion.
        # We approximate deceleration by comparing last 1h vs previous 1h.
        last_1h_vol = sum(
            s for ts, s, _ in self._events
            if ts >= ts_now - 3600
        )
        prev_1h_vol = sum(
            s for ts, s, _ in self._events
            if ts_now - 7200 <= ts < ts_now - 3600
        )
        if prev_1h_vol > 0:
            deceleration_ratio = last_1h_vol / prev_1h_vol
        else:
            deceleration_ratio = 1.0 if last_1h_vol > 0 else 0.0

        # Exhaustion: cascade peaked and now decelerating.
        # Score grows when cascade_index is high AND deceleration_ratio is < 0.5.
        if cascade_index > 1.0:
            exhaustion_score = 100.0 * (
                1.0 / (1.0 + math.exp(-(cascade_index - 2.0)))
                * (1.0 - min(1.0, deceleration_ratio))
            )
        else:
            exhaustion_score = 0.0

        # Continuation: cascade still accelerating.
        continuation_score = 100.0 * (
            min(1.0, cascade_index / 3.0) * min(1.0, deceleration_ratio)
        )

        dominant_side = Side.LONG if long_vol > short_vol else Side.SHORT
        is_exhausting = (
            cascade_index >= 1.5
            and deceleration_ratio < 0.5
            and exhaustion_score >= 40.0
        )

        return CascadeReport(
            cascade_index=cascade_index,
            exhaustion_score=exhaustion_score,
            continuation_score=continuation_score,
            long_liq_6h_usd=long_vol,
            short_liq_6h_usd=short_vol,
            dominant_side=dominant_side,
            is_exhausting=is_exhausting,
        )

    def _estimate_baseline(self, ts_now: float) -> float:
        """Estimate 6h baseline from historical buckets.

        Buckets events into hourly buckets over the baseline window, then
        returns the median bucketed volume scaled up to 6h.
        """
        if not self._events:
            return 1.0  # avoid divide-by-zero; small default
        # Build hourly buckets for the last 30 days (max 720 buckets).
        cutoff = ts_now - self._baseline_sec
        buckets: dict[int, float] = {}
        for ts, size, _ in self._events:
            if ts < cutoff:
                continue
            bucket = int(ts // 3600)
            buckets[bucket] = buckets.get(bucket, 0.0) + size
        if not buckets:
            return 1.0
        # Take median of non-zero buckets, scaled to 6h.
        vals = sorted(buckets.values())
        median_hourly = vals[len(vals) // 2] if vals else 0.0
        # 6h baseline = 6 × hourly median (rough).
        return max(1.0, median_hourly * 6.0)
