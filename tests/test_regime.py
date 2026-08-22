"""Tests for regime classifier."""
import pytest

from trader_arun.core.config import PairConfig
from trader_arun.core.types import Candle, OrderBookSnapshot, Ticker
from trader_arun.data.manager import PairSnapshot
from trader_arun.regime.classifier import RegimeEngine
from trader_arun.core.types import Regime


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


def _candles(n=60, drift=0.0, vol=0.001) -> list[Candle]:
    rng = __import__("numpy").random.default_rng(42)
    candles = []
    price = 100.0
    for i in range(n):
        ret = drift + rng.standard_normal() * vol
        price *= (1 + ret)
        candles.append(Candle(
            venue="coindcx", symbol="BTCUSDT", tf="1m",
            open=price, high=price*1.001, low=price*0.999, close=price,
            volume=10.0,
            open_time=1000 + i * 60, close_time=1060 + i * 60,
        ))
    return candles


def _range_candles(n=60, base=100.0, vol=0.001) -> list[Candle]:
    """Truly flat price series with small noise → RANGE regime."""
    rng = __import__("numpy").random.default_rng(123)
    candles = []
    for i in range(n):
        # Price oscillates around base, no compounding.
        price = base + rng.standard_normal() * 0.05
        candles.append(Candle(
            venue="coindcx", symbol="BTCUSDT", tf="1m",
            open=price, high=price+0.05, low=price-0.05, close=price,
            volume=10.0,
            open_time=1000 + i * 60, close_time=1060 + i * 60,
        ))
    return candles


def test_unknown_when_no_data():
    snap = PairSnapshot(pair=_pair())
    eng = RegimeEngine()
    result = eng.classify(snap, {})
    assert result.regime == Regime.UNKNOWN


def test_trend_up_with_strong_drift():
    snap = PairSnapshot(pair=_pair())
    snap.coindcx_candles = _candles(n=60, drift=0.005, vol=0.001)
    snap.coindcx_ticker = Ticker(
        venue="coindcx", symbol="BTCUSDT", base="BTC", quote="USDT",
        bid=130, ask=130, last=130, mid=130, spread_bps=1.0,
        timestamp=1000.0, received_at=1000.0,
    )
    snap.coindcx_book = OrderBookSnapshot(
        venue="coindcx", symbol="BTCUSDT",
        bids=[(129, 10000)], asks=[(131, 10000)],
        timestamp=1000.0, received_at=1000.0,
    )
    eng = RegimeEngine()
    result = eng.classify(snap, {})
    assert result.regime == Regime.TREND_UP


def test_trend_down_with_strong_negative_drift():
    snap = PairSnapshot(pair=_pair())
    snap.coindcx_candles = _candles(n=60, drift=-0.005, vol=0.001)
    snap.coindcx_ticker = Ticker(
        venue="coindcx", symbol="BTCUSDT", base="BTC", quote="USDT",
        bid=70, ask=70, last=70, mid=70, spread_bps=1.0,
        timestamp=1000.0, received_at=1000.0,
    )
    snap.coindcx_book = OrderBookSnapshot(
        venue="coindcx", symbol="BTCUSDT",
        bids=[(69, 10000)], asks=[(71, 10000)],
        timestamp=1000.0, received_at=1000.0,
    )
    eng = RegimeEngine()
    result = eng.classify(snap, {})
    assert result.regime == Regime.TREND_DOWN


def test_range_with_no_drift():
    snap = PairSnapshot(pair=_pair())
    # Use higher vol so the t-stat drops below 2.5 (true RANGE).
    snap.coindcx_candles = _range_candles(n=60, base=100.0, vol=0.005)
    snap.coindcx_ticker = Ticker(
        venue="coindcx", symbol="BTCUSDT", base="BTC", quote="USDT",
        bid=100, ask=100, last=100, mid=100, spread_bps=1.0,
        timestamp=1000.0, received_at=1000.0,
    )
    snap.coindcx_book = OrderBookSnapshot(
        venue="coindcx", symbol="BTCUSDT",
        bids=[(99, 10000)], asks=[(101, 10000)],
        timestamp=1000.0, received_at=1000.0,
    )
    eng = RegimeEngine()
    result = eng.classify(snap, {})
    assert result.regime == Regime.RANGE


def test_cross_exchange_dislocation_when_mids_far_apart():
    snap = PairSnapshot(pair=_pair())
    snap.coindcx_candles = _candles(n=60, drift=0.0, vol=0.001)
    snap.coindcx_ticker = Ticker(
        venue="coindcx", symbol="BTCUSDT", base="BTC", quote="USDT",
        bid=100, ask=100, last=100, mid=100, spread_bps=1.0,
        timestamp=1000.0, received_at=1000.0,
    )
    snap.coindcx_book = OrderBookSnapshot(
        venue="coindcx", symbol="BTCUSDT",
        bids=[(99, 10000)], asks=[(101, 10000)],
        timestamp=1000.0, received_at=1000.0,
    )
    snap.external_tickers["binance"] = Ticker(
        venue="binance", symbol="BTCUSDT", base="BTC", quote="USDT",
        bid=105, ask=105, last=105, mid=105, spread_bps=1.0,
        timestamp=1000.0, received_at=1000.0,
    )
    eng = RegimeEngine()
    result = eng.classify(snap, {})
    # 500 bp dislocation should trigger CROSS_EXCHANGE_DISLOCATION.
    assert result.regime == Regime.CROSS_EXCHANGE_DISLOCATION
