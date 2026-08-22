"""Tests for CoinDCX provider parsing."""
import pytest

from trader_arun.core.types import Ticker
from trader_arun.data.coindcx import CoinDCXProvider


def test_parse_ticker_basic():
    row = {
        "market": "B-BTC_USDT",
        "bid": "50000.00",
        "ask": "50001.00",
        "last_price": "50000.50",
        "timestamp": "1700000000000",
    }
    t = CoinDCXProvider._parse_ticker(row)
    assert t.venue == "coindcx"
    assert t.symbol == "B-BTC_USDT"
    assert t.base == "BTC"
    assert t.quote == "USDT"
    assert t.bid == 50000.0
    assert t.ask == 50001.0
    assert t.last == 50000.5
    assert t.mid == 50000.5
    assert t.spread_bps == pytest.approx(0.2, abs=0.05)
    assert t.timestamp == 1700000000.0  # ms → s


def test_parse_ticker_no_last():
    row = {
        "market": "B-ETH_USDT",
        "bid": "2000",
        "ask": "2001",
        # No last_price
        "timestamp": "1700000000000",
    }
    t = CoinDCXProvider._parse_ticker(row)
    assert t.last == 2000.5
    assert t.mid == 2000.5


def test_parse_ticker_invalid_market():
    row = {
        "market": "WEIRD",
        "bid": "1",
        "ask": "2",
        "last_price": "1.5",
    }
    t = CoinDCXProvider._parse_ticker(row)
    assert t.base == ""
    assert t.quote == ""


def test_parse_ticker_zero_bid_ask():
    row = {
        "market": "B-XRP_USDT",
        "bid": "0",
        "ask": "0",
        "last_price": "1.5",
    }
    t = CoinDCXProvider._parse_ticker(row)
    assert t.mid == 1.5
    assert t.spread_bps == 0.0
