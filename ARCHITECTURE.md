# ARCHITECTURE — ARUN CoinDCX Futures Signal Bot

## Pipeline

```
EXTERNAL SIGNAL
  → SOURCE QUALITY
  → COINDCX CORRELATION
  → LEAD/LAG
  → COINDCX MISMATCH
  → COINDCX PRICE CONFIRMATION
  → SPREAD/LIQUIDITY
  → RISK/VETO
  → SIGNAL
```

Each layer can reject the signal → NO TRADE. Every rejection is audited.

## Module Layout

```
trader_arun/
├── core/           # config, logger, types, rolling stats, circuit breaker, ring buffers
├── data/           # providers + DataManager + Mismatch + LeadLag
├── microstructure/ # CVD, OBI, absorption, trade clusters, price impact
├── derivatives/    # funding, OI, liquidations, basis
├── alpha/          # S1-S5 strategies + AlphaEngine
├── regime/         # transparent rule-based classifier
├── institutional/  # composite footprint proxy score
├── vetoes/         # V1-V5
├── risk/           # RISK_SCORE gate, position sizer, SL/TP builder
├── portfolio/      # crowding (BTC/ETH beta, correlations, PCA)
├── newsguard/      # free-source news → ALLOW/REDUCE/BLOCK
├── signals/        # generator, Telegram publisher, audit
├── ops/            # storage, safety, operator, health, shutdown
└── backtest/       # walk-forward + DSR
```

## Threading / Concurrency Model

- Single asyncio event loop.
- All providers share one `aiohttp.ClientSession`.
- All blocking writes off-loaded via `asyncio.to_thread`.
- All buffers bounded via `collections.deque(maxlen=N)`.
- All rolling stats incremental O(1) per update.
- No raw tick spam — engine evaluates decisions at `decision_interval_sec` (default 30s).

## Fail-Closed Principles

1. If CoinDCX futures symbol is NOT VERIFIED → NO TRADE.
2. If any required data feed is stale/missing → NO TRADE.
3. If CoinDCX mismatch score ≥ 60 → NO TRADE.
4. If any HARD veto (V1-V5) is triggered → NO TRADE.
5. If RISK_SCORE ≥ 75 → NO TRADE.
6. If news state is BLOCK → NO TRADE.
7. If daily-loss kill switch is active → NO TRADE.
8. If consecutive-loss latch is active → NO TRADE.
9. If manual pause is active → NO TRADE.
10. If news provider is unavailable → BLOCK (fail-safe).

## Persistence

- SQLite with WAL mode.
- Bounded retention (last 100k rows per table).
- Atomic writes via single-writer queue.
- Corruption-tolerant startup (if DB init fails, continues in-memory).
- Operator state and safety latches persist across restarts.

## Health Monitoring

- RSS memory (warning 350 MB, critical 600 MB).
- Event-loop lag (warning 0.5s, critical 2.0s).
- Queue HWM (warning 5000).
- Per-provider latency p95, failures, state.
- Signal/veto counts.

## Operator Commands (Telegram)

```
/status    — overall status
/paused    — show pause state
/pause     — pause new signals
/resume    — resume new signals
/mute      — mute signal output
/unmute    — unmute signal output
/reset     — reset all safety latches
/health    — provider health snapshot
/signals   — recent 5 signals
/risk      — risk gate state
```

## Shutdown

- SIGINT/SIGTERM handled.
- All shutdown hooks called in reverse order.
- Each hook has 10s timeout — cannot block shutdown.
- No post-shutdown reconnects (providers closed cleanly).
