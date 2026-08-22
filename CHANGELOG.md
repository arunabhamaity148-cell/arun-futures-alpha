# Changelog

## Audit repair release

### Added
- `trader_arun.data` package
  - `base.py`
  - `coindcx.py`
  - `manager.py`
  - `leadlag.py`
  - `mismatch.py`
- `tests/test_data_pipeline_regressions.py`
- `scripts/live_probe.py`
- `scripts/smoke_test.py`
- `ARCHITECTURE_CHANGES.md`
- `SOAK_TEST_RESULTS.md`
- `FAULT_INJECTION_RESULTS.md`

### Changed
- repaired `trader_arun/ops/health.py` RSS path
- refreshed README and operational documentation
- added warning throttling for repetitive provider fetch failures

### Verified
- `pytest -q` passes with **155 passed**

### Not verified
- live CoinDCX futures-universe confirmation
- Binance futures reference access in this environment
- 15-minute live soak
- profitability / walk-forward performance
