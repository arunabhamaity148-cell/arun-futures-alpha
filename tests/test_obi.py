"""Tests for OBI calculator."""
import pytest

from trader_arun.core.types import OrderBookSnapshot
from trader_arun.microstructure.obi import OBICalculator


def _book(bid_size, ask_size, mid=100.0) -> OrderBookSnapshot:
    bids = [(mid - 0.5, bid_size)] if bid_size > 0 else []
    asks = [(mid + 0.5, ask_size)] if ask_size > 0 else []
    return OrderBookSnapshot(venue="test", symbol="BTCUSDT",
                             bids=bids, asks=asks, timestamp=1000.0, received_at=1000.0)


def test_obi_balanced_book():
    calc = OBICalculator(levels=1)
    result = calc.compute(_book(100, 100))
    assert result["obi_top"] == pytest.approx(0.0)


def test_obi_bid_heavy():
    calc = OBICalculator(levels=1)
    result = calc.compute(_book(150, 50))
    assert result["obi_top"] > 0.4


def test_obi_ask_heavy():
    calc = OBICalculator(levels=1)
    result = calc.compute(_book(50, 150))
    assert result["obi_top"] < -0.4


def test_obi_empty_book():
    calc = OBICalculator(levels=1)
    result = calc.compute(_book(0, 0))
    assert result["obi_top"] == 0.0
