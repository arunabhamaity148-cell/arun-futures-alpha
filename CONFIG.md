# CONFIG — ARUN CoinDCX Futures Signal Bot

All configuration is via environment variables. Copy `.env.example` to `.env` and edit.

## Required (for live signals)

| Variable | Description |
|---|---|
| `ARUN_TELEGRAM_BOT_TOKEN` | Telegram bot token from @BotFather |
| `ARUN_TELEGRAM_CHAT_ID` | Telegram chat ID to send signals to |
| `ARUN_OPERATOR_WHITELIST` | Comma-separated Telegram user IDs authorised for /commands |

## Optional (external data providers — all public/no-key by default)

| Variable | Description |
|---|---|
| `ARUN_COINGLASS_API_KEY` | CoinGlass API key for liquidations (free tier) |
| `ARUN_FRED_API_KEY` | FRED API key for macro data |
| `ARUN_COINDCX_API_KEY` | CoinDCX API key (not needed for public endpoints) |
| `ARUN_COINDCX_API_SECRET` | CoinDCX API secret |

## Engine Tuning

| Variable | Default | Description |
|---|---|---|
| `ARUN_PAPER_MODE` | true | Always true — bot is signal-only |
| `ARUN_LOOP_INTERVAL_SEC` | 5.0 | Main loop sleep |
| `ARUN_DECISION_INTERVAL_SEC` | 30.0 | Signal generation interval |
| `ARUN_SIGNAL_MIN_COOLDOWN_SEC` | 600.0 | Min time between signals per pair |
| `ARUN_ENTRY_VALIDITY_WINDOW_SEC` | 900.0 | Manual execution validity (15 min) |
| `ARUN_MAX_OPEN_SIGNALS` | 3 | Max concurrent open signals |
| `ARUN_MAX_LEVERAGE` | 10.0 | Hard leverage cap |
| `ARUN_DEFAULT_RISK_PCT` | 0.01 | 1% equity risk per trade |
| `ARUN_DAILY_LOSS_KILL_PCT` | 0.03 | 3% daily loss → kill switch |
| `ARUN_CONSECUTIVE_LOSS_LATCH` | 3 | 3 consecutive losses → latch |

## Resource Limits

| Variable | Default | Description |
|---|---|---|
| `ARUN_RSS_WARNING_MB` | 350 | RSS memory warning threshold |
| `ARUN_RSS_CRITICAL_MB` | 600 | RSS memory critical threshold |
| `ARUN_LOG_LEVEL` | INFO | Logging level |

## Storage

| Variable | Default | Description |
|---|---|---|
| `ARUN_SQLITE_PATH` | data/arun.db | SQLite database path |

## Risk Thresholds (defaults; calibration NOT VERIFIED until 90-day live data)

| Variable | Default | Description |
|---|---|---|
| `mismatch_normal_max` | 25.0 | Below = NORMAL band |
| `mismatch_watch_max` | 40.0 | Below = WATCH band |
| `mismatch_no_trade` | 60.0 | At/above = NO_TRADE |
| `correlation_min_15m` | 0.95 | Min CoinDCX corr with primary venue (15m) |
| `spread_max_median_multiple` | 3.0 | Max spread as multiple of median |
| `slippage_max_edge_ratio` | 0.25 | Max slippage as fraction of edge |
| `risk_score_no_trade` | 75.0 | RISK_SCORE ≥ this → NO_TRADE |
| `risk_score_watch` | 60.0 | RISK_SCORE ≥ this → WATCH |
| `risk_score_reduced` | 40.0 | RISK_SCORE ≥ this → REDUCED_RISK |
