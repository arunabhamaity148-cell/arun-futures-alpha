"""Performance metrics — Sharpe, Sortino, MaxDD, Deflated Sharpe Ratio."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass
class PerformanceMetrics:
    n_trades: int
    win_rate: float
    avg_win_bps: float
    avg_loss_bps: float
    profit_factor: float
    expectancy_bps: float
    sharpe: float
    sortino: float
    max_drawdown_pct: float
    avg_hold_sec: float


def compute_metrics(
    returns: list[float],
    holds_sec: list[float] | None = None,
    periods_per_year: int = 252,
) -> PerformanceMetrics:
    n = len(returns)
    if n == 0:
        return PerformanceMetrics(0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    arr = np.array(returns, dtype=float)
    wins = arr[arr > 0]
    losses = arr[arr <= 0]
    win_rate = len(wins) / n
    avg_win = float(wins.mean()) if len(wins) > 0 else 0.0
    avg_loss = float(losses.mean()) if len(losses) > 0 else 0.0
    if avg_loss != 0:
        profit_factor = -avg_win / avg_loss * win_rate / max(1e-9, 1 - win_rate)
    else:
        profit_factor = float("inf") if avg_win > 0 else 0.0
    expectancy = float(arr.mean())
    std = float(arr.std(ddof=1)) if n > 1 else 0.0
    sharpe = expectancy / std * math.sqrt(periods_per_year) if std > 0 else 0.0
    downside = arr[arr < 0]
    if len(downside) > 1:
        downside_std = float(downside.std(ddof=1))
        sortino = expectancy / downside_std * math.sqrt(periods_per_year) if downside_std > 0 else 0.0
    else:
        sortino = 0.0
    cum = np.cumsum(arr)
    running_max = np.maximum.accumulate(cum)
    drawdowns = cum - running_max
    max_dd = float(drawdowns.min()) if len(drawdowns) > 0 else 0.0
    avg_hold = float(np.mean(holds_sec)) if holds_sec else 0.0
    return PerformanceMetrics(
        n_trades=n, win_rate=win_rate,
        avg_win_bps=avg_win, avg_loss_bps=avg_loss,
        profit_factor=profit_factor, expectancy_bps=expectancy,
        sharpe=sharpe, sortino=sortino,
        max_drawdown_pct=abs(max_dd),
        avg_hold_sec=avg_hold,
    )


@dataclass
class DeflatedSharpeRatio:
    """Deflated Sharpe Ratio — multiple-hypothesis correction (Bailey & López de Prado 2014).

    DSR = (Sharpe - E[max(Sharpe|N)]) × sqrt((T-1) / (1 - skew·Sharpe + (kurt-1)/4 · Sharpe^2))

    Inputs:
    - observed_sharpe: the observed (in-sample) Sharpe
    - n_trials: number of strategies tried
    - n_obs: number of return observations
    - skewness: return skewness
    - kurtosis: return kurtosis (excess)
    """
    observed_sharpe: float
    n_trials: int
    n_obs: int
    skewness: float
    kurtosis: float

    def expected_max_sharpe(self) -> float:
        """E[max Sharpe | N trials] under null hypothesis (Sharpe=0)."""
        if self.n_trials <= 1:
            return 0.0
        # Approximation: E[max] ≈ sqrt(2·ln(N)) for iid normal.
        return math.sqrt(2.0 * math.log(self.n_trials))

    def compute(self) -> float:
        if self.n_obs < 2:
            return 0.0
        e_max = self.expected_max_sharpe()
        denom_sq = (
            1.0 - self.skewness * self.observed_sharpe
            + (self.kurtosis - 1) / 4.0 * self.observed_sharpe ** 2
        )
        if denom_sq <= 0:
            # Numerical instability — return 0 (no claim either way).
            return 0.0
        denom = math.sqrt(denom_sq)
        return (self.observed_sharpe - e_max) * math.sqrt((self.n_obs - 1) / denom ** 2)
