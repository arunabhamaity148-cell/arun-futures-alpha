"""Tests for operator commands."""
import pytest

from trader_arun.core.types import Signal, SignalGrade, Side
from trader_arun.ops.operator import OperatorCommandHandler, OperatorState
from trader_arun.ops.safety import SafetyLatches


@pytest.fixture
def handler():
    state = OperatorState()
    safety = SafetyLatches()
    return OperatorCommandHandler(
        operator_state=state, safety=safety,
        get_recent_signals=lambda: [], get_health=lambda: [],
    )


@pytest.mark.asyncio
async def test_status_command(handler):
    resp = await handler.handle("/status")
    assert "ARUN" in resp
    assert "Uptime" in resp or "uptime" in resp.lower()


@pytest.mark.asyncio
async def test_pause_resume_cycle(handler):
    pause_resp = await handler.handle("/pause")
    assert "paused" in pause_resp.lower() or "বন্ধ" in pause_resp
    assert handler._state.paused is True
    resume_resp = await handler.handle("/resume")
    assert "resumed" in resume_resp.lower() or "চালু" in resume_resp
    assert handler._state.paused is False


@pytest.mark.asyncio
async def test_mute_unmute(handler):
    await handler.handle("/mute")
    assert handler._state.muted is True
    await handler.handle("/unmute")
    assert handler._state.muted is False


@pytest.mark.asyncio
async def test_reset(handler):
    await handler.handle("/pause")
    await handler.handle("/mute")
    await handler.handle("/reset")
    assert handler._state.paused is False
    assert handler._state.muted is False


@pytest.mark.asyncio
async def test_health_no_data(handler):
    resp = await handler.handle("/health")
    # Bengali or English empty-state message.
    assert "নেই" in resp or "No" in resp or "no" in resp


@pytest.mark.asyncio
async def test_unknown_command(handler):
    resp = await handler.handle("/foobar")
    assert "Unknown" in resp


@pytest.mark.asyncio
async def test_authorization_enforced():
    state = OperatorState()
    safety = SafetyLatches()
    handler = OperatorCommandHandler(state, safety)
    handler.set_whitelist(["12345"])
    # Unauthorized.
    resp = await handler.handle("/pause", user_id="99999")
    assert "Unauthorized" in resp
    # Authorized.
    resp = await handler.handle("/pause", user_id="12345")
    assert "paused" in resp.lower() or "বন্ধ" in resp


@pytest.mark.asyncio
async def test_signals_empty(handler):
    resp = await handler.handle("/signals")
    assert "নেই" in resp or "No recent" in resp
