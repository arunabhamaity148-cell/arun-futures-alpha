# Soak Test Results

## 15-minute soak requirement

**Status: NOT VERIFIED — ENVIRONMENT LIMITATION**

A truthful 15-minute soak result was not claimed because the live venue environment was degraded:
- Binance futures reference endpoints returned `HTTP 451`
- CoinDCX futures-universe verification remained unavailable
- CoinDCX critical ticker verification did not complete successfully

## What was run instead

A 60-second live smoke run was executed to validate:
- no crash under degraded venue access
- fail-closed signal suppression
- low observed event-loop lag under async timeout/circuit-break behaviour
- stable task count and RSS during the observed run

## Required future soak plan

Run in the intended deployment network with:
- exact CoinDCX futures endpoints confirmed
- Binance or approved reference venue accessible
- final watchlist configured
- Telegram enabled with operator monitoring

Record at minimum:
- total events
- events/sec
- reconnects by provider
- stale core / optional counts
- provider failures
- event-loop lag p95 / max
- RSS at 0/5/10/15m and peak
- task count / queue HWM
- signal and veto counts
- unexpected exceptions
- shutdown behaviour
