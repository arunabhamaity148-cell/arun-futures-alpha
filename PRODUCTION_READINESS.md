# PRODUCTION READINESS — ARUN

## Status: CONDITIONAL READY

The bot is structurally production-ready (clean code, tests, fail-closed
design, bounded resources, graceful shutdown). However, **two preconditions
must be met before live deployment**:

### 1. CoinDCX Futures Universe Verification (NOT VERIFIED)

The CoinDCX Futures instrument-list API was geo-blocked during research. The
bot's `verify_futures_universe()` method will attempt verification at startup.
If it fails, ALL signals are rejected (fail-closed).

**Action:** Deploy to a non-geo-blocked VPS (India region recommended) and
verify the futures universe is accessible. If any of the 10 watchlist
symbols cannot be confirmed, update `trader_arun/core/config.py` with the
correct CoinDCX futures symbol.

### 2. Calibration (NOT VERIFIED)

All thresholds (mismatch bands, risk score bands, veto thresholds) use
default values from the research file. These are NOT calibrated against
live CoinDCX futures data.

**Action:** Run the bot in paper mode for 2-4 weeks, recording:
- Mismatch score percentiles (replace default bands with 95th/99th pct)
- Spread percentiles (per pair)
- Lead/lag distributions (per pair)
- Cascade index distributions
- Funding/OI z-score distributions

After calibration, update `trader_arun/core/config.py` and
`trader_arun/data/mismatch.py` thresholds.

## Pre-Deployment Checklist

- [ ] `.env` configured with Telegram bot token + chat ID
- [ ] `ARUN_OPERATOR_WHITELIST` set to authorised Telegram user IDs
- [ ] `ARUN_PAPER_MODE=true` (initial deployment — verify signals first)
- [ ] `ARUN_MAX_LEVERAGE` set conservatively (e.g. 5.0, not 10.0)
- [ ] `ARUN_DEFAULT_RISK_PCT` set conservatively (e.g. 0.005 = 0.5%)
- [ ] `ARUN_DAILY_LOSS_KILL_PCT` set (e.g. 0.02 = 2%)
- [ ] VPS region is NOT geo-blocked by Binance/Bybit/CoinDCX
- [ ] SQLite DB path is on persistent storage
- [ ] Log level set to INFO (not DEBUG — too verbose in production)
- [ ] Operator is monitoring Telegram for the first 24h

## Hard Caps (enforced by code)

- Max leverage: `ARUN_MAX_LEVERAGE` (default 10.0)
- Max notional: hardcoded in `PositionSizer` ($50,000)
- Max open signals: `ARUN_MAX_OPEN_SIGNALS` (default 3)
- Max correlated exposure: `ARUN_MAX_CORRELATED_EXPOSURE` (default 2.0× equity)
- Daily loss kill: `ARUN_DAILY_LOSS_KILL_PCT` (default 3%)
- Consecutive loss latch: `ARUN_CONSECUTIVE_LOSS_LATCH` (default 3)
- Book impact cap: 5% of 5% depth (hardcoded)
- WebSocket reconnect attempts: 50 max (then UNAVAILABLE state)
- Provider failure threshold: 5 failures in 60s → circuit OPEN

## What The Bot Does NOT Do

- Place live exchange orders (signal-only by design)
- Use LLM/AI for predictions
- Use generic RSI/MACD/EMA-crossover as core alpha
- Use Bollinger Bands, support/resistance, FVG, Order Blocks as core alpha
- Claim specific institutions bought/sold (uses "large/informed participant
  activity proxy" terminology)
- Fabricate backtest numbers
- Fabricate CoinDCX futures symbols
- Fabricate funding/OI/liquidation data

## What The Bot Does

- Generates LONG/SHORT signals with full entry/SL/TP/risk/confidence/grade
- Audits every decision (including rejections)
- Persists signals, outcomes, operator state, safety state to SQLite
- Provides 10 operator Telegram commands
- Fail-closes on any uncertainty
- Bounds RAM and CPU strictly
- Recovers gracefully from network/provider failures
- Shuts down cleanly on SIGINT/SIGTERM

## Recommendation

1. **Phase 0 (week 1-2):** Deploy in paper mode. Verify CoinDCX futures
   universe. Record mismatch/spread/lead-lag distributions.
2. **Phase 1 (week 3-4):** Calibrate thresholds. Run paper mode continuously.
   Verify 200+ paper signals, ≥80% of which confirm on CoinDCX within the
   validity window.
3. **Phase 2 (week 5-6):** If transfer_score ≥ 70 and net expectancy > 0
   after fees/slippage/funding, switch to live mode with minimum size (1%
   risk per trade).
4. **Phase 3 (week 7+):** Scale size gradually only for pairs/strategies
   with measured transfer_score ≥ 80.

**If any of the 4 conditions in research §25.11 are not met → REAL MONEY
NO-GO.**
