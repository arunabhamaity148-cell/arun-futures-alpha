"""Audit trail — persists signals, outcomes, veto/risk decisions to SQLite."""
from __future__ import annotations

import json
import time
from typing import Any

from ..core.logger import get_logger
from ..core.types import Signal

log = get_logger("audit")


class AuditTrail:
    """In-memory audit trail (persisted to SQLite by StorageEngine)."""

    def __init__(self, max_entries: int = 500) -> None:
        self._entries: list[dict[str, Any]] = []
        self._max = int(max_entries)

    def record(self, signal: Signal | None, audit: dict[str, Any]) -> None:
        entry = {
            "timestamp": time.time(),
            "signal_id": signal.signal_id if signal else None,
            "pair": audit.get("pair"),
            "rejected": signal is None,
            "audit": audit,
        }
        if signal is not None:
            entry["signal"] = signal.to_dict()
        self._entries.append(entry)
        if len(self._entries) > self._max:
            self._entries = self._entries[-self._max:]

    def record_event(self, event_type: str, payload: dict[str, Any]) -> None:
        self._entries.append({
            "timestamp": time.time(),
            "event": event_type,
            "payload": payload,
        })
        if len(self._entries) > self._max:
            self._entries = self._entries[-self._max:]

    def recent(self, n: int = 20) -> list[dict[str, Any]]:
        return list(self._entries[-n:])

    def snapshot(self) -> list[dict[str, Any]]:
        return list(self._entries)

    def clear(self) -> None:
        self._entries.clear()
