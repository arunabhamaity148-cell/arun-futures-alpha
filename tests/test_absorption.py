"""Tests for absorption detector."""
import pytest

from trader_arun.core.types import OrderBookSnapshot, Side, Trade
from trader_arun.microstructure.absorption import AbsorptionDetector
from trader_arun.microstructure.cvd import CVDCalculator


def _trade(side, price, size, ts):
    return Trade(venue="test", symbol="BTCUSDT", price=price, size=size, side=side, timestamp=ts)


def _book(bid_size=100, ask_size=100, mid=100.0) -> OrderBookSnapshot:
    bids = [(mid - 0.5, bid_size)]
    asks = [(mid + 0.5, ask_size)]
    return OrderBookSnapshot(venue="test", symbol="BTCUSDT",
                             bids=bids, asks=asks, timestamp=1000.0, received_at=1000.0)


def test_no_absorption_with_balanced_flow():
    cvd = CVDCalculator(window_sec=60)
    det = AbsorptionDetector(cvd, window_sec=60)
    trades = [
        _trade("BUY", 100, 1.0, 1000),
        _trade("SELL", 100, 1.0, 1001),
    ]
    result = det.update(trades, _book(), current_price=100.0)
    # Balanced flow + price not moving → mild absorption, but low score.
    assert result.score < 50.0


def test_absorption_when_sell_pressure_no_price_move():
    cvd = CVDCalculator(window_sec=60)
    det = AbsorptionDetector(cvd, window_sec=60)
    # Heavy sell-side trades, price stable.
    trades = [_trade("SELL", 100, 5.0, 1000 + i) for i in range(20)]
    result = det.update(trades, _book(), current_price=100.0)
    # Should detect LONG absorption setup (buyers absorbing sells).
    assert result.direction == Side.LONG
    assert result.cvd_z < 0  # negative CVD = sell pressure


def test_no_absorption_when_price_moves():
    cvd = CVDCalculator(window_sec=60)
    det = AbsorptionDetector(cvd, window_sec=60)
    # First call with initial price.
    det.update([_trade("SELL", 100, 5.0, 1000)], _book(), current_price=100.0)
    # Now significant sell-side volume with price dropping.
    trades = [_trade("SELL", 95, 5.0, 1001 + i) for i in range(20)]
    result = det.update(trades, _book(), current_price=95.0)
    # Price moved significantly → not absorption.
    assert result.score < 50.0
