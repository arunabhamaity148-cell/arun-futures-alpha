# ROOT CAUSE REPORT — ARUN

This document explains the root causes of design decisions and known limitations.

## Why CoinDCX Futures Symbols Are NOT VERIFIED

**Root cause:** The CoinDCX Futures instrument-list API (testnet-docs.dcxstage.com)
was geo-blocked from the research sandbox. The public spot API
(`api.coindcx.com/exchange/v1/markets_details`) was accessible and returned 997
verified markets, but the futures-specific endpoints did not respond.

**Impact:** All 10 watchlist futures symbols (BTCUSDT, ETHUSDT, etc.) are marked
NOT VERIFIED. The bot attempts to verify them at startup via
`CoinDCXProvider.verify_futures_universe()`. If verification fails, the
`SignalGenerator` is constructed with `coindcx_futures_verified=False` and
**every signal is rejected** with audit reason `"coindcx futures universe NOT
VERIFIED — fail-closed"`.

**Mitigation:** Once deployed to a non-geo-blocked environment, the bot will
automatically verify the universe on first start and begin emitting signals
(if all other gates pass).

## Why CoinDCX Funding/OI Are NOT VERIFIED

**Root cause:** The public CoinDCX API docs (docs.coindcx.com) do not list
funding rate or open-interest endpoints. Only the futures-specific API exposes
these, and that API is geo-blocked (see above).

**Impact:** The mismatch engine's `fund_rel` and `oi_rel` components are set
to 50 (neutral). The funding/OI context in Telegram signals will read
`"funding NOT VERIFIED (CoinDCX public API)"`.

**Mitigation:** External funding/OI from Hyperliquid/Binance/Bybit are used as
proxies. The S3 (funding/OI unwind) strategy uses these external values
combined with CoinDCX price-action confirmation. This is a proxy, not a
direct measurement — calibration against live CoinDCX futures data is required
before going live with real money.

## Why Backtest Results Are NOT VERIFIED

**Root cause:** No historical CoinDCX futures data is available in this
environment. The backtest framework is implemented structurally (walk-forward,
purged CV, Deflated Sharpe Ratio, bootstrap CIs, cost model) but cannot
produce verified performance numbers without historical data.

**Impact:** All performance metrics (win rate, Sharpe, Sortino, MaxDD, etc.)
are NOT VERIFIED. The bot makes no profitability claims.

**Mitigation:** The framework supports replay evaluation. To verify
performance:
1. Capture 2+ weeks of CoinDCX futures data via the live paper-trading mode.
2. Export the audit log.
3. Replay-evaluate each signal against realised forward returns.
4. Apply the Deflated Sharpe Ratio correction for multiple-hypothesis testing.

## Why PEPE Symbol Is "1000PEPEUSDT"

**Root cause:** Binance uses the `1000PEPE` prefix for PEPE futures (because
PEPE has 6 decimals and the contract size is 1000 PEPE per contract). The
research file notes this as "Binance-style 1000x prefix possible" but
NOT VERIFIED on CoinDCX.

**Impact:** If CoinDCX uses a different symbol (e.g. `PEPEUSDT`), the
`verify_futures_universe()` check will reject PEPE signals until the
`PairConfig.coindcx_futures_symbol` is corrected.

**Mitigation:** Once CoinDCX futures API is accessible, run
`verify_futures_universe()` and update the symbol in `trader_arun/core/config.py`
if needed.

## Why Manual Telegram Execution Constraint

**Root cause:** Telegram delivery + human reading + manual order entry on
CoinDCX takes 30s–5min. Sub-second alpha (lead/lag < 30s) is not actionable.

**Impact:** The S2 (lead/lag) strategy uses 5m-15m windows, not 1s windows.
The `entry_validity_window_sec` defaults to 900s (15 min). Signals expire
after this window.

**Mitigation:** The S2 strategy only fires when the lead is sustained for
multiple minutes, not seconds. The lead/lag analyser uses 1m candles, not
raw ticks.

## Why HMM Is Not Used for Regime

**Root cause:** HMM requires iterative EM training, which has convergence
races and parameter instability on the hot path. A transparent rule-based
classifier is more debuggable and predictable.

**Impact:** The regime engine uses t-stat + vol-ratio + dislocation +
cascade + news rules. It is less expressive than HMM but more predictable
and easier to audit.

## Why SQLite Instead of PostgreSQL

**Root cause:** SQLite with WAL mode is sufficient for single-bot deployment
(< 100 writes/sec, < 1 GB data). PostgreSQL adds operational complexity
(database server, credentials, network) without proportional benefit.

**Impact:** No network database calls. All writes are local. Bounded
retention (last 100k rows per table) keeps the DB small.

## Why Single Shared aiohttp.ClientSession

**Root cause:** Opening a new session per request creates connection-pool
fragmentation and TCP overhead. A single shared session reuses connections
and respects HTTP keep-alive.

**Impact:** All providers share one connection pool. Rate limiters are
per-provider to respect each venue's limits.

## Why No LLM Calls in the Engine

**Root cause:** LLM calls have unbounded latency (1-30s) and cost. They
cannot be on the hot path of a real-time signal engine.

**Impact:** All alpha is computed from measurable market microstructure
and derivatives data. No sentiment analysis, no LLM predictions.

**Mitigation:** NewsGuard uses rule-based classification (substring matching
on headlines) rather than LLM-based sentiment. This is faster, cheaper,
and more debuggable.
