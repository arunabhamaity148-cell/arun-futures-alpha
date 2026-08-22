# ARUN CoinDCX Futures Signal Bot

## Audit status

**Current status: NOT READY**

This repository was audited and repaired as a **signal-only** system. It does **not** place exchange orders. The repaired build now has a complete `trader_arun.data` package, bounded async provider isolation, fail-closed CoinDCX validation, a configurable cross-exchange mismatch engine, regression coverage for the repaired faults, and a clean packaging workflow.

What is verified:
- full automated test suite passes: **155 passed**
- CoinDCX ticker parsing and orderbook schema handling are covered by tests
- fallback/reference data remains explicitly separated from CoinDCX execution-truth fields
- provider timeout / circuit-breaker / failure-isolation paths are covered by tests
- final package build, extraction, retest, compile, and security/artifact checks are documented

What is **not** verified:
- exact CoinDCX futures instrument universe in this environment
- Binance futures reference access in this environment (HTTP 451 geo restriction observed)
- 15-minute live soak against all target venues
- profitability / walk-forward performance

## Core operating rule

If CoinDCX critical execution-truth data is unavailable, stale, malformed, or unverifiable, ARUN must emit **NO TRADE**.

## Data hierarchy

1. **CoinDCX** = execution truth for critical trading fields
2. **Binance Futures** = primary external reference when optional CoinDCX fields are missing
3. **Hyperliquid / Bybit / Kraken** = secondary reference venues when available

Reference venues never become implicit execution truth.

## Repaired areas

- added missing async data package (`base`, `coindcx`, `manager`, `leadlag`, `mismatch`)
- repaired health monitor RSS path (`sys` import bug)
- added strict ticker freshness / shape validation
- added CoinDCX orderbook parser support for dict-or-list payloads
- added exact-symbol futures-universe verification path
- added bounded concurrent snapshot fetch with per-call timeout isolation
- added mismatch scoring for price, bid/ask, spread, returns, liquidity, and timestamp skew
- added log-throttling for repetitive provider warnings
- added regression tests for the repaired failure cases

## Key commands

```bash
pytest -q
PYTHONPATH=. python3 scripts/live_probe.py
ARUN_LOG_LEVEL=ERROR PYTHONPATH=. python3 scripts/smoke_test.py
```

## Release verdict

This build is a **repair-complete audited source package**, but it is **not a production candidate** yet because live CoinDCX futures verification and a full 15-minute multi-venue soak were not verified in the execution environment.
