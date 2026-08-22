"""ARUN main async application.

Orchestrates:
- Config load
- DataManager (all providers)
- NewsGuard
- PortfolioCrowdingEngine
- SignalGenerator
- TelegramPublisher
- OperatorCommandHandler (Telegram bot polling)
- HealthMonitor
- SafetyLatches
- StorageEngine
- ShutdownManager
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from .core.config import Config, load_config
from .core.exceptions import ShutdownRequested
from .core.logger import get_logger, set_log_level
from .data.manager import DataManager
from .newsguard.engine import NewsGuard
from .ops.health import HealthMonitor
from .ops.operator import OperatorCommandHandler, OperatorState
from .ops.safety import SafetyLatches
from .ops.shutdown import ShutdownManager
from .ops.storage import StorageEngine
from .portfolio.crowding import PortfolioCrowdingEngine
from .signals.audit import AuditTrail
from .signals.generator import SignalGenerator
from .signals.publisher import TelegramPublisher

log = get_logger("app")


class ARUNApp:
    """Main ARUN application."""

    def __init__(self, cfg: Config | None = None) -> None:
        self._cfg = cfg or load_config()
        set_log_level(self._cfg.log_level)
        self._dm: DataManager | None = None
        self._news = NewsGuard()
        self._portfolio = PortfolioCrowdingEngine()
        self._safety = SafetyLatches(
            daily_loss_kill_pct=self._cfg.daily_loss_kill_pct,
            consecutive_loss_latch=self._cfg.consecutive_loss_latch,
        )
        self._operator_state = OperatorState()
        self._audit = AuditTrail(max_entries=500)
        self._health = HealthMonitor(
            rss_warning_mb=self._cfg.rss_warning_mb,
            rss_critical_mb=self._cfg.rss_critical_mb,
            event_loop_lag_warning_sec=self._cfg.event_loop_lag_warning_sec,
            event_loop_lag_critical_sec=self._cfg.event_loop_lag_critical_sec,
        )
        self._shutdown = ShutdownManager()
        self._storage = StorageEngine(db_path=self._cfg.sqlite_path)
        self._publisher: TelegramPublisher | None = None
        self._generator: SignalGenerator | None = None
        self._operator: OperatorCommandHandler | None = None
        self._coindcx_verified = False
        self._signals_today: list = []
        self._stop = False

    async def __aenter__(self) -> "ARUNApp":
        await self.start()
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.stop()

    async def start(self) -> None:
        log.x_info("ARUN starting", extras={
            "version": "1.0.0",
            "paper_mode": self._cfg.paper_mode,
            "pairs": len(self._cfg.pairs),
        })

        # Storage first (for state recovery).
        await self._storage.start()
        # Recover safety state.
        safety_state = await self._storage.load_safety_state()
        if safety_state:
            self._safety.load_from_persist(safety_state)
            log.x_info("safety state recovered", extras={"keys": list(safety_state.keys())})

        # Data manager.
        self._dm = DataManager(self._cfg)
        await self._dm.start()

        # Verify CoinDCX futures universe (NOT VERIFIED if it fails).
        try:
            self._coindcx_verified = await self._dm.verify_futures_universe()
        except Exception as exc:  # pragma: no cover - defensive
            log.x_warn("coindcx futures verification failed", extras={"err": str(exc)})
            self._coindcx_verified = False

        # Signal generator.
        self._generator = SignalGenerator(
            cfg=self._cfg,
            news_guard=self._news,
            portfolio_engine=self._portfolio,
            coindcx_futures_verified=self._coindcx_verified,
        )

        # Telegram publisher + operator.
        self._publisher = TelegramPublisher(
            bot_token=self._cfg.telegram_bot_token,
            chat_id=self._cfg.telegram_chat_id,
        )
        self._operator = OperatorCommandHandler(
            operator_state=self._operator_state,
            safety=self._safety,
            get_recent_signals=lambda: self._signals_today,
            get_health=lambda: [h.__dict__ for h in self._dm.registry.health()],
        )
        self._operator.set_whitelist(list(self._cfg.operator_whitelist))

        # Shutdown hooks.
        self._shutdown.add_hook(self._publisher.close)
        self._shutdown.add_hook(self._dm.stop)
        self._shutdown.add_hook(self._storage.stop)
        self._shutdown.install_signal_handlers()

        log.x_info("ARUN started", extras={
            "coindcx_verified": self._coindcx_verified,
            "telegram_enabled": self._publisher.enabled,
        })

        if self._publisher.enabled:
            await self._publisher.register_commands()
            await self._publisher.publish_text(
                f"🟢 ARUN online · paper_mode={self._cfg.paper_mode} · "
                f"coindcx_verified={self._coindcx_verified}"
            )

    async def stop(self) -> None:
        log.x_info("ARUN stopping")
        self._stop = True
        await self._shutdown.execute_shutdown()
        log.x_info("ARUN stopped")

    async def run_forever(self) -> None:
        """Main decision loop."""
        if self._dm is None or self._generator is None:
            raise RuntimeError("ARUN not started")
        last_decision = 0.0
        last_health_log = 0.0
        last_news_poll = 0.0
        last_news_pair = 0  # round-robin news fetching
        while not self._stop and not self._shutdown.shutdown_requested:
            try:
                now = time.time()
                # Decision cycle.
                if now - last_decision >= self._cfg.decision_interval_sec:
                    try:
                        await asyncio.wait_for(self._decision_cycle(), timeout=120.0)
                    except asyncio.TimeoutError:
                        log.x_warn("decision cycle timed out")
                    except Exception as exc:
                        log.x_warn("decision cycle error", extras={"err": str(exc)})
                    last_decision = now
                # Health snapshot every 60s.
                if now - last_health_log >= 60.0:
                    snap = self._health.snapshot(
                        task_count=len(asyncio.all_tasks()),
                        signal_count=self._operator_state.signal_count,
                        veto_count=0,  # populated by generator if needed
                    )
                    await self._storage.persist_provider_health(
                        [h.__dict__ for h in self._dm.registry.health()]
                    )
                    last_health_log = now
                # News polling every 5 min (round-robin one pair at a time to stay light).
                # Wrapped in timeout to prevent blocking the main loop.
                if now - last_news_poll >= 300.0:
                    pairs = self._cfg.pairs
                    if pairs:
                        pair = pairs[last_news_pair % len(pairs)]
                        try:
                            await asyncio.wait_for(
                                self._poll_news(pair.base), timeout=15.0
                            )
                        except asyncio.TimeoutError:
                            log.x_warn("news poll timed out", extras={"pair": pair.base})
                        except Exception as exc:
                            log.x_warn("news poll error", extras={
                                "pair": pair.base, "err": str(exc),
                            })
                        last_news_pair += 1
                    last_news_poll = now
                await asyncio.sleep(self._cfg.loop_interval_sec)
            except ShutdownRequested:
                break
            except Exception as exc:  # pragma: no cover - defensive
                log.x_error("main loop error", extras={"err": str(exc)})
                await asyncio.sleep(5.0)

    async def _decision_cycle(self) -> None:
        """Run signal generation across all pairs."""
        assert self._dm is not None and self._generator is not None
        # Safety check first.
        can_trade, reason = await self._safety.check_can_trade()
        if not can_trade:
            log.x_info("no trade — safety latch", extras={"reason": reason})
            return

        # Fetch all CoinDCX tickers ONCE (instead of per-pair) to avoid 10x
        # redundant full-list fetches. This dramatically reduces event-loop lag.
        coindcx_tickers: dict[str, "Ticker"] = {}
        try:
            coindcx_tickers = await asyncio.wait_for(
                self._dm.coindcx.get_all_tickers(), timeout=10.0
            )
        except asyncio.TimeoutError:
            log.x_warn("coindcx all-tickers fetch timed out")
        except Exception as exc:
            log.x_warn("coindcx all-tickers fetch failed", extras={"err": str(exc)})

        # Iterate watchlist.
        for pair in self._cfg.pairs:
            try:
                # Per-pair timeout to prevent one slow pair from blocking the cycle.
                snap = await asyncio.wait_for(
                    self._dm.fetch_pair_snapshot(pair, coindcx_tickers=coindcx_tickers),
                    timeout=30.0,
                )
                # Quality gate.
                if not self._dm.validate_ticker(snap.coindcx_ticker, "coindcx"):
                    await self._safety.set_data_quality_halt(True, f"{pair.base} coindcx ticker invalid")
                    self._audit.record_event("data_quality_fail", {"pair": pair.base})
                    continue
                # Generate.
                trade_history = {
                    venue: self._dm.get_trade_history(venue, pair.base)
                    for venue in ("coindcx", "binance", "hyperliquid")
                }
                result = self._generator.generate(snap, trade_history)
                if result.signal is None:
                    self._operator_state.reject_count += 1
                    self._audit.record(None, result.audit)
                    continue
                # Signal accepted.
                signal = result.signal
                self._operator_state.signal_count += 1
                self._operator_state.last_signal = signal
                self._signals_today.append(signal)
                if len(self._signals_today) > 50:
                    self._signals_today = self._signals_today[-50:]
                self._audit.record(signal, result.audit)
                # Persist.
                await self._storage.persist_signal(signal, risk_score=result.audit.get("risk", {}).get("score", 0.0))
                # Publish (unless muted).
                if not await self._safety.is_muted() and self._publisher is not None:
                    await self._publisher.publish_signal(signal)
                log.x_info("signal generated", extras={
                    "signal_id": signal.signal_id,
                    "pair": signal.pair,
                    "side": signal.side.value,
                    "strategy": signal.strategy,
                    "confidence": signal.confidence,
                    "grade": signal.grade.value,
                })
            except asyncio.TimeoutError:
                log.x_warn("pair fetch timed out", extras={"pair": pair.base})
            except Exception as exc:  # pragma: no cover - defensive
                log.x_warn("pair decision error", extras={
                    "pair": pair.base, "err": str(exc),
                })

    async def _poll_news(self, base: str) -> None:
        """Fetch news for one pair (round-robin)."""
        assert self._dm is not None
        try:
            items = await self._dm.gdelt.search(
                query=f"{base} crypto", max_records=10, pair_tags=[base],
            )
            if items:
                self._news.ingest(items)
        except Exception as exc:  # pragma: no cover - defensive
            log.x_debug("news poll failed", extras={"pair": base, "err": str(exc)})

    @property
    def operator(self) -> OperatorCommandHandler:
        assert self._operator is not None
        return self._operator

    @property
    def audit(self) -> AuditTrail:
        return self._audit

    @property
    def health(self) -> HealthMonitor:
        return self._health

    @property
    def coindcx_verified(self) -> bool:
        return self._coindcx_verified
