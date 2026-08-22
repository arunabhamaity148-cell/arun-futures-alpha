# Architecture Changes

## Summary

This audit added the missing runtime data plane and tightened fail-closed behaviour around CoinDCX execution-truth requirements.

## Added modules

### `trader_arun/data/base.py`
- async provider primitive
- circuit breaker
- rate limiter
- bounded latency telemetry
- provider health reporting

### `trader_arun/data/coindcx.py`
- CoinDCX ticker parser
- CoinDCX orderbook parser with dict/list compatibility
- candle parsing
- futures symbol discovery / verification helpers
- warning throttling

### `trader_arun/data/manager.py`
- `PairSnapshot`
- `ProviderRegistry`
- `ReferenceHTTPProvider`
- `DataManager`
- bounded per-call isolation with `asyncio.wait_for`
- bounded trade history storage
- ticker freshness validation

### `trader_arun/data/leadlag.py`
- normalized lead/lag report for strategy S2

### `trader_arun/data/mismatch.py`
- cross-exchange mismatch scoring
- timestamp-skew penalty
- bounded mismatch history / EWMA / MAD / z-score

## Repaired existing module

### `trader_arun/ops/health.py`
- imported `sys` to restore RSS snapshot support on Unix-like platforms

## Behavioural changes

1. CoinDCX critical fields remain distinct from reference venues.
2. Missing CoinDCX verification now fails closed instead of drifting into implicit fallback semantics.
3. Provider calls are bounded by semaphore + timeout.
4. Provider failures return partial snapshots instead of crashing the fetch path.
5. Repeated provider warnings are throttled.
6. Orderbook parsing accepts the observed dict-form payload variant.

## Net effect

The repository now has a coherent exchange-normalization layer that the existing alpha, veto, risk, and signal modules can actually execute against.
