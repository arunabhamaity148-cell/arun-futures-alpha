"""Tests for position sizing."""
import pytest

from trader_arun.risk.sizing import PositionSizer


def test_basic_sizing():
    s = PositionSizer(equity_usd=10_000, risk_pct=0.01, max_leverage=10.0)
    # Risk $100, stop is 1% away → size = $100/0.01 = $10,000.
    result = s.size(
        entry_price=100.0, stop_price=99.0,
        book_depth_5pct_usd=1_000_000,
    )
    assert result.size_usd == pytest.approx(10_000.0, rel=0.01)
    assert result.leverage == pytest.approx(1.0, rel=0.01)


def test_size_capped_by_max_leverage():
    s = PositionSizer(equity_usd=1_000, risk_pct=0.05, max_leverage=2.0)
    # Risk $50, stop 0.1% → size would be $50,000 — but cap is 2×$1,000 = $2,000.
    result = s.size(
        entry_price=100.0, stop_price=99.9,
        book_depth_5pct_usd=1_000_000,
    )
    assert result.size_usd <= 2_000.0
    assert result.clipped


def test_size_capped_by_book_depth():
    s = PositionSizer(equity_usd=100_000, risk_pct=0.05, max_leverage=50.0)
    result = s.size(
        entry_price=100.0, stop_price=99.0,
        book_depth_5pct_usd=10_000,  # very thin book
    )
    # Should cap at 5% of $10k = $500.
    assert result.size_usd <= 600.0
    assert result.clipped


def test_zero_multiplier_returns_zero():
    s = PositionSizer()
    result = s.size(
        entry_price=100.0, stop_price=99.0,
        book_depth_5pct_usd=1_000_000,
        size_multiplier=0.0,
    )
    assert result.size_usd == 0.0


def test_invalid_prices_return_zero():
    s = PositionSizer()
    result = s.size(
        entry_price=0.0, stop_price=99.0,
        book_depth_5pct_usd=1_000_000,
    )
    assert result.size_usd == 0.0
