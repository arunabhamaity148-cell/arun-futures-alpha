# Test Results

## Automated suite

- Command: `pytest -q`
- Result: **155 passed**
- Failed: **0**
- Skipped: **0**
- Warnings: **0 test warnings requiring action**

## Regression tests added during audit

`tests/test_data_pipeline_regressions.py`
- CoinDCX orderbook dict payload parsing
- exact CoinDCX futures-symbol verification logic
- provider isolation when CoinDCX critical call times out
- mismatch timestamp-skew penalty

## Existing coverage areas that now pass

- CoinDCX ticker parsing
- circuit breaker behaviour
- fault injection
- mismatch engine
- NewsGuard
- veto engine
- regime classifier
- risk gate
- signal generator
- Telegram formatting
- storage
- shutdown
- portfolio crowding
- backtest metrics

## Interpretation

The codebase is now internally consistent enough for deterministic unit and integration-style tests to execute end to end. Test success does **not** imply live market readiness or profitability.
