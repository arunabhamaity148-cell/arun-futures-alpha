"""Tests for mismatch engine."""
import math
from unittest.mock import MagicMock

import pytest

from trader_arun.core.config import PairConfig
from trader_arun.core.types import (
    Candle, FundingRate, OpenInterest, OrderBookSnapshot, Ticker,
)
from trader_arun.data.manager import PairSnapshot
from trader_arun.data.mismatch import MismatchEngine


def _make_pair() -> PairConfig:
    return PairConfig(
        rank=1, base="BTC", quote="USDT",
        coindcx_spot_symbol="B-BTC_USDT",
        coindcx_futures_symbol="BTCUSDT",
        binance_symbol="BTCUSDT",
        hyperliquid_asset="BTC",
        kraken_pair="XXBTZUSD",
        bybit_symbol="BTCUSDT",
        primary_discovery="binance",
        best_strategy="S2/S1", primary_veto="V1",
    )


def _make_ticker(venue, mid, spread_bps=2.0) -> Ticker:
    spread = mid * spread_bps / 1e4
    return Ticker(
        venue=venue, symbol=f"{venue.upper()}BTC", base="BTC", quote="USDT",
        bid=mid - spread/2, ask=mid + spread/2, last=mid, mid=mid,
        spread_bps=spread_bps, timestamp=1000.0, received_at=1000.0,
    )


def _make_book(venue, mid, depth_usd=500_000) -> OrderBookSnapshot:
    # Simple flat book: 5% depth = depth_usd/2 each side.
    half = depth_usd / 2 / mid
    bid_price = mid * 0.99
    ask_price = mid * 1.01
    bids = [(bid_price, half)]
    asks = [(ask_price, half)]
    return OrderBookSnapshot(venue=venue, symbol=f"{venue}BTCUSDT",
                             bids=bids, asks=asks, timestamp=1000.0, received_at=1000.0)


def _make_candles(venue, base=100.0, n=30) -> list[Candle]:
    return [
        Candle(venue=venue, symbol=f"{venue}BTCUSDT", tf="1m",
               open=base + i, high=base + i + 0.5, low=base + i - 0.5,
               close=base + i + 0.1, volume=10.0,
               open_time=1000 + i * 60, close_time=1060 + i * 60)
        for i in range(n)
    ]


def test_mismatch_normal_when_venues_agree():
    pair = _make_pair()
    snap = PairSnapshot(pair=pair)
    snap.coindcx_ticker = _make_ticker("coindcx", 100.0)
    snap.coindcx_book = _make_book("coindcx", 100.0)
    snap.coindcx_candles = _make_candles("coindcx")
    snap.external_tickers["binance"] = _make_ticker("binance", 100.01)
    snap.external_books["binance"] = _make_book("binance", 100.01)
    snap.binance_candles = _make_candles("binance")

    engine = MismatchEngine()
    report = engine.compute(snap, {"coindcx_futures_verified": True})
    assert report.score < 40  # normal
    assert report.band == "NORMAL"


def test_mismatch_high_when_coindcx_diverges():
    pair = _make_pair()
    snap = PairSnapshot(pair=pair)
    snap.coindcx_ticker = _make_ticker("coindcx", 100.0)
    snap.coindcx_book = _make_book("coindcx", 100.0)
    snap.coindcx_candles = _make_candles("coindcx")
    snap.external_tickers["binance"] = _make_ticker("binance", 100.5)  # 50 bps dev
    snap.external_books["binance"] = _make_book("binance", 100.5)
    snap.binance_candles = _make_candles("binance", base=100.0)

    engine = MismatchEngine()
    report = engine.compute(snap, {"coindcx_futures_verified": True})
    # Deviation of 50 bp should push score up significantly.
    assert report.score > 20
    assert "price_dev" in report.components


def test_mismatch_no_trade_when_coindcx_far_off():
    pair = _make_pair()
    snap = PairSnapshot(pair=pair)
    snap.coindcx_ticker = _make_ticker("coindcx", 100.0)
    snap.coindcx_book = _make_book("coindcx", 100.0)
    snap.coindcx_candles = _make_candles("coindcx")
    # External at 105 — 500 bp deviation
    snap.external_tickers["binance"] = _make_ticker("binance", 105.0)
    snap.external_books["binance"] = _make_book("binance", 105.0)
    snap.binance_candles = _make_candles("binance", base=105.0)

    engine = MismatchEngine()
    report = engine.compute(snap, {"coindcx_futures_verified": True})
    assert report.score >= 60.0
    assert report.band == "NO_TRADE"


def test_mismatch_fail_closed_when_data_missing():
    pair = _make_pair()
    snap = PairSnapshot(pair=pair)
    # No tickers set.
    engine = MismatchEngine()
    report = engine.compute(snap, {"coindcx_futures_verified": False})
    assert report.score >= 50  # missing data → fail-closed bias
    assert "contract_diff" in report.components
    # NOT VERIFIED adds 50 to contract_diff
    assert report.components["contract_diff"] == 50.0
