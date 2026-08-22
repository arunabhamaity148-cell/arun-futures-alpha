"""Tests for Telegram publisher message formatting."""
import pytest

from trader_arun.core.types import Regime, Side, Signal, SignalGrade
from trader_arun.signals.publisher import format_signal_message


def _signal(**overrides) -> Signal:
    defaults = dict(
        signal_id="ARUN-TEST123",
        pair="BTC/USDT",
        coindcx_futures_symbol="BTCUSDT",
        coindcx_spot_symbol="B-BTC_USDT",
        side=Side.LONG,
        strategy="S2_LEAD_LAG_CONFIRM",
        regime=Regime.TREND_UP,
        entry_zone_low=49000.0, entry_zone_high=49100.0,
        stop_loss=48500.0, tp1=50000.0, tp2=51000.0, tp3=52000.0,
        rr=2.5, leverage_min=1.0, leverage_max=5.0,
        risk_pct=0.01, confidence=70.0, grade=SignalGrade.B,
        primary_alpha="lead/lag confirm (binance leads CoinDCX by 2m)",
        institutional_footprint=55.0, coindcx_match=85.0,
        transfer_score=82.0, liquidity_state="ADEQUATE",
        funding_context="binance +0.5bp/8h (z=+0.50, LONG)",
        oi_context="binance ΔOI +0.50% (z=+0.80)",
        news_state="ALLOW", portfolio_crowding=20.0,
        validity_window_sec=900.0, valid_until=9999999999.0,
        invalidation_condition="close < 48500",
    )
    defaults.update(overrides)
    return Signal(**defaults)


def test_format_long_signal():
    sig = _signal()
    msg = format_signal_message(sig)
    assert "ARUN" in msg
    assert "LONG" in msg
    assert "BTC/USDT" in msg
    assert "BTCUSDT" in msg
    assert "S2_LEAD_LAG_CONFIRM" in msg
    assert "48500" in msg
    assert "50000" in msg
    assert "ARUN-TEST123" in msg


def test_format_short_signal():
    sig = _signal(side=Side.SHORT)
    msg = format_signal_message(sig)
    assert "SHORT" in msg


def test_format_grade_a_signal():
    sig = _signal(grade=SignalGrade.A)
    msg = format_signal_message(sig)
    assert "A" in msg


def test_format_contains_all_required_fields():
    sig = _signal()
    msg = format_signal_message(sig)
    required = [
        "Pair", "CoinDCX Symbol", "Strategy", "Regime",
        "Entry Zone", "Stop Loss", "TP1", "TP2", "TP3", "R:R",
        "Leverage", "Risk", "Confidence", "CoinDCX Match",
        "Transfer Score", "Liquidity", "Funding", "OI",
        "News", "Portfolio Crowding", "Footprint", "Primary Alpha",
        "Validity", "Invalidation", "Signal ID",
    ]
    for field in required:
        assert field in msg, f"missing field: {field}"
