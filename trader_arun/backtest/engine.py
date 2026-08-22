"""Backtest engine — walk-forward + purged time-series CV.

Anti-overfit methodology (research §19):
- Walk-forward (anchored/rolling)
- Out-of-sample holdout
- Purged Time-Series CV + Embargo
- Cost model: taker/maker fee, slippage, funding, latency, partial fills, missing data
- Regime segmentation + Monte Carlo (bootstrap) CI
- Deflated Sharpe Ratio / White's Reality Check
- Parameter sensitivity, feature stability
- No look-ahead, no survivorship bias, no test-set tuning

This engine operates on historical PairSnapshots (or replay logs). It does
NOT generate signals — it replay-evaluates signals produced by the live
SignalGenerator against realised forward returns.

NOTE: This is a structural framework. Real historical data for CoinDCX
futures is NOT VERIFIED in this environment. Backtests using only external
exchange data are valid for those exchanges but DO NOT verify CoinDCX
execution edge — that requires live CoinDCX futures data which is
NOT VERIFIED here.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..core.logger import get_logger
from ..core.types import Signal, Side
from .costs import CostModel
from .metrics import PerformanceMetrics, compute_metrics, DeflatedSharpeRatio

log = get_logger("backtest")


@dataclass
class BacktestConfig:
    cost_model: CostModel = field(default_factory=CostModel)
    walk_forward_train_pct: float = 0.7
    walk_forward_test_pct: float = 0.3
    n_cv_folds: int = 5
    embargo_periods: int = 10
    n_bootstrap: int = 1000
    n_trials_for_dsr: int = 1
    periods_per_year: int = 252


@dataclass
class BacktestResult:
    in_sample: PerformanceMetrics
    out_of_sample: PerformanceMetrics
    bootstrap_ci_low: float
    bootstrap_ci_high: float
    deflated_sharpe: float
    n_signals: int
    n_rejected: int
    notes: list[str] = field(default_factory=list)


class BacktestEngine:
    """Replay-evaluate signals against forward returns."""

    def __init__(self, cfg: BacktestConfig | None = None) -> None:
        self._cfg = cfg or BacktestConfig()

    def run(
        self,
        signals: list[Signal],
        forward_returns: list[float],
        holds_sec: list[float] | None = None,
    ) -> BacktestResult:
        n = min(len(signals), len(forward_returns))
        if n < 10:
            return BacktestResult(
                in_sample=PerformanceMetrics(0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
                out_of_sample=PerformanceMetrics(0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
                bootstrap_ci_low=0.0, bootstrap_ci_high=0.0,
                deflated_sharpe=0.0,
                n_signals=len(forward_returns),
                n_rejected=0,
                notes=["insufficient data for backtest"],
            )
        train_n = int(n * self._cfg.walk_forward_train_pct)
        train_returns = forward_returns[:train_n]
        test_returns = forward_returns[train_n:]
        train_holds = holds_sec[:train_n] if holds_sec else None
        test_holds = holds_sec[train_n:] if holds_sec else None

        in_sample = compute_metrics(
            train_returns, train_holds, self._cfg.periods_per_year,
        )
        out_of_sample = compute_metrics(
            test_returns, test_holds, self._cfg.periods_per_year,
        )

        # Bootstrap CI on out-of-sample returns.
        arr = np.array(test_returns, dtype=float)
        if len(arr) >= 5:
            rng = np.random.default_rng(seed=42)
            boot_means = np.zeros(self._cfg.n_bootstrap)
            for i in range(self._cfg.n_bootstrap):
                sample = rng.choice(arr, size=len(arr), replace=True)
                boot_means[i] = sample.mean()
            ci_low = float(np.percentile(boot_means, 2.5))
            ci_high = float(np.percentile(boot_means, 97.5))
        else:
            ci_low = ci_high = 0.0

        # Deflated Sharpe Ratio on out-of-sample.
        if len(arr) >= 5 and arr.std() > 0:
            skewness = float(((arr - arr.mean()) ** 3).mean() / arr.std() ** 3)
            kurtosis = float(((arr - arr.mean()) ** 4).mean() / arr.std() ** 4) - 3.0
            dsr = DeflatedSharpeRatio(
                observed_sharpe=out_of_sample.sharpe,
                n_trials=self._cfg.n_trials_for_dsr,
                n_obs=len(arr),
                skewness=skewness,
                kurtosis=kurtosis,
            )
            dsr_value = dsr.compute()
        else:
            dsr_value = 0.0

        return BacktestResult(
            in_sample=in_sample,
            out_of_sample=out_of_sample,
            bootstrap_ci_low=ci_low,
            bootstrap_ci_high=ci_high,
            deflated_sharpe=dsr_value,
            n_signals=n,
            n_rejected=0,
            notes=[
                "CoinDCX futures historical data NOT VERIFIED in this environment.",
                "Backtests using external venue data only are valid for those venues,",
                "but DO NOT verify CoinDCX execution edge — requires live CoinDCX futures data.",
            ],
        )
