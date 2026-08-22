"""Tests for SL/TP builder."""
import pytest

from trader_arun.core.types import Candle, Side
from trader_arun.risk.sltp import SLTPBuilder


def _candles(n=30, base=100.0, atr_target=1.0) -> list[Candle]:
    candles = []
    for i in range(n):
        c = Candle(
            venue="coindcx", symbol="BTCUSDT", tf="1m",
            open=base + i * 0.1,
            high=base + i * 0.1 + atr_target,
            low=base + i * 0.1 - atr_target,
            close=base + i * 0.1 + 0.05,
            volume=10.0,
            open_time=1000 + i * 60,
            close_time=1060 + i * 60,
        )
        candles.append(c)
    return candles


def test_long_sltp_valid():
    builder = SLTPBuilder()
    result = builder.build(_candles(), Side.LONG, current_price=105.0)
    assert result.valid
    assert result.stop_loss < 105.0
    assert result.tp1 > 105.0
    assert result.tp2 > result.tp1
    assert result.tp3 > result.tp2
    assert result.rr >= 1.5


def test_short_sltp_valid():
    builder = SLTPBuilder()
    result = builder.build(_candles(), Side.SHORT, current_price=105.0)
    assert result.valid
    assert result.stop_loss > 105.0
    assert result.tp1 < 105.0
    assert result.tp2 < result.tp1
    assert result.tp3 < result.tp2


def test_flat_side_invalid():
    builder = SLTPBuilder()
    result = builder.build(_candles(), Side.FLAT, current_price=105.0)
    assert not result.valid


def test_insufficient_candles():
    builder = SLTPBuilder()
    result = builder.build(_candles(n=5), Side.LONG, current_price=105.0)
    assert not result.valid


def test_zero_price_invalid():
    builder = SLTPBuilder()
    result = builder.build(_candles(), Side.LONG, current_price=0.0)
    assert not result.valid
