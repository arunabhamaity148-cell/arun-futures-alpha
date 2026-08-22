"""Regression tests for repaired data-pipeline faults."""
from __future__ import annotations

import asyncio
import dataclasses
import time
from unittest.mock import AsyncMock

import pytest

from trader_arun.core.config import Config, PairConfig
from trader_arun.core.types import Ticker
from trader_arun.data.coindcx import CoinDCXProvider
from trader_arun.data.manager import DataManager
from trader_arun.data.mismatch import MismatchEngine


def _pair() -> PairConfig:
    return PairConfig(
        rank=1,
        base="BTC",
        quote="USDT",
        coindcx_spot_symbol="B-BTC_USDT",
        coindcx_futures_symbol="BTCUSDT",
        binance_symbol="BTCUSDT",
        hyperliquid_asset="BTC",
        kraken_pair="XXBTZUSD",
        bybit_symbol="BTCUSDT",
        primary_discovery="binance",
        best_strategy="S2/S1",
        primary_veto="V1",
    )


def _ticker(venue: str, mid: float, ts: float) -> Ticker:
    spread = mid * 2 / 1e4
    return Ticker(
        venue=venue,
        symbol=f"{venue}-BTCUSDT",
        base="BTC",
        quote="USDT",
        bid=mid - spread / 2,
        ask=mid + spread / 2,
        last=mid,
        mid=mid,
        spread_bps=2.0,
        timestamp=ts,
        received_at=ts,
    )


def test_coindcx_orderbook_accepts_dict_payload():
    book = CoinDCXProvider._parse_orderbook(
        "B-BTC_USDT",
        {
            "bids": {"100.0": "2.0", "99.0": "1.0"},
            "asks": {"101.0": "3.0", "102.0": "1.0"},
            "timestamp": "1700000000000",
        },
    )
    assert book.bids[0] == (100.0, 2.0)
    assert book.asks[0] == (101.0, 3.0)
    assert book.timestamp == 1700000000.0


@pytest.mark.asyncio
async def test_verify_futures_universe_requires_exact_symbol_match():
    cfg = Config(pairs=(_pair(),))
    async with DataManager(cfg) as dm:
        dm.coindcx.discover_futures_symbols = AsyncMock(return_value={"BTCUSDT", "ETHUSDT"})
        assert await dm.verify_futures_universe() is True
        dm.coindcx.discover_futures_symbols = AsyncMock(return_value={"B-BTC_USDT"})
        assert await dm.verify_futures_universe() is False


@pytest.mark.asyncio
async def test_pair_snapshot_provider_isolation_keeps_fast_reference_data():
    cfg = dataclasses.replace(Config(), pairs=(_pair(),), request_timeout_sec=0.05)
    async with DataManager(cfg) as dm:
        dm.coindcx.get_orderbook = AsyncMock(side_effect=asyncio.TimeoutError())
        dm.coindcx.get_candles = AsyncMock(return_value=[])
        dm.coindcx.get_ticker = AsyncMock(return_value=None)
        dm.binance.get_ticker = AsyncMock(return_value=_ticker("binance", 100.0, time.time()))
        dm.binance.get_orderbook = AsyncMock(return_value=None)
        dm.binance.get_candles = AsyncMock(return_value=[])
        dm.binance.get_funding = AsyncMock(return_value=None)
        dm.binance.get_open_interest = AsyncMock(return_value=None)
        snap = await dm.fetch_pair_snapshot(_pair())
        assert snap.coindcx_ticker is None
        assert snap.external_tickers["binance"].mid == 100.0


def test_mismatch_penalises_timestamp_skew():
    snap = dataclasses.make_dataclass("Tmp", [("pair", PairConfig), ("coindcx_ticker", Ticker | None), ("external_tickers", dict), ("coindcx_candles", list), ("binance_candles", list), ("hl_candles", list), ("coindcx_book", object), ("external_books", dict)])
    pair = _pair()
    now = time.time()
    obj = snap(
        pair=pair,
        coindcx_ticker=_ticker("coindcx", 100.0, now),
        external_tickers={"binance": _ticker("binance", 100.0, now - 20.0)},
        coindcx_candles=[],
        binance_candles=[],
        hl_candles=[],
        coindcx_book=None,
        external_books={},
    )
    report = MismatchEngine().compute(obj, {"coindcx_futures_verified": True})
    assert report.components["timestamp_skew_ms"] >= 20_000
    assert report.score >= 15.0
