"""Backtest framework — anti-overfit methodology (research §19)."""
from .engine import BacktestEngine, BacktestConfig, BacktestResult
from .costs import CostModel
from .metrics import compute_metrics, DeflatedSharpeRatio

__all__ = [
    "BacktestEngine",
    "BacktestConfig",
    "BacktestResult",
    "CostModel",
    "compute_metrics",
    "DeflatedSharpeRatio",
]
