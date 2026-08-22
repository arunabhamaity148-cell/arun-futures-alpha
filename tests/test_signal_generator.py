"""Tests for alpha engine + signal generator end-to-end."""
import time

import pytest

from trader_arun.core.config import Config, PairConfig
from trader_arun.core.types import (
    Candle, FundingRate, OpenInterest, OrderBookSnapshot, Side, Ticker, Trade,
)
from trader_arun.data.manager import PairSnapshot
from trader_arun.alpha.engine import AlphaEngine
from trader_arun.alpha.s1_cascade import S1CascadeExhaustion
from trader_arun.alpha.s3_funding_oi import S3FundingOIUnwind
from trader_arun.derivatives.funding import FundingAnalyser, FundingReport
from trader_arun.derivatives.open_interest import OpenInterestAnalyser, OIReport
from trader_arun.derivatives.liquidations import CascadeReport
from trader_arun.newsguard.engine import NewsGuard
from trader_arun.portfolio.crowding import PortfolioCrowdingEngine
from trader_arun.signals.generator import SignalGenerator


def _pair() -> PairConfig:
    return PairConfig(
        rank=4, base="DOGE", quote="USDT",
        coindcx_spot_symbol="B-DOGE_USDT",
        coindcx_futures_symbol="DOGEUSDT",
        binance_symbol="DOGEUSDT",
        hyperliquid_asset="DOGE",
        kraken_pair="XXDGZUSD",
        bybit_symbol="DOGEUSDT",
        primary_discovery="hyperliquid",
        best_strategy="S1/S3", primary_veto="V4",
    )


def _make_candles(n=60, base=0.10) -> list[Candle]:
    candles = []
    for i in range(n):
        candles.append(Candle(
            venue="coindcx", symbol="DOGEUSDT", tf="1m",
            open=base, high=base*1.001, low=base*0.999, close=base,
            volume=1_000_000,
            open_time=1000 + i * 60, close_time=1060 + i * 60,
        ))
    return candles


def test_alpha_engine_returns_no_signal_when_no_data():
    snap = PairSnapshot(pair=_pair())
    engine = AlphaEngine()
    result = engine.evaluate(snap, {})
    assert result.best_signal is None


def test_s1_no_signal_without_cascade():
    snap = PairSnapshot(pair=_pair())
    snap.coindcx_ticker = Ticker(
        venue="coindcx", symbol="DOGEUSDT", base="DOGE", quote="USDT",
        bid=0.10, ask=0.10, last=0.10, mid=0.10, spread_bps=2.0,
        timestamp=time.time(), received_at=time.time(),
    )
    snap.coindcx_candles = _make_candles()
    s1 = S1CascadeExhaustion()
    result = s1.evaluate(snap, {"cascade_report": CascadeReport(
        cascade_index=0.5, exhaustion_score=0.0, continuation_score=10.0,
        long_liq_6h_usd=0.0, short_liq_6h_usd=0.0,
        dominant_side=Side.LONG, is_exhausting=False,
    )})
    assert result.side == Side.FLAT
    assert result.confidence == 0.0


def test_s1_signal_when_cascade_exhausting():
    snap = PairSnapshot(pair=_pair())
    snap.coindcx_ticker = Ticker(
        venue="coindcx", symbol="DOGEUSDT", base="DOGE", quote="USDT",
        bid=0.10, ask=0.10, last=0.10, mid=0.10, spread_bps=2.0,
        timestamp=time.time(), received_at=time.time(),
    )
    snap.coindcx_candles = _make_candles(n=60)
    s1 = S1CascadeExhaustion()
    result = s1.evaluate(snap, {"cascade_report": CascadeReport(
        cascade_index=2.5, exhaustion_score=75.0, continuation_score=20.0,
        long_liq_6h_usd=5_000_000, short_liq_6h_usd=500_000,
        dominant_side=Side.LONG, is_exhausting=True,
    )})
    assert result.side == Side.LONG
    assert result.confidence >= 70.0


def test_s3_signal_when_funding_oi_unwind():
    snap = PairSnapshot(pair=_pair())
    snap.coindcx_ticker = Ticker(
        venue="coindcx", symbol="DOGEUSDT", base="DOGE", quote="USDT",
        bid=0.10, ask=0.10, last=0.10, mid=0.10, spread_bps=2.0,
        timestamp=time.time(), received_at=time.time(),
    )
    snap.coindcx_candles = _make_candles(n=30)
    # Simulate declining price.
    for i, c in enumerate(snap.coindcx_candles[-5:]):
        snap.coindcx_candles[-5 + i] = Candle(
            venue=c.venue, symbol=c.symbol, tf=c.tf,
            open=c.open * (1 - 0.001 * (i+1)),
            high=c.high * (1 - 0.001 * (i+1)),
            low=c.low * (1 - 0.001 * (i+1)),
            close=c.close * (1 - 0.001 * (i+1)),
            volume=c.volume, open_time=c.open_time, close_time=c.close_time,
        )
    s3 = S3FundingOIUnwind()
    funding = FundingReport(
        venue="hl", symbol="DOGEUSDT", rate_8h=0.001,
        annualised_pct=109.5, z_score=2.5, is_extreme=True, crowding_side="LONG",
    )
    oi = OIReport(
        venue="hl", symbol="DOGEUSDT", oi_usd=700_000_000,
        delta_usd=-10_000_000, delta_pct=-0.02, z_score=-2.5, is_impulse=True,
    )
    result = s3.evaluate(snap, {"funding_report": funding, "oi_report": oi})
    assert result.side == Side.SHORT
    assert result.confidence >= 50.0


def test_signal_generator_fail_closed_when_unverified():
    cfg = Config()
    news = NewsGuard()
    portfolio = PortfolioCrowdingEngine()
    gen = SignalGenerator(cfg, news, portfolio, coindcx_futures_verified=False)
    snap = PairSnapshot(pair=_pair())
    snap.coindcx_ticker = Ticker(
        venue="coindcx", symbol="DOGEUSDT", base="DOGE", quote="USDT",
        bid=0.10, ask=0.10, last=0.10, mid=0.10, spread_bps=2.0,
        timestamp=time.time(), received_at=time.time(),
    )
    snap.coindcx_candles = _make_candles()
    snap.coindcx_book = OrderBookSnapshot(
        venue="coindcx", symbol="DOGEUSDT",
        bids=[(0.099, 100000)], asks=[(0.101, 100000)],
        timestamp=time.time(), received_at=time.time(),
    )
    result = gen.generate(snap)
    assert result.signal is None
    assert "NOT VERIFIED" in result.audit.get("reject", "")
