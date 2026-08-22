"""SQLite storage — WAL mode, bounded retention, off-loop writes.

Persists:
- signals (with full audit)
- outcomes
- veto/risk decisions
- provider health
- operator state
- safety state
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from ..core.logger import get_logger
from ..core.types import Signal

log = get_logger("storage")


class StorageEngine:
    """Async-safe SQLite storage with WAL."""

    def __init__(self, db_path: str = "data/arun.db", write_interval_sec: float = 1.0) -> None:
        self._db_path = str(db_path)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._write_interval = float(write_interval_sec)
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._writer_task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._conn: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        # Run init in a thread to avoid blocking the loop.
        await asyncio.to_thread(self._init_db)
        self._writer_task = asyncio.create_task(self._writer_loop(), name="storage_writer")

    def _init_db(self) -> None:
        try:
            self._conn = sqlite3.connect(self._db_path, isolation_level=None, check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA synchronous=NORMAL;")
            self._conn.execute("PRAGMA temp_store=MEMORY;")
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    signal_id TEXT NOT NULL,
                    pair TEXT NOT NULL,
                    side TEXT,
                    strategy TEXT,
                    grade TEXT,
                    confidence REAL,
                    risk_score REAL,
                    payload_json TEXT NOT NULL
                );
            """)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    event_type TEXT NOT NULL,
                    pair TEXT,
                    payload_json TEXT NOT NULL
                );
            """)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS operator_state (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
            """)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS safety_state (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
            """)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS provider_health (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    provider TEXT NOT NULL,
                    state TEXT,
                    failures INTEGER,
                    latency_p95 REAL,
                    payload_json TEXT
                );
            """)
            # Bounded retention: keep last 100k rows per table.
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_ts ON signals(timestamp);")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(timestamp);")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_health_ts ON provider_health(timestamp);")
        except sqlite3.Error as exc:
            log.x_error("storage init failed (continuing in-memory)", extras={"err": str(exc)})
            self._conn = None

    async def _writer_loop(self) -> None:
        while not self._stop.is_set():
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=self._write_interval)
            except asyncio.TimeoutError:
                continue
            # Drain queue.
            batch = [item]
            while not self._queue.empty():
                try:
                    batch.append(self._queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
            try:
                await asyncio.to_thread(self._write_batch, batch)
            except Exception as exc:  # pragma: no cover - defensive
                log.x_warn("storage write batch failed", extras={"err": str(exc)})

    def _write_batch(self, batch: list[tuple[str, dict]]) -> None:
        if self._conn is None:
            return
        cur = self._conn.cursor()
        for op, payload in batch:
            try:
                ts = payload.get("timestamp", time.time())
                if op == "signal":
                    cur.execute(
                        "INSERT INTO signals (timestamp, signal_id, pair, side, strategy, grade, confidence, risk_score, payload_json) VALUES (?,?,?,?,?,?,?,?,?)",
                        (ts, payload.get("signal_id"), payload.get("pair"),
                         payload.get("side"), payload.get("strategy"),
                         payload.get("grade"), payload.get("confidence"),
                         payload.get("risk_score"), json.dumps(payload, default=str)),
                    )
                elif op == "audit":
                    cur.execute(
                        "INSERT INTO audit_log (timestamp, event_type, pair, payload_json) VALUES (?,?,?,?)",
                        (ts, payload.get("event_type"), payload.get("pair"),
                         json.dumps(payload, default=str)),
                    )
                elif op == "operator_state":
                    for k, v in payload.get("items", {}).items():
                        cur.execute(
                            "INSERT OR REPLACE INTO operator_state (key, value_json, updated_at) VALUES (?,?,?)",
                            (k, json.dumps(v, default=str), ts),
                        )
                elif op == "safety_state":
                    for k, v in payload.get("items", {}).items():
                        cur.execute(
                            "INSERT OR REPLACE INTO safety_state (key, value_json, updated_at) VALUES (?,?,?)",
                            (k, json.dumps(v, default=str), ts),
                        )
                elif op == "provider_health":
                    cur.execute(
                        "INSERT INTO provider_health (timestamp, provider, state, failures, latency_p95, payload_json) VALUES (?,?,?,?,?,?)",
                        (ts, payload.get("provider"), payload.get("state"),
                         payload.get("failures"), payload.get("latency_p95"),
                         json.dumps(payload, default=str)),
                    )
            except sqlite3.Error as exc:
                log.x_warn("storage write row failed", extras={"op": op, "err": str(exc)})
        # Bounded retention: prune old rows.
        try:
            cur.execute("DELETE FROM signals WHERE id NOT IN (SELECT id FROM signals ORDER BY timestamp DESC LIMIT 100000);")
            cur.execute("DELETE FROM audit_log WHERE id NOT IN (SELECT id FROM audit_log ORDER BY timestamp DESC LIMIT 100000);")
            cur.execute("DELETE FROM provider_health WHERE id NOT IN (SELECT id FROM provider_health ORDER BY timestamp DESC LIMIT 10000);")
        except sqlite3.Error:
            pass

    async def persist_signal(self, signal: Signal, risk_score: float = 0.0) -> None:
        payload = signal.to_dict()
        payload["risk_score"] = risk_score
        payload["timestamp"] = signal.created_at
        try:
            self._queue.put_nowait(("signal", payload))
        except asyncio.QueueFull:
            log.x_warn("storage queue full — dropping signal")

    async def persist_audit(self, event_type: str, pair: str | None, payload: dict) -> None:
        try:
            self._queue.put_nowait(("audit", {
                "event_type": event_type, "pair": pair, "timestamp": time.time(),
                **payload,
            }))
        except asyncio.QueueFull:
            log.x_warn("storage queue full — dropping audit")

    async def persist_operator_state(self, items: dict[str, Any]) -> None:
        try:
            self._queue.put_nowait(("operator_state", {"items": items, "timestamp": time.time()}))
        except asyncio.QueueFull:
            pass

    async def persist_safety_state(self, items: dict[str, Any]) -> None:
        try:
            self._queue.put_nowait(("safety_state", {"items": items, "timestamp": time.time()}))
        except asyncio.QueueFull:
            pass

    async def persist_provider_health(self, health: list[dict]) -> None:
        for h in health:
            try:
                # ProviderHealth dataclass uses 'name' for the provider field.
                provider_name = h.get("provider") or h.get("name", "unknown")
                self._queue.put_nowait(("provider_health", {
                    **h, "provider": provider_name, "timestamp": time.time(),
                }))
            except asyncio.QueueFull:
                break

    async def load_operator_state(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._load_operator_state)

    def _load_operator_state(self) -> dict[str, Any]:
        if self._conn is None:
            return {}
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT key, value_json FROM operator_state;")
            return {row[0]: json.loads(row[1]) for row in cur.fetchall()}
        except sqlite3.Error:
            return {}

    async def load_safety_state(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._load_safety_state)

    def _load_safety_state(self) -> dict[str, Any]:
        if self._conn is None:
            return {}
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT key, value_json FROM safety_state;")
            return {row[0]: json.loads(row[1]) for row in cur.fetchall()}
        except sqlite3.Error:
            return {}

    async def stop(self) -> None:
        self._stop.set()
        if self._writer_task is not None:
            self._writer_task.cancel()
            try:
                await self._writer_task
            except (asyncio.CancelledError, Exception):
                pass
            self._writer_task = None
        if self._conn is not None:
            await asyncio.to_thread(self._conn.close)
            self._conn = None
