"""Tests for institutional footprint engine."""
import pytest

from trader_arun.core.config import PairConfig
from trader_arun.core.types import (
    Candle, OrderBookSnapshot, Ticker,
)
from trader_arun.data.manager import PairSnapshot
from trader_arun.derivatives.funding import FundingReport
from trader_arun.derivatives.open_interest import OIReport
from trader_arun.derivatives.liquidations import CascadeReport
from trader_arun.institutional.footprint import InstitutionalFootprintEngine
from trader_arun.core.types import Side


def _pair() -> PairConfig:
    return PairConfig(
        rank=4, base="DOGE", quote="USDT",
        coindcx_spot_symbol="B-DOGE_USDT",
        coindcx_futures_symbol="DOGEUSDT",
        binance_symbol="DOGEUSDT",
        hyperliquid_asset="DOGE", kraken_pair="XXDGZUSD",
        bybit_symbol="DOGEUSDT",
        primary_discovery="hyperliquid",
        best_strategy="S1/S3", primary_veto="V4",
    )


def test_low_footprint_with_quiet_market():
    snap = PairSnapshot(pair=_pair())
    snap.coindcx_ticker = Ticker(
        venue="coindcx", symbol="DOGEUSDT", base="DOGE", quote="USDT",
        bid=0.10, ask=0.10, last=0.10, mid=0.10, spread_bps=2.0,
        timestamp=1000.0, received_at=1000.0,
    )
    snap.coindcx_book = OrderBookSnapshot(
        venue="coindcx", symbol="DOGEUSDT",
        bids=[(0.099, 100000)], asks=[(0.101, 100000)],
        timestamp=1000.0, received_at=1000.0,
    )
    eng = InstitutionalFootprintEngine()
    result = eng.compute(snap, {})
    assert 0 <= result.score <= 100
    assert "large/informed participant activity proxy" in result.label


def test_high_footprint_with_cascade_and_funding():
    snap = PairSnapshot(pair=_pair())
    snap.coindcx_ticker = Ticker(
        venue="coindcx", symbol="DOGEUSDT", base="DOGE", quote="USDT",
        bid=0.10, ask=0.10, last=0.10, mid=0.10, spread_bps=2.0,
        timestamp=1000.0, received_at=1000.0,
    )
    snap.coindcx_book = OrderBookSnapshot(
        venue="coindcx", symbol="DOGEUSDT",
        bids=[(0.099, 1000000)], asks=[(0.101, 1000000)],
        timestamp=1000.0, received_at=1000.0,
    )
    analyser_state = {
        "funding_report": FundingReport(
            venue="hl", symbol="DOGEUSDT", rate_8h=0.001,
            annualised_pct=109.5, z_score=3.0, is_extreme=True, crowding_side="LONG",
        ),
        "oi_report": OIReport(
            venue="hl", symbol="DOGEUSDT", oi_usd=700_000_000,
            delta_usd=50_000_000, delta_pct=0.08, z_score=3.5, is_impulse=True,
        ),
        "cascade_report": CascadeReport(
            cascade_index=3.0, exhaustion_score=80.0, continuation_score=20.0,
            long_liq_6h_usd=10_000_000, short_liq_6h_usd=1_000_000,
            dominant_side=Side.LONG, is_exhausting=True,
        ),
        "absorption_result": type("A", (), {
            "score": 70.0, "cvd_z": -2.5, "price_move_bps": 1.0,
            "obi_top": 0.3, "direction": Side.LONG,
        })(),
        "cvd_calculator": type("C", (), {
            "buy_volume": 1_000_000, "sell_volume": 200_000,
            "total_volume": 1_200_000,
        })(),
        "obi_data": {"obi_top": 0.4},
    }
    eng = InstitutionalFootprintEngine()
    result = eng.compute(snap, analyser_state)
    assert result.score > 30.0
    assert result.subscores["long_crowding_score"] > 0
    assert result.subscores["liquidation_cascade_score"] > 0
