"""Incremental rolling statistics — O(1) per update, never O(history).

- RollingMean     — running sum / count over window
- RollingVariance — Welford one-pass, windowed
- EWMA            — exponential moving average
- RollingZScore   — (x - mean) / std over window
- RollingQuantile — approximate via fixed buckets (no P2 — too noisy)
"""
from __future__ import annotations

import math
from collections import deque
from typing import Deque

import numpy as np


class RollingMean:
    """Exact rolling mean over a fixed-length window."""

    __slots__ = ("_window", "_maxlen", "_sum")

    def __init__(self, maxlen: int) -> None:
        if maxlen <= 0:
            raise ValueError("maxlen must be positive")
        self._maxlen = int(maxlen)
        self._window: Deque[float] = deque(maxlen=self._maxlen)
        self._sum = 0.0

    def update(self, x: float) -> float:
        if not math.isfinite(x):
            return self._sum / max(len(self._window), 1)
        if len(self._window) == self._maxlen:
            self._sum -= self._window[0]
        self._window.append(x)
        self._sum += x
        return self._sum / len(self._window)

    @property
    def mean(self) -> float:
        n = len(self._window)
        return self._sum / n if n else float("nan")

    @property
    def count(self) -> int:
        return len(self._window)

    def reset(self) -> None:
        self._window.clear()
        self._sum = 0.0


class RollingVariance:
    """Windowed variance using Welford numerically-stable accumulation."""

    __slots__ = ("_maxlen", "_window", "_sum", "_sumsq")

    def __init__(self, maxlen: int) -> None:
        if maxlen <= 0:
            raise ValueError("maxlen must be positive")
        self._maxlen = int(maxlen)
        self._window: Deque[float] = deque(maxlen=self._maxlen)
        self._sum = 0.0
        self._sumsq = 0.0

    def update(self, x: float) -> float:
        if not math.isfinite(x):
            return self.variance
        if len(self._window) == self._maxlen:
            old = self._window[0]
            self._sum -= old
            self._sumsq -= old * old
        self._window.append(x)
        self._sum += x
        self._sumsq += x * x
        return self.variance

    @property
    def mean(self) -> float:
        n = len(self._window)
        return self._sum / n if n else float("nan")

    @property
    def variance(self) -> float:
        n = len(self._window)
        if n < 2:
            return float("nan")
        m = self._sum / n
        return max(0.0, (self._sumsq / n) - m * m) * n / (n - 1)

    @property
    def std(self) -> float:
        v = self.variance
        return math.sqrt(v) if math.isfinite(v) else float("nan")

    @property
    def count(self) -> int:
        return len(self._window)

    def reset(self) -> None:
        self._window.clear()
        self._sum = 0.0
        self._sumsq = 0.0


class EWMA:
    """Exponential moving average. Halflife in samples."""

    __slots__ = ("_alpha", "_value", "_initialised")

    def __init__(self, halflife: float) -> None:
        if halflife <= 0:
            raise ValueError("halflife must be positive")
        self._alpha = 1.0 - math.exp(-math.log(2.0) / halflife)
        self._value = float("nan")
        self._initialised = False

    def update(self, x: float) -> float:
        if not math.isfinite(x):
            return self._value
        if not self._initialised:
            self._value = x
            self._initialised = True
        else:
            self._value = self._alpha * x + (1.0 - self._alpha) * self._value
        return self._value

    @property
    def value(self) -> float:
        return self._value

    def reset(self) -> None:
        self._value = float("nan")
        self._initialised = False


class RollingZScore:
    """Z-score of latest value vs rolling window mean/std."""

    __slots__ = ("_rv",)

    def __init__(self, maxlen: int) -> None:
        self._rv = RollingVariance(maxlen)

    def update(self, x: float) -> float:
        self._rv.update(x)
        s = self._rv.std
        if not math.isfinite(s) or s == 0:
            return 0.0
        return (x - self._rv.mean) / s

    @property
    def mean(self) -> float:
        return self._rv.mean

    @property
    def std(self) -> float:
        return self._rv.std

    @property
    def count(self) -> int:
        return self._rv.count


class RollingQuantile:
    """Approximate rolling quantile using a fixed bucket histogram.

    Not as precise as sort-based quantile, but O(1) update and bounded memory.
    Suitable for percentile thresholds in calibration.
    """

    __slots__ = ("_bins", "_count", "_min", "_max", "_bucket_counts", "_n_bins")

    def __init__(self, n_bins: int = 100, min_val: float = 0.0, max_val: float = 1.0) -> None:
        if n_bins <= 0:
            raise ValueError("n_bins must be positive")
        if max_val <= min_val:
            raise ValueError("max_val must exceed min_val")
        self._n_bins = int(n_bins)
        self._min = float(min_val)
        self._max = float(max_val)
        self._bucket_counts = np.zeros(self._n_bins, dtype=np.int64)
        self._count = 0

    def update(self, x: float) -> None:
        if not math.isfinite(x):
            return
        if x < self._min:
            x = self._min
        elif x > self._max:
            x = self._max
        idx = int((x - self._min) / (self._max - self._min) * (self._n_bins - 1))
        self._bucket_counts[idx] += 1
        self._count += 1

    def quantile(self, q: float) -> float:
        if self._count == 0:
            return float("nan")
        if not 0.0 <= q <= 1.0:
            raise ValueError("q must be in [0,1]")
        target = q * self._count
        cumulative = 0
        for i in range(self._n_bins):
            cumulative += int(self._bucket_counts[i])
            if cumulative >= target:
                # Linear interpolation within bucket.
                bin_lower = self._min + i * (self._max - self._min) / self._n_bins
                return bin_lower
        return self._max

    @property
    def count(self) -> int:
        return self._count

    def reset(self) -> None:
        self._bucket_counts.fill(0)
        self._count = 0


def safe_zscore(x: float, mean: float, std: float, fallback: float = 0.0) -> float:
    """Z-score with safe fallback for non-finite inputs."""
    if not all(math.isfinite(v) for v in (x, mean, std)):
        return fallback
    if std == 0:
        return fallback
    return (x - mean) / std
