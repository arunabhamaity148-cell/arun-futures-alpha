"""Telegram publisher — premium ARUN-formatted signal messages."""
from __future__ import annotations

import asyncio
import time
from typing import Any

import aiohttp

from ..core.exceptions import ARUNError
from ..core.logger import get_logger
from ..core.types import Signal, SignalGrade

log = get_logger("telegram")


# Command list shown in Telegram's command autocomplete menu.
TELEGRAM_COMMANDS: list[dict[str, str]] = [
    {"command": "status", "description": "📊 বটের সম্পূর্ণ স্ট্যাটাস (uptime, signals, rejects)"},
    {"command": "paused", "description": "⏸️ পজ অবস্থা দেখাও"},
    {"command": "pause", "description": "🛑 নতুন সিগন্যাল বন্ধ করো"},
    {"command": "resume", "description": "✅ নতুন সিগন্যাল চালু করো"},
    {"command": "mute", "description": "🔇 টেলিগ্রামে সিগন্যাল আউটপুট বন্ধ করো"},
    {"command": "unmute", "description": "🔊 টেলিগ্রামে সিগন্যাল আউটপুট চালু করো"},
    {"command": "reset", "description": "🔄 সব সেফটি ল্যাচ রিসেট করো"},
    {"command": "health", "description": "🏥 প্রোভাইডার হেলথ রিপোর্ট"},
    {"command": "signals", "description": "📈 সাম্প্রতিক ৫টি সিগন্যাল"},
    {"command": "risk", "description": "⚠️ বর্তমান রিস্ক গেট অবস্থা"},
    {"command": "help", "description": "❓ সাহায্য ও কমান্ড তালিকা"},
]


def format_signal_message(sig: Signal) -> str:
    """Format a Signal as a professional Telegram message."""
    arrow = "🟢 LONG" if sig.side.value == "LONG" else "🔴 SHORT"
    if sig.grade == SignalGrade.A:
        grade_badge = "A ★"
    elif sig.grade == SignalGrade.B:
        grade_badge = "B"
    else:
        grade_badge = "C"

    lines = [
        f"━━━━━━━━━━━━━━━━━━━━━━",
        f"  {sig.brand} · {arrow} · {sig.grade.value}",
        f"━━━━━━━━━━━━━━━━━━━━━━",
        f"Pair: {sig.pair}",
        f"CoinDCX Symbol: `{sig.coindcx_futures_symbol}`",
        f"Strategy: {sig.strategy}",
        f"Regime: {sig.regime.value}",
        f"",
        f"Entry Zone: {sig.entry_zone_low:.4f} – {sig.entry_zone_high:.4f}",
        f"Stop Loss: {sig.stop_loss:.4f}",
        f"TP1: {sig.tp1:.4f}",
        f"TP2: {sig.tp2:.4f}",
        f"TP3: {sig.tp3:.4f}",
        f"R:R: {sig.rr:.2f}",
        f"Leverage: {sig.leverage_min:.0f}x–{sig.leverage_max:.0f}x",
        f"Risk: {sig.risk_pct*100:.2f}% of equity",
        f"",
        f"Confidence: {sig.confidence:.0f}/100",
        f"CoinDCX Match: {sig.coindcx_match:.0f}/100",
        f"Transfer Score: {sig.transfer_score:.0f}/100",
        f"Liquidity: {sig.liquidity_state}",
        f"Funding: {sig.funding_context}",
        f"OI: {sig.oi_context}",
        f"News: {sig.news_state}",
        f"Portfolio Crowding: {sig.portfolio_crowding:.0f}/100",
        f"Footprint Proxy: {sig.institutional_footprint:.0f}/100",
        f"",
        f"Primary Alpha: {sig.primary_alpha}",
        f"Validity: {int(sig.validity_window_sec//60)} min from issue",
        f"Invalidation: {sig.invalidation_condition}",
        f"Signal ID: `{sig.signal_id}`",
        f"━━━━━━━━━━━━━━━━━━━━━━",
    ]
    return "\n".join(lines)


class TelegramPublisher:
    """Send signals via Telegram Bot API. Fail-safe — never blocks engine."""

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        session: aiohttp.ClientSession | None = None,
        timeout_sec: float = 8.0,
    ) -> None:
        self._token = bot_token
        self._chat_id = chat_id
        self._session = session
        self._timeout = aiohttp.ClientTimeout(total=timeout_sec)
        self._owns_session = session is None
        self._enabled = bool(bot_token and chat_id)
        self._commands_registered = False
        if not self._enabled:
            log.x_warn("telegram publisher disabled (missing token/chat_id)")

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self._session

    async def register_commands(self) -> bool:
        """Register the command menu shown in Telegram's autocomplete.

        Safe to call multiple times — Telegram dedupes.
        """
        if not self._enabled or self._commands_registered:
            return False
        session = await self._ensure_session()
        url = f"https://api.telegram.org/bot{self._token}/setMyCommands"
        try:
            async with session.post(url, json={"commands": TELEGRAM_COMMANDS}) as resp:
                if resp.status == 200:
                    self._commands_registered = True
                    log.x_info("telegram commands registered", extras={
                        "count": len(TELEGRAM_COMMANDS),
                    })
                    return True
                body = await resp.text()
                log.x_warn("telegram setMyCommands failed", extras={
                    "status": resp.status, "body": body[:200],
                })
                return False
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            log.x_warn("telegram setMyCommands network error", extras={"err": str(exc)})
            return False

    async def publish_signal(self, sig: Signal) -> bool:
        if not self._enabled:
            log.x_info("signal suppressed (telegram disabled)", extras={
                "signal_id": sig.signal_id, "pair": sig.pair,
            })
            return False
        text = format_signal_message(sig)
        return await self._send_message(text)

    async def publish_text(self, text: str) -> bool:
        if not self._enabled:
            return False
        return await self._send_message(text)

    async def _send_message(self, text: str) -> bool:
        session = await self._ensure_session()
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        try:
            async with session.post(
                url,
                json={
                    "chat_id": self._chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                },
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    log.x_warn("telegram send failed", extras={
                        "status": resp.status, "body": body[:200],
                    })
                    return False
                return True
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            log.x_warn("telegram network error", extras={"err": str(exc)})
            return False

    async def close(self) -> None:
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    @property
    def enabled(self) -> bool:
        return self._enabled

