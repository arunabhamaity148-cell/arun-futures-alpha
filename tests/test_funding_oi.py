"""Tests for funding + OI analysers."""
import pytest

from trader_arun.core.types import FundingRate, OpenInterest
from trader_arun.derivatives.funding import FundingAnalyser
from trader_arun.derivatives.open_interest import OpenInterestAnalyser


def _funding(rate, ts=1000.0):
    return FundingRate(venue="hyperliquid", symbol="BTCUSDT", rate=rate,
                       next_funding_time=ts + 28800, timestamp=ts)


def _oi(usd, ts=1000.0):
    return OpenInterest(venue="hyperliquid", symbol="BTCUSDT",
                        oi_base=usd/100, oi_usd=usd, timestamp=ts)


def test_funding_baseline_then_extreme():
    fa = FundingAnalyser(venue="hyperliquid", symbol="BTCUSDT", baseline_samples=20)
    # Baseline funding around 0.0001
    for _ in range(20):
        fa.update(_funding(0.0001))
    # Now an extreme value
    rep = fa.update(_funding(0.001))  # 10x baseline
    assert rep.is_extreme
    assert rep.crowding_side == "LONG"


def test_funding_short_crowding():
    fa = FundingAnalyser(venue="hl", symbol="BTCUSDT", baseline_samples=20)
    for _ in range(20):
        fa.update(_funding(-0.0001))
    rep = fa.update(_funding(-0.001))
    assert rep.is_extreme
    assert rep.crowding_side == "SHORT"


def test_funding_neutral_when_small():
    fa = FundingAnalyser(venue="hl", symbol="BTCUSDT", baseline_samples=20)
    for _ in range(20):
        fa.update(_funding(0.00005))
    rep = fa.update(_funding(0.00006))
    assert rep.crowding_side == "NEUTRAL"


def test_oi_impulse_detection():
    oa = OpenInterestAnalyser(venue="hl", symbol="BTCUSDT", baseline_samples=20)
    # Baseline OI around 100M
    for _ in range(20):
        oa.update(_oi(100_000_000))
    # Sudden 10% jump
    rep = oa.update(_oi(110_000_000))
    assert rep.delta_pct > 0.05
    assert rep.is_impulse


def test_oi_no_impulse_when_steady():
    oa = OpenInterestAnalyser(venue="hl", symbol="BTCUSDT", baseline_samples=20)
    # Use slightly varied baseline so std > 0.
    rng = [100_000_000, 100_500_000, 99_800_000, 100_200_000, 100_100_000,
           99_900_000, 100_300_000, 100_050_000, 99_950_000, 100_400_000,
           99_700_000, 100_600_000, 100_150_000, 99_850_000, 100_250_000,
           100_350_000, 99_750_000, 100_550_000, 100_450_000, 99_650_000]
    for v in rng:
        oa.update(_oi(v))
    # 0.5% change → within baseline variance → not an impulse.
    rep = oa.update(_oi(100_500_000))
    assert not rep.is_impulse
