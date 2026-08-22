# Runtime Verification

## Live probe

Command:

```bash
PYTHONPATH=. python3 scripts/live_probe.py
```

### Observed result

- CoinDCX futures universe: **not verified**
- Binance futures reference: **unavailable in this environment** (`HTTP 451` observed)
- Hyperliquid reference: **partially reachable** (ticker/book observed)
- CoinDCX candles/orderbook: **partially reachable**
- CoinDCX ticker endpoint / exact futures mapping: **not verified**

### Interpretation

The repaired code handled venue failure without crashing, preserved external-reference separation, and produced partial snapshots. However, the environment did not provide enough successful CoinDCX-futures/Binance access to certify production readiness.

## 60-second smoke

Command:

```bash
ARUN_LOG_LEVEL=ERROR PYTHONPATH=. python3 scripts/smoke_test.py
```

### Observed metrics

- duration_sec: **61.082**
- events: **3**
- events_per_sec: **0.049**
- connections: **5**
- reconnects: **0**
- provider_errors: **11**
- stale_suppressions_core: **3**
- stale_suppressions_optional: **0**
- event_loop_lag_p95_sec: **0.001729**
- event_loop_lag_max_sec: **0.006071**
- rss_mb_peak: **60.379**
- task_count_peak: **2**
- signals: **0**
- vetoes: **0**

### Smoke verdict

- Async/event-loop blocking: **improved / low lag in observed run**
- Market readiness: **not verified**
- Signal emission: **correctly suppressed** because CoinDCX critical data was not verified

## 15-minute soak

**NOT VERIFIED — ENVIRONMENT LIMITATION**

Reasons:
- Binance futures reference was geo-restricted in this environment.
- CoinDCX futures-universe verification was not confirmed.
- The available execution environment was not suitable evidence for a truthful 15-minute multi-venue production soak conclusion.
