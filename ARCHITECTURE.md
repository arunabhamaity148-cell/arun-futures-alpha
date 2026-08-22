# ARUN Architecture

## Top-level flow

```text
CoinDCX / Binance / Hyperliquid / Bybit / Kraken
                ↓
         Normalized provider layer
                ↓
            PairSnapshot
                ↓
  Feature / analyser state construction
                ↓
Mismatch → Regime → Alpha → News → Footprint → Veto → Risk → Sizing → SL/TP
                ↓
        Audited Telegram signal
```

## Critical design constraints

- ARUN is **signal-only**. It never places orders.
- CoinDCX is the **execution-truth venue**.
- External venues are **reference-only** and remain explicitly separated from CoinDCX fields.
- If critical CoinDCX fields fail validation, the system must produce **NO TRADE**.

## Provider layer

### `trader_arun.data.base.Provider`

Implements:
- async HTTP only
- request timeout
- connection timeout
- token-bucket rate limiting
- circuit breaker
- bounded latency history
- health reporting
- fail-closed exceptions

### `trader_arun.data.coindcx.CoinDCXProvider`

Responsibilities:
- parse CoinDCX tickers into canonical `Ticker`
- parse orderbooks with list-or-dict schema support
- fetch candles
- discover futures instruments for exact symbol verification

### `trader_arun.data.manager.DataManager`

Responsibilities:
- own providers
- fetch pair snapshots with bounded concurrency
- isolate provider failures per request
- validate ticker freshness and basic integrity
- expose provider health
- enforce CoinDCX-vs-reference separation

## Snapshot model

`PairSnapshot` carries per-field data without collapsing venue identity:
- `coindcx_ticker`, `coindcx_book`, `coindcx_candles`
- `external_tickers`, `external_books`
- `binance_candles`, `hl_candles`
- `funding`, `open_interest`
- `liquidations`, `trades_by_venue`
- `metadata`

## Mismatch engine

`trader_arun.data.mismatch.MismatchEngine` scores:
- price deviation
- bid deviation
- ask deviation
- spread deviation
- return divergence
- volatility divergence
- liquidity divergence
- timestamp skew
- contract verification penalty
- missing-data penalty

Bands:
- `NORMAL`
- `WATCH`
- `REDUCE`
- `NO_TRADE`

## Signal path

1. verify CoinDCX futures universe status
2. build analyser state from normalized snapshot
3. compute cross-exchange mismatch
4. classify regime
5. evaluate alpha stack `S1..S5`
6. apply NewsGuard state
7. compute institutional footprint
8. apply deterministic veto engine `V1..V5`
9. compute risk
10. size position suggestion
11. build SL/TP and output auditable signal

## Failure model

- one provider failure must not crash the decision loop
- one pair timeout must not block the rest of the watchlist
- missing CoinDCX critical data must fail closed
- optional reference data may enrich context but never silently replace CoinDCX execution truth

## Bounded-state controls

- provider latency histories are bounded
- trade-history stores are bounded deques
- warning aggregation state is bounded by provider/pair keys
- circuit-breaker failure windows are bounded

## Live verification status

Architecture is code-complete and test-covered, but live verification remains environment-limited because exact CoinDCX futures-universe confirmation did not succeed and Binance futures was geo-restricted in this environment.
