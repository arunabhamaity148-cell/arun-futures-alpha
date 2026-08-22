"""Tests for shutdown manager."""
import asyncio

import pytest

from trader_arun.ops.shutdown import ShutdownManager


@pytest.mark.asyncio
async def test_shutdown_initial_state():
    sm = ShutdownManager()
    assert not sm.shutdown_requested


@pytest.mark.asyncio
async def test_request_shutdown_sets_event():
    sm = ShutdownManager()
    sm.request_shutdown()
    assert sm.shutdown_requested


@pytest.mark.asyncio
async def test_hooks_called_in_reverse_order():
    sm = ShutdownManager()
    order: list[str] = []
    async def h1():
        order.append("h1")
    async def h2():
        order.append("h2")
    async def h3():
        order.append("h3")
    sm.add_hook(h1)
    sm.add_hook(h2)
    sm.add_hook(h3)
    await sm.execute_shutdown()
    # Reverse order: h3, h2, h1
    assert order == ["h3", "h2", "h1"]


@pytest.mark.asyncio
async def test_hook_timeout_does_not_block_others():
    sm = ShutdownManager()
    called: list[bool] = []
    async def slow_hook():
        await asyncio.sleep(100)  # will time out
    async def fast_hook():
        called.append(True)
    sm.add_hook(slow_hook)
    sm.add_hook(fast_hook)
    await sm.execute_shutdown()
    assert called == [True]


@pytest.mark.asyncio
async def test_hook_exception_does_not_block_others():
    sm = ShutdownManager()
    called: list[bool] = []
    async def bad_hook():
        raise RuntimeError("boom")
    async def good_hook():
        called.append(True)
    sm.add_hook(bad_hook)
    sm.add_hook(good_hook)
    await sm.execute_shutdown()
    assert called == [True]
