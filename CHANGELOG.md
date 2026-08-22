# CHANGELOG — ARUN

## v1.0.0 (2026-08-22)

### Initial release

**Core engines implemented:**
- Cross-exchange lead/lag (S2)
- Liquidation-cascade exhaustion (S1)
- Funding/OI crowding unwind (S3)
- Order-book absorption / CVD divergence (S4)
- Perp-basis vs spot convergence (S5)

**Top 5 veto engine:**
- V1 Cross-exchange contradiction (hard veto ≥60 bp deviation)
- V2 OI/funding contradiction (hard veto when persistent ≥6h)
- V3 Liquidity vacuum (hard veto on thin book / wide spread)
- V4 Liquidation exhaustion / incomplete cascade (hard veto)
- V5 Macro/news contradiction (hard veto on BLOCK)

**Data providers (all real, no mocks):**
- CoinDCX (REST: ticker, orderbook, candles, trades, futures verification)
- Hyperliquid (REST: allMids, metaAndAssetCtxs, l2Book, candlesSnapshot)
- Kraken (REST: Ticker, Depth, OHLC)
- Binance Futures (REST: bookTicker, depth, klines, premiumIndex, openInterest)
- Bybit v5 (REST: tickers, orderbook, kline, funding, OI)
- CoinGlass (REST: liquidations, funding — requires API key)
- GDELT (REST: news search)
- FRED (REST: macro series)
- TokenUnlocks (REST: unlock calendar)

**Risk / portfolio:**
- RISK_SCORE (0-100) with fail-closed NO_TRADE on missing inputs or news BLOCK
- Risk-based position sizing (leverage cap, book depth cap, correlated cap)
- ATR-based SL/TP with R:R ≥ 1.5 minimum
- Portfolio crowding (BTC/ETH beta, PCA concentration, directional exposure)

**Operations:**
- SQLite WAL storage with bounded retention
- 8 persistent safety latches (daily loss, consecutive loss, volatility,
  data quality, exchange outage, mismatch, network degraded, manual pause)
- 10 operator Telegram commands
- Health monitor (RSS, event-loop lag, queue HWM, task count)
- Graceful shutdown with reverse-order hooks

**Backtest framework:**
- Walk-forward (70/30 split)
- Bootstrap CIs (1000 resamples)
- Deflated Sharpe Ratio (Bailey & López de Prado 2014)
- Cost model (taker fee, slippage, funding, latency, partial fills, outages)

**Testing:**
- 151 unit + integration + fault-injection tests, all passing

**Documentation:**
- README, ARCHITECTURE, CONFIG, ROOT_CAUSE_REPORT, TEST_RESULTS,
  RUNTIME_VERIFICATION, PRODUCTION_READINESS, CHANGELOG

### Known Limitations (NOT VERIFIED)

- CoinDCX Futures instrument list (geo-blocked during research)
- CoinDCX funding/OI endpoints (not in public docs)
- CoinDCX fee/slippage structure (app-side schedule)
- Backtest performance numbers (no historical CoinDCX futures data)
- Transfer score (requires 2-4 weeks live calibration)
- Mismatch threshold calibration (defaults used; 95th/99th pct pending)
