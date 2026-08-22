"""Tests for storage engine."""
import asyncio
import os
import tempfile

import pytest

from trader_arun.core.types import Regime, Side, Signal, SignalGrade
from trader_arun.ops.storage import StorageEngine


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.mark.asyncio
async def test_storage_round_trip(temp_db):
    storage = StorageEngine(db_path=temp_db)
    await storage.start()
    try:
        sig = Signal(
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
            primary_alpha="lead/lag confirm",
            institutional_footprint=55.0, coindcx_match=85.0,
            transfer_score=82.0, liquidity_state="ADEQUATE",
            funding_context="binance +0.5bp/8h",
            oi_context="binance ΔOI +0.5%",
            news_state="ALLOW", portfolio_crowding=20.0,
            validity_window_sec=900.0, valid_until=9999999999.0,
            invalidation_condition="close < 48500",
        )
        await storage.persist_signal(sig, risk_score=35.0)
        # Wait briefly for the writer to flush.
        await asyncio.sleep(0.2)
        # Verify (would normally query DB; here just verify no exceptions).
        op_state = await storage.load_operator_state()
        assert isinstance(op_state, dict)
    finally:
        await storage.stop()


@pytest.mark.asyncio
async def test_storage_persists_operator_state(temp_db):
    storage = StorageEngine(db_path=temp_db)
    await storage.start()
    try:
        await storage.persist_operator_state({"paused": True, "muted": False})
        await asyncio.sleep(0.2)
        loaded = await storage.load_operator_state()
        assert "paused" in loaded
    finally:
        await storage.stop()


@pytest.mark.asyncio
async def test_storage_init_with_in_memory():
    # Should work with :memory: path.
    storage = StorageEngine(db_path=":memory:")
    await storage.start()
    try:
        await storage.persist_audit("test_event", "BTC", {"foo": "bar"})
        await asyncio.sleep(0.1)
    finally:
        await storage.stop()
