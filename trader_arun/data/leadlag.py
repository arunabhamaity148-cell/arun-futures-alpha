"""Cross-exchange lead/lag engine — measures external venue → CoinDCX lag."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..core.rolling import RollingMean
from ..data.manager import PairSnapshot


@dataclass
class LeadLagReport:
    best_lag_min: int                 # > 0 = external leads CoinDCX
    best_corr: float
    stability: float                  # 0–1, peak prominence
    is_actionable: bool               # lag >= 1m AND corr >= 0.5
    direction_consistent: bool        # sign of correlation stable over window


class LeadLagEngine:
    """Per-pair lead/lag analyser."""

    def __init__(self, max_lag_min: int = 10) -> None:
        self._max_lag = int(max_lag_min)
        # Stability tracker — recent best_lag values.
        self._lag_history: list[int] = []
        self._corr_history: list[float] = []
        self._max_history = 30

    def analyse(self, snap: PairSnapshot) -> LeadLagReport:
        if not snap.coindcx_candles:
            return LeadLagReport(0, 0.0, 0.0, False, False)
        ext_candles = snap.binance_candles or snap.hl_candles
        if not ext_candles or len(ext_candles) < 30:
            return LeadLagReport(0, 0.0, 0.0, False, False)

        # Align 1m candles.
        cd_by_time = {int(c.open_time // 60): c.close for c in snap.coindcx_candles[-60:]}
        ext_by_time = {int(c.open_time // 60): c.close for c in ext_candles[-60:]}
        common = sorted(set(cd_by_time.keys()) & set(ext_by_time.keys()))
        if len(common) < 25:
            return LeadLagReport(0, 0.0, 0.0, False, False)

        ext_prices = np.array([ext_by_time[t] for t in common], dtype=float)
        cd_prices = np.array([cd_by_time[t] for t in common], dtype=float)
        ext_ret = np.diff(np.log(ext_prices))
        cd_ret = np.diff(np.log(cd_prices))

        if len(ext_ret) < 20:
            return LeadLagReport(0, 0.0, 0.0, False, False)

        max_lag = min(self._max_lag, len(ext_ret) // 3)
        lags = list(range(-max_lag, max_lag + 1))
        corrs = []
        for lag in lags:
            if lag < 0:
                a, b = ext_ret[-lag:], cd_ret[:lag]
            elif lag > 0:
                a, b = ext_ret[:-lag], cd_ret[lag:]
            else:
                a, b = ext_ret, cd_ret
            n = min(len(a), len(b))
            if n < 10:
                corrs.append(0.0)
                continue
            a_, b_ = a[:n], b[:n]
            if a_.std() == 0 or b_.std() == 0:
                corrs.append(0.0)
                continue
            c = float(np.corrcoef(a_, b_)[0, 1])
            corrs.append(c)

        if not corrs:
            return LeadLagReport(0, 0.0, 0.0, False, False)

        best_idx = int(np.argmax(corrs))
        best_lag = lags[best_idx]
        best_corr = corrs[best_idx]

        # Stability: peak prominence (peak - median of other values).
        others = [c for i, c in enumerate(corrs) if i != best_idx]
        median_others = float(np.median(others)) if others else 0.0
        prominence = best_corr - median_others
        stability = max(0.0, min(1.0, prominence * 2.0))

        # Track history for direction consistency.
        self._lag_history.append(best_lag)
        self._corr_history.append(best_corr)
        if len(self._lag_history) > self._max_history:
            self._lag_history = self._lag_history[-self._max_history:]
            self._corr_history = self._corr_history[-self._max_history:]

        if len(self._corr_history) >= 5:
            sign_consistency = (
                sum(1 for c in self._corr_history if c > 0) / len(self._corr_history)
            )
            direction_consistent = sign_consistency >= 0.7 or sign_consistency <= 0.3
        else:
            direction_consistent = True

        is_actionable = best_lag >= 1 and best_corr >= 0.5 and stability >= 0.2

        return LeadLagReport(
            best_lag_min=best_lag,
            best_corr=best_corr,
            stability=stability,
            is_actionable=is_actionable,
            direction_consistent=direction_consistent,
        )
