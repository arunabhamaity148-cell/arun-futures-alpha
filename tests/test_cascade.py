"""Tests for liquidation cascade analyser."""
import pytest

from trader_arun.core.types import Liquidation, Side
from trader_arun.derivatives.liquidations import LiquidationAnalyser


def test_no_cascade_when_no_events():
    la = LiquidationAnalyser(base="BTC")
    r = la.update([], now=1000.0)
    assert r.cascade_index == 0.0
    assert r.exhaustion_score == 0.0
    assert not r.is_exhausting


def test_cascade_index_increases_with_volume():
    la = LiquidationAnalyser(base="BTC")
    # Prime baseline with hourly events.
    base_ts = 1000.0
    # 30 days of small hourly events.
    for hour in range(720):
        for _ in range(5):
            la._events.append((base_ts - (720 - hour) * 3600, 1000.0, Side.LONG))
    # Now add a 6h cascade of large events.
    for i in range(50):
        la._events.append((base_ts - 60, 100_000.0, Side.LONG))
    r = la.update([], now=base_ts)
    assert r.cascade_index > 1.0
    assert r.long_liq_6h_usd > 0.0


def test_exhaustion_requires_deceleration():
    la = LiquidationAnalyser(base="BTC")
    base_ts = 1000.0
    # Prime baseline with hourly events EXCEPT for the most recent 3 hours
    # (so the cascade is clearly decelerating — no recent activity).
    for hour in range(3, 720):
        la._events.append((base_ts - hour * 3600, 1000.0, Side.LONG))
    # Cascade peaked 5h ago, no recent activity.
    for _ in range(100):
        la._events.append((base_ts - 5 * 3600, 50_000.0, Side.LONG))
    r = la.update([], now=base_ts)
    # With no recent events (last_1h_vol=0, prev_1h_vol=0), deceleration_ratio=0,
    # so exhaustion should be high.
    assert r.cascade_index > 1.0
    assert r.exhaustion_score > 0.0


def test_dominant_side():
    la = LiquidationAnalyser(base="BTC")
    base_ts = 1000.0
    # Prime baseline.
    for hour in range(720):
        la._events.append((base_ts - (720 - hour) * 3600, 1000.0, Side.LONG))
    # Add long-dominant liquidations.
    for _ in range(50):
        la._events.append((base_ts - 60, 100_000.0, Side.LONG))
    r = la.update([], now=base_ts)
    assert r.dominant_side == Side.LONG
