"""Tests for risk gate."""
import pytest

from trader_arun.core.types import RiskDecision
from trader_arun.risk.gate import RiskGate, RiskInputs


def _inputs(**kwargs):
    defaults = dict(
        pair="BTC",
        signal_confidence=70.0,
        edge_estimate_bps=50.0,
        volatility_z=0.5,
        spread_bps=2.0,
        spread_z=0.5,
        slippage_estimate_bps=5.0,
        book_depth_5pct_usd=1_000_000,
        funding_z=0.5,
        cascade_index=0.5,
        cross_exchange_deviation_bps=5.0,
        mismatch_score=15.0,
        news_action="ALLOW",
        data_fresh=True,
        stop_distance_atr=1.5,
        rr_ratio=2.0,
        portfolio_correlation_avg=0.3,
        directional_exposure=0.5,
        required_inputs_present=True,
        missing_inputs=[],
    )
    defaults.update(kwargs)
    return RiskInputs(**defaults)


def test_low_risk_signal_trades():
    gate = RiskGate()
    risk = gate.assess(_inputs())
    assert risk.decision == RiskDecision.TRADE
    assert risk.size_multiplier == 1.0


def test_high_risk_signal_no_trade():
    gate = RiskGate()
    risk = gate.assess(_inputs(
        volatility_z=4.0,
        spread_z=4.0,
        slippage_estimate_bps=40.0,  # 80% of edge
        book_depth_5pct_usd=100_000,
        cascade_index=3.0,
        cross_exchange_deviation_bps=50.0,
        mismatch_score=55.0,
        news_action="BLOCK",
        signal_confidence=30.0,
        rr_ratio=0.5,
    ))
    assert risk.decision == RiskDecision.NO_TRADE
    assert risk.size_multiplier == 0.0


def test_medium_risk_reduces_size():
    gate = RiskGate()
    risk = gate.assess(_inputs(
        volatility_z=2.5,
        spread_z=2.5,
        slippage_estimate_bps=20.0,
        book_depth_5pct_usd=200_000,
        cascade_index=1.5,
        cross_exchange_deviation_bps=25.0,
        mismatch_score=35.0,
    ))
    # Should be in REDUCED or WATCH.
    assert risk.decision in (RiskDecision.REDUCED_RISK, RiskDecision.WATCH)


def test_fail_closed_on_missing_inputs():
    gate = RiskGate()
    risk = gate.assess(_inputs(required_inputs_present=False, missing_inputs=["funding"]))
    assert risk.decision == RiskDecision.NO_TRADE


def test_fail_closed_on_stale_data():
    gate = RiskGate()
    risk = gate.assess(_inputs(data_fresh=False))
    assert risk.decision == RiskDecision.NO_TRADE


def test_news_block_forces_no_trade():
    gate = RiskGate()
    risk = gate.assess(_inputs(news_action="BLOCK"))
    assert risk.decision == RiskDecision.NO_TRADE
