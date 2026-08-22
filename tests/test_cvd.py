"""Tests for CVD calculator."""
import pytest

from trader_arun.core.types import Trade
from trader_arun.microstructure.cvd import CVDCalculator


def _trade(side, price, size, ts=1000.0):
    return Trade(venue="test", symbol="BTCUSDT", price=price, size=size,
                 side=side, timestamp=ts)


def test_cvd_basic_buy():
    cvd = CVDCalculator(window_sec=60)
    cvd.update(_trade("BUY", 100, 1.0))
    cvd.update(_trade("BUY", 100, 1.0))
    assert cvd.cvd == pytest.approx(200.0)
    assert cvd.buy_volume == pytest.approx(200.0)
    assert cvd.sell_volume == 0.0


def test_cvd_mixed():
    cvd = CVDCalculator(window_sec=60)
    cvd.update(_trade("BUY", 100, 2.0))   # +200 USD
    cvd.update(_trade("SELL", 100, 1.0))  # -100 USD
    assert cvd.cvd == pytest.approx(100.0)
    assert cvd.delta_ratio == pytest.approx(1.0 / 3.0)


def test_cvd_window_evicts_old_trades():
    cvd = CVDCalculator(window_sec=10)
    cvd.update(_trade("BUY", 100, 1.0, ts=0.0))
    cvd.update(_trade("BUY", 100, 1.0, ts=5.0))
    cvd.update(_trade("BUY", 100, 1.0, ts=20.0))  # evicts first two
    # Only the third trade should be in window.
    assert cvd.cvd == pytest.approx(100.0)


def test_cvd_zscore_zero_when_constant():
    cvd = CVDCalculator(window_sec=60)
    # Alternate buy/sell of equal size → CVD stays at 0 (constant).
    for _ in range(20):
        cvd.update(_trade("BUY", 100, 1.0, ts=1000.0))
        cvd.update(_trade("SELL", 100, 1.0, ts=1000.0))
    # CVD should be 0 (balanced flow).
    assert cvd.cvd == 0.0
    assert cvd.buy_volume == cvd.sell_volume


def test_cvd_reset():
    cvd = CVDCalculator(window_sec=60)
    cvd.update(_trade("BUY", 100, 1.0))
    cvd.reset()
    assert cvd.cvd == 0.0
    assert cvd.buy_volume == 0.0
