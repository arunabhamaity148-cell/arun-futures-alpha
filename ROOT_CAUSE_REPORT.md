# Root Cause Report

## Verdict

The original repository was **structurally incomplete** for runtime use. The largest operational failure was not a single bug but a broken data plane: the application imported `trader_arun.data.*` modules that did not exist in the repository. That defect alone prevented collection-time import success and invalidated the exchange → normalization → alpha → veto → risk path.

## Verified root causes

### P0

1. **Missing data package**
   - `trader_arun.data.base`
   - `trader_arun.data.coindcx`
   - `trader_arun.data.manager`
   - `trader_arun.data.leadlag`
   - `trader_arun.data.mismatch`
   - Impact: hard import failure, no runtime data flow, no signal generation.

2. **No executable CoinDCX normalization path**
   - No provider implementation existed for ticker/orderbook/candle normalization.
   - Impact: no validated CoinDCX execution-truth state.

3. **No implemented provider isolation layer**
   - No bounded-concurrency snapshot manager existed.
   - Impact: provider timeouts or malformed responses could not be isolated by pair/provider.

### P1

4. **No implemented mismatch engine module**
   - Existing signal path imported a mismatch engine that was absent.
   - Impact: no mathematical cross-exchange dislocation gate.

5. **No implemented lead/lag engine module**
   - `S2` imported a missing module.
   - Impact: strategy path incomplete.

6. **Health monitor RSS bug**
   - `sys` was referenced but not imported in `HealthMonitor.get_rss_mb()`.
   - Impact: health tests failed and RSS snapshotting could crash on Unix-like systems.

7. **Orderbook schema fragility**
   - Runtime bug report mentioned `bids expected list, got dict`.
   - Root cause: no resilient parser existed to accept either dict or list payload forms.
   - Impact: provider payload rejection / data-quality halt.

### P2

8. **Repetitive provider warning noise**
   - Repeated failing venue calls could produce repeated logs.
   - Repair added warning throttling for provider fetch failures.

9. **Incomplete live verification evidence**
   - CoinDCX futures-universe confirmation and Binance reference access were environment-dependent.
   - Impact: repository cannot honestly be labeled production candidate without that evidence.

## Observed environment limitations during verification

- Binance futures endpoints returned **HTTP 451** in this environment.
- CoinDCX futures-universe verification remained **not verified**.
- Hyperliquid reference access returned usable ticker/book data in probe runs.

## Repair summary

- implemented full `trader_arun.data` package
- restored import/runtime continuity
- added exact symbol verification path for CoinDCX futures
- added strict ticker freshness validation
- added dict-or-list CoinDCX orderbook parsing
- added bounded async provider orchestration with circuit breakers and timeouts
- added mismatch scoring and timestamp-skew penalty
- repaired health monitor RSS path
- added regression tests covering repaired failures

## Final release status

The source tree is now **buildable, testable, and packageable**, but it is **NOT READY** for production use until live CoinDCX futures verification and full environment-level soak verification are completed.
