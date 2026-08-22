"""Tests for veto engine."""
import pytest

from trader_arun.core.config import Config, PairConfig
from trader_arun.core.types import (
    FundingRate, NewsAction, NewsItem, NewsState, OpenInterest,
    OrderBookSnapshot, Regime, Side, Ticker, VetoSeverity,
)
from trader_arun.data.manager import PairSnapshot
from trader_arun.derivatives.funding import FundingReport
from trader_arun.derivatives.open_interest import OIReport
from trader_arun.derivatives.liquidations import CascadeReport
from trader_arun.newsguard.engine import NewsGuard
from trader_arun.vetoes.engine import VetoEngine
from trader_arun.vetoes.base import VetoContext


def _pair() -> PairConfig:
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


def _ticker(venue, mid, spread_bps=2.0) -> Ticker:
    spread = mid * spread_bps / 1e4
    return Ticker(
        venue=venue, symbol=f"{venue}BTC", base="BTC", quote="USDT",
        bid=mid - spread/2, ask=mid + spread/2, last=mid, mid=mid,
        spread_bps=spread_bps, timestamp=1000.0, received_at=1000.0,
    )


def _book(venue, mid, depth_usd=500_000) -> OrderBookSnapshot:
    n = depth_usd / 2 / mid
    return OrderBookSnapshot(venue=venue, symbol=f"{venue}BTCUSDT",
                             bids=[(mid*0.99, n)], asks=[(mid*1.01, n)],
                             timestamp=1000.0, received_at=1000.0)


def test_v1_no_veto_when_venues_agree():
    snap = PairSnapshot(pair=_pair())
    snap.coindcx_ticker = _ticker("coindcx", 100.0)
    snap.external_tickers["binance"] = _ticker("binance", 100.01)
    ctx = VetoContext(snap=snap, cfg=Config())
    engine = VetoEngine()
    result = engine.evaluate(ctx)
    # V1 should not trigger hard veto.
    v1 = [r for r in result.reports if r.veto_id == "V1"][0]
    assert not (v1.triggered and v1.severity == VetoSeverity.HARD)


def test_v1_hard_veto_when_coindcx_far_off():
    snap = PairSnapshot(pair=_pair())
    snap.coindcx_ticker = _ticker("coindcx", 100.0)
    snap.external_tickers["binance"] = _ticker("binance", 105.0)  # 500 bp dev
    ctx = VetoContext(snap=snap, cfg=Config())
    engine = VetoEngine()
    result = engine.evaluate(ctx)
    v1 = [r for r in result.reports if r.veto_id == "V1"][0]
    assert v1.triggered
    assert v1.severity == VetoSeverity.HARD
    assert result.hard_veto
    assert "V1" in result.hard_veto_ids


def test_v3_hard_veto_when_book_thin():
    snap = PairSnapshot(pair=_pair())
    snap.coindcx_ticker = _ticker("coindcx", 100.0, spread_bps=2.0)
    snap.coindcx_book = _book("coindcx", 100.0, depth_usd=10_000)  # thin
    snap.external_tickers["binance"] = _ticker("binance", 100.0)
    snap.external_books["binance"] = _book("binance", 100.0, depth_usd=2_000_000)
    ctx = VetoContext(snap=snap, cfg=Config())
    engine = VetoEngine()
    result = engine.evaluate(ctx)
    v3 = [r for r in result.reports if r.veto_id == "V3"][0]
    assert v3.triggered
    assert v3.severity == VetoSeverity.HARD


def test_v5_hard_veto_on_news_block():
    snap = PairSnapshot(pair=_pair())
    snap.coindcx_ticker = _ticker("coindcx", 100.0)
    snap.coindcx_book = _book("coindcx", 100.0)
    snap.external_tickers["binance"] = _ticker("binance", 100.0)
    snap.external_books["binance"] = _book("binance", 100.0)
    news_state = NewsState(
        action=NewsAction.BLOCK,
        blocking_items=[NewsItem(
            source="test", headline="FOMC rate decision",
            severity="CRITICAL", pair_tags=["*"], url="",
            published_at=1000.0, received_at=1000.0,
        )],
        reduce_items=[], cooldown_until=2000.0, timestamp=1000.0,
    )
    ctx = VetoContext(
        snap=snap, cfg=Config(),
        analyser_state={"news_state": news_state},
    )
    engine = VetoEngine()
    result = engine.evaluate(ctx)
    v5 = [r for r in result.reports if r.veto_id == "V5"][0]
    assert v5.triggered
    assert v5.severity == VetoSeverity.HARD


def test_v2_soft_when_persistent_contradiction():
    snap = PairSnapshot(pair=_pair())
    snap.coindcx_ticker = _ticker("coindcx", 100.0)
    snap.coindcx_book = _book("coindcx", 100.0)
    snap.external_tickers["binance"] = _ticker("binance", 100.0)
    snap.external_books["binance"] = _book("binance", 100.0)
    funding = FundingReport(
        venue="binance", symbol="BTCUSDT", rate_8h=0.001,
        annualised_pct=109.5, z_score=2.5, is_extreme=True, crowding_side="LONG",
    )
    oi = OIReport(
        venue="binance", symbol="BTCUSDT", oi_usd=1e9,
        delta_usd=-5e7, delta_pct=-0.05, z_score=-2.0, is_impulse=True,
    )
    ctx = VetoContext(
        snap=snap, cfg=Config(),
        analyser_state={
            "funding_report": funding,
            "oi_report": oi,
            "oi_funding_contradiction_persistence_sec": 7 * 3600,  # >6h
        },
    )
    engine = VetoEngine()
    result = engine.evaluate(ctx)
    v2 = [r for r in result.reports if r.veto_id == "V2"][0]
    assert v2.triggered
    assert v2.severity == VetoSeverity.HARD
