"""Tests for backtest framework."""
import pytest

from trader_arun.backtest.engine import BacktestConfig, BacktestEngine
from trader_arun.backtest.costs import CostModel
from trader_arun.backtest.metrics import DeflatedSharpeRatio, compute_metrics


def test_cost_model_round_trip():
    cm = CostModel()
    # Round-trip = 2*(5+3) + 0.5*1 = 16.5 bps
    assert cm.round_trip_cost_bps(holding_periods_8h=1.0) == pytest.approx(16.5)
    # Net edge = 50 - 16.5 = 33.5
    assert cm.net_edge_bps(50.0, 1.0) == pytest.approx(33.5)


def test_compute_metrics_empty():
    m = compute_metrics([])
    assert m.n_trades == 0


def test_compute_metrics_basic():
    returns = [10, -5, 8, -3, 12, -2, 6, -4]
    m = compute_metrics(returns)
    assert m.n_trades == 8
    assert m.win_rate == pytest.approx(0.5)
    assert m.expectancy_bps > 0


def test_deflated_sharpe_zero_when_no_trials():
    dsr = DeflatedSharpeRatio(
        observed_sharpe=2.0, n_trials=1, n_obs=100,
        skewness=0.0, kurtosis=0.0,
    )
    assert dsr.expected_max_sharpe() == 0.0


def test_deflated_sharpe_penalises_multiple_trials():
    dsr1 = DeflatedSharpeRatio(
        observed_sharpe=2.0, n_trials=1, n_obs=100,
        skewness=0.0, kurtosis=0.0,
    )
    dsr10 = DeflatedSharpeRatio(
        observed_sharpe=2.0, n_trials=100, n_obs=100,
        skewness=0.0, kurtosis=0.0,
    )
    assert dsr10.expected_max_sharpe() > dsr1.expected_max_sharpe()


def test_backtest_engine_runs_with_minimal_data():
    eng = BacktestEngine()
    result = eng.run(signals=[], forward_returns=[1.0, 2.0])
    # Insufficient data → returns zeros but doesn't crash.
    assert result.n_signals == 2


def test_backtest_engine_with_realistic_data():
    eng = BacktestEngine(BacktestConfig(n_bootstrap=100))
    # Simulate 50 trades with positive expectancy.
    returns = [5, -3, 8, -2, 4, 6, -1, 7, -4, 5] * 5
    result = eng.run(signals=[None]*len(returns), forward_returns=returns)
    assert result.n_signals == 50
    assert result.in_sample.expectancy_bps > 0
    assert result.out_of_sample.n_trades > 0
    assert isinstance(result.deflated_sharpe, float)
