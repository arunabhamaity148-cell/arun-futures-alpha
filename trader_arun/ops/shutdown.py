"""Shutdown manager — graceful, idempotent."""
from __future__ import annotations

import asyncio
import signal
from typing import Awaitable, Callable

from ..core.logger import get_logger

log = get_logger("shutdown")


class ShutdownManager:
    """Coordinates graceful shutdown across all components."""

    def __init__(self) -> None:
        self._stop_event = asyncio.Event()
        self._shutdown_hooks: list[Callable[[], Awaitable[None]]] = []
        self._signal_handlers_installed = False

    def install_signal_handlers(self) -> None:
        if self._signal_handlers_installed:
            return
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._handle_signal, sig)
            except (NotImplementedError, RuntimeError):
                # Windows / non-main-thread fallback.
                pass
        self._signal_handlers_installed = True

    def _handle_signal(self, sig) -> None:
        log.x_warn("shutdown signal received", extras={"signal": sig.name})
        self._stop_event.set()

    def request_shutdown(self) -> None:
        self._stop_event.set()

    @property
    def shutdown_requested(self) -> bool:
        return self._stop_event.is_set()

    async def wait_for_shutdown(self) -> None:
        await self._stop_event.wait()

    def add_hook(self, hook: Callable[[], Awaitable[None]]) -> None:
        self._shutdown_hooks.append(hook)

    async def execute_shutdown(self) -> None:
        log.x_info("shutdown starting", extras={"hooks": len(self._shutdown_hooks)})
        for hook in reversed(self._shutdown_hooks):
            try:
                await asyncio.wait_for(hook(), timeout=10.0)
            except asyncio.TimeoutError:
                log.x_warn("shutdown hook timed out", extras={"hook": hook.__name__ if hasattr(hook, '__name__') else '?'})
            except Exception as exc:  # pragma: no cover - defensive
                log.x_warn("shutdown hook error", extras={
                    "hook": hook.__name__ if hasattr(hook, '__name__') else '?',
                    "err": str(exc),
                })
        log.x_info("shutdown complete")
