"""Portfolio crowding — BTC/ETH beta, correlations, PCA concentration."""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..core.types import PortfolioCrowding


@dataclass
class OpenPosition:
    pair: str
    side: str           # "LONG" | "SHORT"
    notional_usd: float
    strategy_id: str
    btc_beta: float = 0.0
    eth_beta: float = 0.0


class PortfolioCrowdingEngine:
    """Track open positions and compute portfolio crowding metrics."""

    def __init__(self, equity_usd: float = 10_000.0) -> None:
        self._equity = float(equity_usd)
        self._positions: list[OpenPosition] = []
        # Rolling correlation matrix of pair returns (kept small — 10 pairs max).
        self._returns_history: dict[str, list[float]] = {}

    def update_returns(self, pair: str, ret: float) -> None:
        if pair not in self._returns_history:
            self._returns_history[pair] = []
        self._returns_history[pair].append(ret)
        # Bounded — keep last 240 samples (1h of 1m returns).
        if len(self._returns_history[pair]) > 240:
            self._returns_history[pair] = self._returns_history[pair][-240:]

    def add_position(self, pos: OpenPosition) -> None:
        self._positions.append(pos)

    def remove_position(self, pair: str) -> None:
        self._positions = [p for p in self._positions if p.pair != pair]

    def compute(self) -> PortfolioCrowding:
        if not self._positions:
            return PortfolioCrowding(
                score=0.0, btc_beta_avg=0.0, eth_beta_avg=0.0,
                sector_corr_avg=0.0, pca_concentration=0.0,
                directional_exposure=0.0, timestamp=time.time(),
            )
        # BTC/ETH beta averages (already provided per-position).
        btc_beta_avg = float(np.mean([p.btc_beta for p in self._positions]))
        eth_beta_avg = float(np.mean([p.eth_beta for p in self._positions]))

        # Directional exposure: net notional / equity (signed).
        net = sum(
            (p.notional_usd if p.side == "LONG" else -p.notional_usd)
            for p in self._positions
        )
        directional_exposure = net / self._equity if self._equity > 0 else 0.0

        # Sector correlation: average |corr| across all pairs present in history.
        sector_corr_avg = self._avg_abs_corr()

        # PCA concentration: share of variance from PC1.
        pca_concentration = self._pca_concentration()

        # Score: high directional exposure + high correlation + high PCA → crowded.
        directional_score = min(50.0, abs(directional_exposure) * 25.0)
        corr_score = min(30.0, sector_corr_avg * 30.0)
        pca_score = min(20.0, max(0.0, pca_concentration - 0.5) * 40.0)
        score = directional_score + corr_score + pca_score

        return PortfolioCrowding(
            score=score,
            btc_beta_avg=btc_beta_avg,
            eth_beta_avg=eth_beta_avg,
            sector_corr_avg=sector_corr_avg,
            pca_concentration=pca_concentration,
            directional_exposure=directional_exposure,
            timestamp=time.time(),
        )

    def _avg_abs_corr(self) -> float:
        pairs = [p for p in self._returns_history if len(self._returns_history[p]) >= 30]
        if len(pairs) < 2:
            return 0.0
        corrs: list[float] = []
        for i in range(len(pairs)):
            for j in range(i + 1, len(pairs)):
                a = np.array(self._returns_history[pairs[i]][-60:], dtype=float)
                b = np.array(self._returns_history[pairs[j]][-60:], dtype=float)
                n = min(len(a), len(b))
                if n < 30:
                    continue
                if a.std() == 0 or b.std() == 0:
                    continue
                c = float(np.corrcoef(a[-n:], b[-n:])[0, 1])
                if math.isfinite(c):
                    corrs.append(abs(c))
        if not corrs:
            return 0.0
        return float(np.mean(corrs))

    def _pca_concentration(self) -> float:
        pairs = [p for p in self._returns_history if len(self._returns_history[p]) >= 60]
        if len(pairs) < 2:
            return 0.0
        # Build matrix: rows = time, cols = pairs.
        min_len = min(len(self._returns_history[p]) for p in pairs)
        if min_len < 30:
            return 0.0
        mat = np.array([
            self._returns_history[p][-min_len:]
            for p in pairs
        ], dtype=float).T  # shape (T, N)
        # Center columns.
        mat = mat - mat.mean(axis=0, keepdims=True)
        try:
            # SVD-based PCA.
            u, s, vh = np.linalg.svd(mat, full_matrices=False)
            total = s.sum()
            if total <= 0:
                return 0.0
            return float(s[0] ** 2 / (s ** 2).sum())
        except np.linalg.LinAlgError:
            return 0.0

    @property
    def positions(self) -> list[OpenPosition]:
        return list(self._positions)
