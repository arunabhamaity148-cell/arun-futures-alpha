# Fault Injection Results

## Source of evidence

- `tests/test_fault_injection.py`
- `tests/test_data_pipeline_regressions.py`

## Verified behaviours

### Provider overload / outage
- repeated `429` opens provider circuit breaker
- repeated `500` opens provider circuit breaker
- repeated timeout opens provider circuit breaker
- failed providers raise typed exceptions instead of silently fabricating values

### Schema resilience
- malformed `/exchange/ticker` payload raises `SchemaError`
- CoinDCX orderbook parser accepts dict-or-list sides and rejects malformed items deterministically

### Isolation
- if all providers fail, `DataManager.fetch_pair_snapshot()` still returns a partial snapshot instead of crashing the runtime
- if CoinDCX critical fields are absent while Binance reference remains available, the snapshot preserves the reference field but does not promote it to execution truth

### Freshness / validation
- stale tickers are rejected
- zero-valued bid/ask tickers are rejected
- timestamp skew contributes to mismatch penalty

## Conclusion

The repaired data plane now fails closed and isolates provider failure paths in a way that is test-backed rather than implied.
