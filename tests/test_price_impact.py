"""Tests for price impact estimator."""
import pytest

from trader_arun.core.types import OrderBookSnapshot
from trader_arun.microstructure.price_impact import PriceImpactEstimator


def _book(depth_usd=1_000_000) -> OrderBookSnapshot:
    # 100k units at $100 each side → $10M depth, scaled down.
    n_units = depth_usd / 2 / 100
    bids = [(99.5, n_units)]
    asks = [(100.5, n_units)]
    return OrderBookSnapshot(venue="test", symbol="BTCUSDT",
                             bids=bids, asks=asks, timestamp=1000.0, received_at=1000.0)


def test_zero_impact_for_small_order():
    est = PriceImpactEstimator(k=10.0)
    result = est.estimate(_book(1_000_000), notional_usd=1_000)
    assert result.expected_slippage_bps < 1.0


def test_high_impact_for_large_order():
    est = PriceImpactEstimator(k=10.0)
    result = est.estimate(_book(100_000), notional_usd=100_000)
    assert result.expected_slippage_bps > 5.0


def test_illiquid_book_flagged():
    est = PriceImpactEstimator(k=10.0, illiquid_threshold_usd=500_000)
    result = est.estimate(_book(100_000), notional_usd=10_000)
    assert result.is_illiquid


def test_empty_book_returns_max_slippage():
    est = PriceImpactEstimator(k=10.0)
    empty_book = OrderBookSnapshot(venue="test", symbol="BTCUSDT",
                                    bids=[], asks=[], timestamp=1000.0, received_at=1000.0)
    result = est.estimate(empty_book, notional_usd=10_000)
    assert result.expected_slippage_bps == 999.0
    assert result.is_illiquid
