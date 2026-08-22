"""Operator state + Telegram command handler.

Commands (research):
  /status   — overall bot status
  /paused   — show pause state
  /pause    — pause new signals
  /resume   — resume new signals
  /mute     — mute Telegram signal output (commands still work)
  /unmute   — unmute signal output
  /reset    — reset all safety latches
  /health   — provider health snapshot
  /signals  — recent signals
  /risk     — current risk gate state
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from ..core.logger import get_logger
from ..core.types import Signal
from .safety import SafetyLatches

log = get_logger("operator")


@dataclass
class OperatorState:
    """Shared mutable operator state."""
    paused: bool = False
    muted: bool = False
    started_at: float = field(default_factory=time.time)
    last_signal: Signal | None = None
    signal_count: int = 0
    reject_count: int = 0


class OperatorCommandHandler:
    """Handles Telegram /commands. Modifies the same shared state used by the engine."""

    def __init__(
        self,
        operator_state: OperatorState,
        safety: SafetyLatches,
        get_recent_signals: Callable[[], list[Signal]] | None = None,
        get_health: Callable[[], list[dict]] | None = None,
    ) -> None:
        self._state = operator_state
        self._safety = safety
        self._get_recent_signals = get_recent_signals or (lambda: [])
        self._get_health = get_health or (lambda: [])
        self._whitelist: set[str] = set()

    def set_whitelist(self, user_ids: list[str]) -> None:
        self._whitelist = {str(u) for u in user_ids}

    def is_authorized(self, user_id: str | int) -> bool:
        if not self._whitelist:
            return True  # no whitelist = allow all (development mode)
        return str(user_id) in self._whitelist

    async def handle(self, command: str, user_id: str | int = "0") -> str:
        if not self.is_authorized(user_id):
            return f"⛔ Unauthorized: {user_id}"
        cmd = command.strip().lower().split()[0] if command else ""
        if cmd in ("/status", "/state"):
            return await self._status()
        if cmd == "/paused":
            return f"Paused: {self._state.paused}"
        if cmd == "/pause":
            await self._safety.pause()
            self._state.paused = True
            return "🛑 ARUN paused. New signals suppressed."
        if cmd == "/resume":
            await self._safety.resume()
            self._state.paused = False
            return "✅ ARUN resumed. New signals active."
        if cmd == "/mute":
            await self._safety.mute()
            self._state.muted = True
            return "🔇 Signal output muted."
        if cmd == "/unmute":
            await self._safety.unmute()
            self._state.muted = False
            return "🔊 Signal output unmuted."
        if cmd == "/reset":
            await self._safety.reset()
            self._state.paused = False
            self._state.muted = False
            return "🔄 All safety latches reset."
        if cmd == "/health":
            return await self._health()
        if cmd == "/signals":
            return self._signals_text()
        if cmd == "/risk":
            return "Risk gate: see /status for current risk score."
        if cmd in ("/help", "/start"):
            return (
                "━━━ ARUN কমান্ড তালিকা ━━━\n"
                "📊 /status — বটের সম্পূর্ণ স্ট্যাটাস\n"
                "⏸️ /paused — পজ অবস্থা দেখাও\n"
                "🛑 /pause — নতুন সিগন্যাল বন্ধ করো\n"
                "✅ /resume — নতুন সিগন্যাল চালু করো\n"
                "🔇 /mute — সিগন্যাল আউটপুট বন্ধ\n"
                "🔊 /unmute — সিগন্যাল আউটপুট চালু\n"
                "🔄 /reset — সব সেফটি ল্যাচ রিসেট\n"
                "🏥 /health — প্রোভাইডার হেলথ\n"
                "📈 /signals — সাম্প্রতিক ৫টি সিগন্যাল\n"
                "⚠️ /risk — রিস্ক গেট অবস্থা"
            )
        return f"Unknown command: {command}"

    async def _status(self) -> str:
        s = self._state
        uptime = time.time() - s.started_at
        can_trade, reason = await self._safety.check_can_trade()
        lines = [
            f"━━━ 📊 ARUN স্ট্যাটাস ━━━",
            f"⏱️ Uptime: {int(uptime//3600)}ঘ {int(uptime%3600//60)}মি",
            f"⏸️ Paused: {s.paused}",
            f"🔇 Muted: {s.muted}",
            f"📈 Signals: {s.signal_count}",
            f"❌ Rejects: {s.reject_count}",
            f"✅ Can trade: {can_trade}",
            f"📝 Reason: {reason}",
        ]
        return "\n".join(lines)

    async def _health(self) -> str:
        health = self._get_health()
        if not health:
            return "কোনো প্রোভাইডার হেলথ ডেটা নেই।"
        lines = ["━━━ 🏥 প্রোভাইডার হেলথ ━━━"]
        for h in health:
            lines.append(
                f"{h.get('name', '?')}: {h.get('state', '?')} | "
                f"p95={h.get('latency_p95_sec', 0):.3f}s | "
                f"fail={h.get('failures_in_window', 0)}"
            )
        return "\n".join(lines)

    def _signals_text(self) -> str:
        recent = self._get_recent_signals()
        if not recent:
            return "কোনো সাম্প্রতিক সিগন্যাল নেই।"
        lines = ["━━━ 📈 সাম্প্রতিক সিগন্যাল ━━━"]
        for sig in recent[-5:]:
            lines.append(
                f"{sig.signal_id} {sig.pair} {sig.side.value} "
                f"{sig.grade.value} conf={sig.confidence:.0f}"
            )
        return "\n".join(lines)
