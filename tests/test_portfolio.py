"""Tests for portfolio crowding engine."""
import numpy as np
import pytest

from trader_arun.portfolio.crowding import OpenPosition, PortfolioCrowdingEngine


def test_empty_portfolio_zero_crowding():
    eng = PortfolioCrowdingEngine(equity_usd=10_000)
    p = eng.compute()
    assert p.score == 0.0
    assert p.directional_exposure == 0.0


def test_single_long_position_low_crowding():
    eng = PortfolioCrowdingEngine(equity_usd=10_000)
    eng.add_position(OpenPosition(
        pair="BTC", side="LONG", notional_usd=2_000,
        strategy_id="S2", btc_beta=1.0, eth_beta=0.5,
    ))
    p = eng.compute()
    # Single small position → low crowding.
    assert p.score < 20.0
    assert p.directional_exposure == pytest.approx(0.2)


def test_many_long_positions_high_crowding():
    eng = PortfolioCrowdingEngine(equity_usd=10_000)
    # 5 longs of $4k each = $20k notional = 2x equity directional.
    for pair in ["BTC", "ETH", "SOL", "ADA", "XRP"]:
        eng.add_position(OpenPosition(
            pair=pair, side="LONG", notional_usd=4_000,
            strategy_id="S2", btc_beta=1.0, eth_beta=0.5,
        ))
    p = eng.compute()
    assert p.directional_exposure == pytest.approx(2.0)
    assert p.score > 30.0


def test_balanced_long_short_zero_exposure():
    eng = PortfolioCrowdingEngine(equity_usd=10_000)
    eng.add_position(OpenPosition(pair="BTC", side="LONG", notional_usd=5_000,
                                   strategy_id="S2", btc_beta=1.0, eth_beta=0.5))
    eng.add_position(OpenPosition(pair="ETH", side="SHORT", notional_usd=5_000,
                                   strategy_id="S3", btc_beta=0.5, eth_beta=1.0))
    p = eng.compute()
    assert p.directional_exposure == pytest.approx(0.0)


def test_pca_concentration_with_correlated_returns():
    eng = PortfolioCrowdingEngine(equity_usd=10_000)
    # Feed identical returns for 3 pairs → PC1 explains ~100% variance.
    for pair in ["BTC", "ETH", "SOL"]:
        for _ in range(100):
            eng.update_returns(pair, 0.001)
    pca = eng._pca_concentration()
    assert pca > 0.9  # highly correlated


def test_pca_low_concentration_with_uncorrelated_returns():
    eng = PortfolioCrowdingEngine(equity_usd=10_000)
    rng = np.random.default_rng(42)
    for pair in ["BTC", "ETH", "SOL"]:
        for _ in range(100):
            eng.update_returns(pair, float(rng.standard_normal() * 0.01))
    pca = eng._pca_concentration()
    assert pca < 0.7  # diversified


def test_remove_position():
    eng = PortfolioCrowdingEngine(equity_usd=10_000)
    eng.add_position(OpenPosition(
        pair="BTC", side="LONG", notional_usd=5_000,
        strategy_id="S2", btc_beta=1.0, eth_beta=0.5,
    ))
    assert len(eng.positions) == 1
    eng.remove_position("BTC")
    assert len(eng.positions) == 0
