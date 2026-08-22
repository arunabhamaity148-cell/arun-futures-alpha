"""Safety latches — persistent kill switches.

Implements:
- daily-loss kill switch
- consecutive-loss latch
- extreme-volatility halt
- data-quality halt
- exchange-outage halt
- CoinDCX mismatch halt
- network-degraded mode
- manual pause

All latches survive restart via StorageEngine. Cleared only by explicit
operator /reset command.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from ..core.logger import get_logger
from ..core.types import RiskDecision

log = get_logger("safety")


@dataclass
class SafetyState:
    paused: bool = False
    muted: bool = False
    daily_loss_pct: float = 0.0
    daily_loss_kill_active: bool = False
    daily_loss_day: str = ""                # YYYY-MM-DD when reset
    consecutive_losses: int = 0
    consecutive_loss_latch_active: bool = False
    extreme_volatility_halt: bool = False
    data_quality_halt: bool = False
    exchange_outage_halt: bool = False
    coindcx_mismatch_halt: bool = False
    network_degraded: bool = False
    last_reset_ts: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)


class SafetyLatches:
    """Persistent safety latch manager."""

    def __init__(
        self,
        daily_loss_kill_pct: float = 0.03,
        consecutive_loss_latch: int = 3,
    ) -> None:
        self._state = SafetyState()
        self._daily_kill = float(daily_loss_kill_pct)
        self._consecutive_kill = int(consecutive_loss_latch)
        self._lock = asyncio.Lock()

    @property
    def state(self) -> SafetyState:
        return self._state

    def to_persist(self) -> dict[str, Any]:
        return {
            "paused": self._state.paused,
            "muted": self._state.muted,
            "daily_loss_pct": self._state.daily_loss_pct,
            "daily_loss_kill_active": self._state.daily_loss_kill_active,
            "daily_loss_day": self._state.daily_loss_day,
            "consecutive_losses": self._state.consecutive_losses,
            "consecutive_loss_latch_active": self._state.consecutive_loss_latch_active,
            "extreme_volatility_halt": self._state.extreme_volatility_halt,
            "data_quality_halt": self._state.data_quality_halt,
            "exchange_outage_halt": self._state.exchange_outage_halt,
            "coindcx_mismatch_halt": self._state.coindcx_mismatch_halt,
            "network_degraded": self._state.network_degraded,
            "last_reset_ts": self._state.last_reset_ts,
        }

    def load_from_persist(self, data: dict[str, Any]) -> None:
        for k, v in data.items():
            if hasattr(self._state, k):
                setattr(self._state, k, v)

    async def check_can_trade(self) -> tuple[bool, str]:
        """Return (allowed, reason)."""
        async with self._lock:
            if self._state.paused:
                return False, "manual pause active"
            if self._state.daily_loss_kill_active:
                return False, f"daily loss kill ({self._state.daily_loss_pct*100:.2f}%)"
            if self._state.consecutive_loss_latch_active:
                return False, f"consecutive loss latch ({self._state.consecutive_losses})"
            if self._state.extreme_volatility_halt:
                return False, "extreme volatility halt"
            if self._state.data_quality_halt:
                return False, "data quality halt"
            if self._state.exchange_outage_halt:
                return False, "exchange outage halt"
            if self._state.coindcx_mismatch_halt:
                return False, "CoinDCX mismatch halt"
            return True, "OK"

    async def record_outcome(self, pnl_pct: float) -> None:
        async with self._lock:
            # Update daily P/L — reset on day change.
            today = time.strftime("%Y-%m-%d", time.gmtime())
            if self._state.daily_loss_day != today:
                self._state.daily_loss_day = today
                self._state.daily_loss_pct = 0.0
                self._state.daily_loss_kill_active = False
            self._state.daily_loss_pct += pnl_pct
            if self._state.daily_loss_pct <= -abs(self._daily_kill):
                self._state.daily_loss_kill_active = True
                log.x_error("daily loss kill triggered", extras={
                    "daily_loss_pct": self._state.daily_loss_pct,
                })
            # Consecutive losses.
            if pnl_pct < 0:
                self._state.consecutive_losses += 1
                if self._state.consecutive_losses >= self._consecutive_kill:
                    self._state.consecutive_loss_latch_active = True
                    log.x_error("consecutive loss latch triggered", extras={
                        "count": self._state.consecutive_losses,
                    })
            elif pnl_pct > 0:
                self._state.consecutive_losses = 0

    async def set_extreme_volatility_halt(self, active: bool, reason: str = "") -> None:
        async with self._lock:
            if active != self._state.extreme_volatility_halt:
                log.x_warn("extreme vol halt toggled", extras={"active": active, "reason": reason})
            self._state.extreme_volatility_halt = active

    async def set_data_quality_halt(self, active: bool, reason: str = "") -> None:
        async with self._lock:
            if active != self._state.data_quality_halt:
                log.x_warn("data quality halt toggled", extras={"active": active, "reason": reason})
            self._state.data_quality_halt = active

    async def set_exchange_outage_halt(self, active: bool, reason: str = "") -> None:
        async with self._lock:
            if active != self._state.exchange_outage_halt:
                log.x_warn("exchange outage halt toggled", extras={"active": active, "reason": reason})
            self._state.exchange_outage_halt = active

    async def set_coindcx_mismatch_halt(self, active: bool, reason: str = "") -> None:
        async with self._lock:
            if active != self._state.coindcx_mismatch_halt:
                log.x_warn("coindcx mismatch halt toggled", extras={"active": active, "reason": reason})
            self._state.coindcx_mismatch_halt = active

    async def set_network_degraded(self, active: bool) -> None:
        async with self._lock:
            if active != self._state.network_degraded:
                log.x_warn("network degraded toggled", extras={"active": active})
            self._state.network_degraded = active

    async def pause(self) -> None:
        async with self._lock:
            self._state.paused = True
            log.x_warn("manual pause activated")

    async def resume(self) -> None:
        async with self._lock:
            self._state.paused = False
            log.x_info("manual pause cleared")

    async def mute(self) -> None:
        async with self._lock:
            self._state.muted = True

    async def unmute(self) -> None:
        async with self._lock:
            self._state.muted = False

    async def reset(self) -> None:
        async with self._lock:
            self._state = SafetyState(last_reset_ts=time.time())
            log.x_warn("safety state RESET by operator")

    async def is_muted(self) -> bool:
        return self._state.muted
