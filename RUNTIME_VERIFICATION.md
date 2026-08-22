# RUNTIME VERIFICATION — ARUN

## 1. Clean Install

```bash
# Create fresh venv.
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies.
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Verify imports.
python3 -c "from trader_arun.app import ARUNApp; print('imports ok')"

# Result: PASS
```

## 2. Startup / Import Verification

```bash
python3 -c "
from trader_arun.core.config import load_config
from trader_arun.app import ARUNApp
import asyncio

async def test():
    cfg = load_config()
    async with ARUNApp(cfg) as app:
        print(f'started: coindcx_verified={app.coindcx_verified}')
        print(f'audit entries: {len(app.audit.snapshot())}')

asyncio.run(test())
# Result: PASS (bot starts, providers connect, no exceptions)
```

## 3. Compile Check (all .py files)

```bash
python3 -m compileall trader_arun/ -q
# Result: PASS (no syntax errors)
```

## 4. Static Type Sanity (manual review)

All public functions have type annotations. No `Any` returns on hot paths.
TypedDicts and dataclasses used throughout. Enum values are strings (JSON-
serialisable).

## 5. 60-Second Live Smoke

**Status: NOT VERIFIED — ENVIRONMENT LIMITATION**

**Actual smoke run (22 Aug 2026, this sandbox):**

| Provider | State | p95 latency | Failures |
|---|---|---|---|
| coindcx | DEGRADED | 0.000s | 43 (HTTP 403 — geo-blocked from sandbox) |
| hyperliquid | DEGRADED → HEALTHY | 0.160s | 9 (initial retries, then healthy) |
| kraken | HEALTHY | 0.487s | 0 |
| binance_futures | HEALTHY | 0.088s | 14 (some endpoints 451 geo-blocked) |
| bybit | HEALTHY | 0.078s | 0 |
| coinglass | HEALTHY | 0.000s | 0 (no API key — empty responses) |
| gdelt | HEALTHY | 0.000s | 0 |
| fred | HEALTHY | 0.000s | 0 |
| tokenunlocks | HEALTHY | 0.000s | 0 |

**Observed behavior:**
- elapsed: 75.1s (60s run + 15s shutdown)
- signals emitted: 0 (correct — coindcx_verified=False → fail-closed)
- audit entries: 10 (one data_quality_fail event per pair per decision cycle)
- shutdown: clean, all hooks called, no orphan tasks, no unclosed sessions
- RSS memory: ~150 MB (well under 350 MB warning threshold)

**NOT VERIFIED (sandbox limits):**
- CoinDCX futures universe verification (HTTP 403 from sandbox)
- Live signal generation (requires non-geo-blocked deployment)
- 15-min soak (would require longer run window)

**Conclusion:** The bot's fail-closed behavior is **VERIFIED** — when CoinDCX
data is unavailable, the bot correctly emits zero signals and records
data-quality events. The external data providers (Hyperliquid, Kraken, Bybit)
all work from this environment.

## 6. 15-Minute Live Soak

**Status: NOT VERIFIED — ENVIRONMENT LIMITATION**

Same as above. The 15-minute soak would additionally measure:
- Memory growth (target: < 50 MB growth in 15 min)
- Reconnect count (target: 0)
- Provider circuit breaker state transitions (target: 0 opens)
- Signal/veto counts (target: 0-2 signals, 5-15 veto rejections)
- Audit log size (target: < 1000 entries)
- SQLite DB size (target: < 1 MB)

## 7. Shutdown Validation

```bash
python3 -c "
import asyncio, signal
from trader_arun.app import ARUNApp
from trader_arun.core.config import load_config

async def test():
    cfg = load_config()
    app = ARUNApp(cfg)
    await app.start()
    # Schedule shutdown after 2 seconds.
    asyncio.get_event_loop().call_later(2.0, app._shutdown.request_shutdown)
    await app.run_forever()
    print('shutdown complete')

asyncio.run(test())
# Result: PASS (clean shutdown, all hooks called, no orphan tasks)
```

## 8. Fault Injection (verified via unit tests)

See `tests/test_fault_injection.py` and `tests/test_safety.py` for full
coverage. All fault paths produce fail-closed behavior:
- 429 → circuit breaker opens → ProviderUnavailable → NO TRADE
- 500 → circuit breaker opens → ProviderUnavailable → NO TRADE
- Timeout → circuit breaker opens → ProviderUnavailable → NO TRADE
- Malformed payload → SchemaError → NO TRADE
- Network outage → all providers fail → snapshot has None fields → NO TRADE
- News provider unavailable → NewsGuard fails-safe to BLOCK → NO TRADE

## Summary

| Check | Status |
|---|---|
| Clean install | PASS |
| Import / startup | PASS |
| Compile (all .py) | PASS |
| Type sanity | PASS (manual review) |
| 60-sec live smoke | NOT VERIFIED — ENVIRONMENT LIMITATION |
| 15-min live soak | NOT VERIFIED — ENVIRONMENT LIMITATION |
| Shutdown | PASS |
| Fault injection | PASS (via unit tests) |
