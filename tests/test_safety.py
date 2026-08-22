"""Tests for safety latches."""
import asyncio
import time

import pytest

from trader_arun.ops.safety import SafetyLatches


@pytest.mark.asyncio
async def test_clean_state_allows_trade():
    s = SafetyLatches()
    allowed, reason = await s.check_can_trade()
    assert allowed
    assert reason == "OK"


@pytest.mark.asyncio
async def test_pause_blocks_trade():
    s = SafetyLatches()
    await s.pause()
    allowed, reason = await s.check_can_trade()
    assert not allowed
    assert "pause" in reason.lower()


@pytest.mark.asyncio
async def test_resume_clears_pause():
    s = SafetyLatches()
    await s.pause()
    await s.resume()
    allowed, _ = await s.check_can_trade()
    assert allowed


@pytest.mark.asyncio
async def test_daily_loss_kill_triggers():
    s = SafetyLatches(daily_loss_kill_pct=0.03)
    await s.record_outcome(-0.04)  # -4% loss
    allowed, reason = await s.check_can_trade()
    assert not allowed
    assert "daily loss" in reason.lower()


@pytest.mark.asyncio
async def test_consecutive_loss_latch():
    s = SafetyLatches(consecutive_loss_latch=3, daily_loss_kill_pct=0.10)
    await s.record_outcome(-0.01)
    await s.record_outcome(-0.01)
    # Not yet latched at 2.
    allowed, _ = await s.check_can_trade()
    assert allowed
    await s.record_outcome(-0.01)  # 3rd consecutive
    allowed, reason = await s.check_can_trade()
    assert not allowed
    assert "consecutive" in reason.lower()


@pytest.mark.asyncio
async def test_win_resets_consecutive_count():
    s = SafetyLatches(consecutive_loss_latch=3)
    await s.record_outcome(-0.01)
    await s.record_outcome(-0.01)
    await s.record_outcome(0.005)  # win resets
    assert s.state.consecutive_losses == 0


@pytest.mark.asyncio
async def test_reset_clears_all():
    s = SafetyLatches()
    await s.pause()
    await s.record_outcome(-0.05)
    await s.set_data_quality_halt(True)
    await s.reset()
    allowed, _ = await s.check_can_trade()
    assert allowed


@pytest.mark.asyncio
async def test_mute_independent_of_trade():
    s = SafetyLatches()
    await s.mute()
    assert await s.is_muted()
    # Trade still allowed (mute is just for Telegram output).
    allowed, _ = await s.check_can_trade()
    assert allowed


@pytest.mark.asyncio
async def test_persist_round_trip():
    s = SafetyLatches(daily_loss_kill_pct=0.05)
    await s.pause()
    await s.record_outcome(-0.06)
    persisted = s.to_persist()
    s2 = SafetyLatches(daily_loss_kill_pct=0.05)
    s2.load_from_persist(persisted)
    assert s2.state.paused is True
    assert s2.state.daily_loss_kill_active is True
