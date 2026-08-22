from __future__ import annotations

import asyncio
import json
import statistics
import time

from trader_arun.core.config import Config
from trader_arun.data.manager import DataManager
from trader_arun.ops.health import HealthMonitor


async def _monitor_loop_lag(stop: asyncio.Event, samples: list[float], interval: float = 0.05) -> None:
    loop = asyncio.get_running_loop()
    next_tick = loop.time() + interval
    while not stop.is_set():
        await asyncio.sleep(interval)
        now = loop.time()
        samples.append(max(0.0, now - next_tick))
        next_tick = now + interval


async def main() -> None:
    cfg = Config(request_timeout_sec=3.0, max_concurrent_requests=8)
    hm = HealthMonitor()
    start = time.time()
    lag_samples: list[float] = []
    events = 0
    provider_errors = 0
    core_stale = 0
    optional_stale = 0
    reconnects = 0
    rss_samples = []
    task_samples = []
    pairs = cfg.pairs[:3]
    stop_event = asyncio.Event()
    monitor = asyncio.create_task(_monitor_loop_lag(stop_event, lag_samples))
    try:
        async with DataManager(cfg) as dm:
            await dm.verify_futures_universe()
            while time.time() - start < 60.0:
                snaps = await asyncio.gather(*(dm.fetch_pair_snapshot(p) for p in pairs), return_exceptions=True)
            for snap in snaps:
                if isinstance(snap, Exception):
                    provider_errors += 1
                    continue
                events += 1
                if not dm.validate_ticker(snap.coindcx_ticker, "coindcx"):
                    core_stale += 1
                if not snap.external_tickers:
                    optional_stale += 1
                await asyncio.sleep(0.2)
                snap = hm.snapshot(task_count=len(asyncio.all_tasks()), signal_count=0, veto_count=0)
                rss_samples.append(snap.rss_mb)
                task_samples.append(snap.task_count)
            health = dm.registry.health()
            provider_errors += sum(h.failures_in_window for h in health)
    finally:
        stop_event.set()
        await monitor
    result = {
        "duration_sec": round(time.time() - start, 3),
        "events": events,
        "events_per_sec": round(events / max(time.time() - start, 1e-9), 3),
        "connections": 5,
        "reconnects": reconnects,
        "provider_errors": provider_errors,
        "stale_suppressions_core": core_stale,
        "stale_suppressions_optional": optional_stale,
        "event_loop_lag_p95_sec": round(statistics.quantiles(lag_samples, n=20)[18], 6) if len(lag_samples) >= 20 else round(max(lag_samples, default=0.0), 6),
        "event_loop_lag_max_sec": round(max(lag_samples, default=0.0), 6),
        "rss_mb_last": round(rss_samples[-1], 3) if rss_samples else 0.0,
        "rss_mb_peak": round(max(rss_samples, default=0.0), 3),
        "task_count_last": task_samples[-1] if task_samples else 0,
        "task_count_peak": max(task_samples, default=0),
        "queue_hwm": 0,
        "signals": 0,
        "vetoes": 0,
        "coindcx_verified": False,
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
