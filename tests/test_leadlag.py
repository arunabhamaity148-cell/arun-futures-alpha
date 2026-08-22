"""Tests for lead/lag engine."""
import pytest

from trader_arun.core.config import PairConfig
from trader_arun.core.types import Candle
from trader_arun.data.leadlag import LeadLagEngine
from trader_arun.data.manager import PairSnapshot


def _pair() -> PairConfig:
    return PairConfig(
        rank=1, base="BTC", quote="USDT",
        coindcx_spot_symbol="B-BTC_USDT",
        coindcx_futures_symbol="BTCUSDT",
        binance_symbol="BTCUSDT",
        hyperliquid_asset="BTC", kraken_pair="XXBTZUSD",
        bybit_symbol="BTCUSDT",
        primary_discovery="binance",
        best_strategy="S2/S1", primary_veto="V1",
    )


def _candles(venue, n=40, lag_min=0, base=100.0, drift=0.001) -> list[Candle]:
    candles = []
    price = base
    for i in range(n):
        # External venue moves first by `drift`, CoinDCX follows `lag_min` later.
        if venue == "ext":
            ret = drift if i < n - lag_min else 0.0
        else:
            ret = drift if i >= lag_min else 0.0
        price *= (1 + ret)
        candles.append(Candle(
            venue=venue, symbol="BTCUSDT", tf="1m",
            open=price, high=price*1.001, low=price*0.999, close=price,
            volume=10.0,
            open_time=i * 60, close_time=i * 60 + 60,
        ))
    return candles


def test_no_signal_with_insufficient_data():
    snap = PairSnapshot(pair=_pair())
    eng = LeadLagEngine()
    report = eng.analyse(snap)
    assert not report.is_actionable


def test_lead_detected_when_external_moves_first():
    snap = PairSnapshot(pair=_pair())
    snap.coindcx_candles = _candles("coindcx", n=40, lag_min=3, drift=0.002)
    snap.binance_candles = _candles("ext", n=40, lag_min=3, drift=0.002)
    eng = LeadLagEngine()
    report = eng.analyse(snap)
    # Should detect a positive lag (external leads coindcx).
    assert report.best_lag_min > 0
    assert report.best_corr > 0.3


def test_no_lead_when_uncorrelated():
    import numpy as np
    snap = PairSnapshot(pair=_pair())
    rng = np.random.default_rng(42)
    snap.coindcx_candles = [
        Candle(venue="coindcx", symbol="BTCUSDT", tf="1m",
               open=p, high=p, low=p, close=p, volume=1.0,
               open_time=i*60, close_time=i*60+60)
        for i, p in enumerate(rng.standard_normal(40) * 0.001 + 100)
    ]
    snap.binance_candles = [
        Candle(venue="binance", symbol="BTCUSDT", tf="1m",
               open=p, high=p, low=p, close=p, volume=1.0,
               open_time=i*60, close_time=i*60+60)
        for i, p in enumerate(rng.standard_normal(40) * 0.001 + 100)
    ]
    eng = LeadLagEngine()
    report = eng.analyse(snap)
    # Random data → low correlation → not actionable.
    assert report.best_corr < 0.6
