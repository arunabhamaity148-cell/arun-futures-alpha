# TEST RESULTS — ARUN

## Test Suite

Location: `tests/`

Framework: `pytest` + `pytest-asyncio`

## Categories

### Unit Tests
- `test_rolling.py` — rolling mean/variance/EWMA/zscore/quantile (O(1) updates, exact windows)
- `test_ringbuffer.py` — bounded ring buffer (threadsafe, eviction)
- `test_circuit_breaker.py` — circuit breaker, rate limiter, backoff
- `test_coindcx_provider.py` — CoinDCX ticker parsing (incl. B- prefix, missing fields, invalid markets)
- `test_cvd.py` — CVD accumulator (window eviction, z-score, reset)
- `test_obi.py` — Order Book Imbalance
- `test_absorption.py` — Absorption detector (CVD + price + OBI)
- `test_price_impact.py` — Square-root impact model (empty book, illiquid flag)
- `test_funding_oi.py` — Funding + OI analysers (z-score, crowding, impulse)
- `test_cascade.py` — Liquidation cascade (cascade index, exhaustion, deceleration)
- `test_mismatch_engine.py` — CoinDCX mismatch (normal/high/no-trade bands, fail-closed)
- `test_leadlag.py` — Cross-exchange lead/lag (detection, uncorrelated data)
- `test_risk_gate.py` — RISK_SCORE (low/high/medium, fail-closed, news block)
- `test_sizing.py` — Position sizing (leverage cap, book depth cap, correlated cap)
- `test_sltp.py` — SL/TP builder (ATR-based, LONG/SHORT, R:R check, ordering)
- `test_vetoes.py` — V1-V5 veto engine (hard/soft, fail-closed)
- `test_newsguard.py` — NewsGuard (BLOCK/REDUCE/ALLOW, dedup, pair filtering, provider unavailable)
- `test_regime.py` — Regime classifier (TREND_UP/DOWN, RANGE, dislocation, UNKNOWN)
- `test_footprint.py` — Institutional footprint (low/high, subscores, "proxy" label)
- `test_portfolio.py` — Portfolio crowding (BTC/ETH beta, PCA concentration, directional exposure)
- `test_backtest.py` — Backtest framework (cost model, metrics, Deflated Sharpe)

### Integration Tests
- `test_signal_generator.py` — End-to-end signal generation (alpha engine, fail-closed when unverified)
- `test_signal_format.py` — Telegram message formatting (all required fields present)
- `test_storage.py` — SQLite persistence (round-trip, operator state, in-memory mode)

### Resilience / Fault Injection
- `test_fault_injection.py` — 429, 500, timeout, malformed payload, network outage, schema validation
- `test_safety.py` — Safety latches (daily loss, consecutive loss, pause, mute, reset, persist round-trip)
- `test_shutdown.py` — Shutdown manager (reverse-order hooks, timeout, exception isolation)
- `test_operator.py` — Operator commands (status, pause, mute, reset, authorization)

### Health Monitoring
- `test_health.py` — RSS sampling, event-loop lag, snapshot

## Test Counts

- Total test files: 22
- Total test cases: 151
- Passing: 151
- Failing: 0
- Skipped: 0

## Extracted-Artifact Verification

After building `ARUN_COINDCX_FUTURES_SIGNAL_BOT_FINAL.zip`, the ZIP was
extracted into a clean directory and the full test suite was re-run:

```
cd clean_extract/ARUN_SIGNAL_BOT
python3 -m pytest tests/ -q
........................................................................ [ 47%]
........................................................................ [ 95%]
.......                                                                  [100%]
151 passed in 56.27s
```

All 151 tests pass against the extracted artifact.

## How to Run

```bash
cd ARUN_SIGNAL_BOT
pip install -r requirements-dev.txt
pytest tests/ -v
```

## Coverage of Critical Paths

| Path | Test |
|---|---|
| CoinDCX ticker parsing | `test_coindcx_provider.py` |
| CoinDCX mismatch fail-closed | `test_mismatch_engine.py::test_mismatch_fail_closed_when_data_missing` |
| CoinDCX mismatch NO_TRADE | `test_mismatch_engine.py::test_mismatch_no_trade_when_coindcx_far_off` |
| V1 cross-exchange contradiction | `test_vetoes.py::test_v1_hard_veto_when_coindcx_far_off` |
| V3 liquidity vacuum | `test_vetoes.py::test_v3_hard_veto_when_book_thin` |
| V5 news BLOCK | `test_vetoes.py::test_v5_hard_veto_on_news_block` |
| V2 OI/funding contradiction | `test_vetoes.py::test_v2_soft_when_persistent_contradiction` |
| Risk gate fail-closed | `test_risk_gate.py::test_fail_closed_on_missing_inputs` |
| Risk gate news BLOCK | `test_risk_gate.py::test_news_block_forces_no_trade` |
| Safety daily-loss kill | `test_safety.py::test_daily_loss_kill_triggers` |
| Safety consecutive-loss latch | `test_safety.py::test_consecutive_loss_latch` |
| Safety state persistence | `test_safety.py::test_persist_round_trip` |
| Signal generator fail-closed when unverified | `test_signal_generator.py::test_signal_generator_fail_closed_when_unverified` |
| Network outage does not crash | `test_fault_injection.py::test_network_error_does_not_crash_data_manager` |
| Schema validation catches malformed | `test_fault_injection.py::test_schema_validation_catches_malformed_payload` |
| Circuit breaker opens on 429/500 | `test_fault_injection.py::test_provider_429_triggers_circuit_breaker` |
| Circuit breaker half-open recovery | `test_circuit_breaker.py::test_circuit_breaker_half_open_recovers_on_success` |
| Shutdown hook isolation | `test_shutdown.py::test_hook_exception_does_not_block_others` |
