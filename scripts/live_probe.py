from __future__ import annotations

import asyncio
import json
import time

from trader_arun.core.config import Config
from trader_arun.data.manager import DataManager


async def main() -> None:
    cfg = Config(request_timeout_sec=3.0, max_concurrent_requests=8)
    started = time.time()
    result: dict[str, object] = {
        "started_at": started,
        "coindcx_verified": False,
        "pairs": [],
        "errors": [],
    }
    async with DataManager(cfg) as dm:
        try:
            result["coindcx_verified"] = await dm.verify_futures_universe()
        except Exception as exc:
            result["errors"].append(f"verify_futures_universe: {exc}")
        for pair in cfg.pairs[:3]:
            try:
                snap = await dm.fetch_pair_snapshot(pair)
                result["pairs"].append({
                    "pair": pair.base,
                    "coindcx_ticker": snap.coindcx_ticker is not None,
                    "coindcx_book": snap.coindcx_book is not None,
                    "coindcx_candles": len(snap.coindcx_candles),
                    "external_tickers": sorted(snap.external_tickers.keys()),
                    "external_books": sorted(snap.external_books.keys()),
                    "funding": sorted(snap.funding.keys()),
                    "open_interest": sorted(snap.open_interest.keys()),
                    "coindcx_valid": dm.validate_ticker(snap.coindcx_ticker, "coindcx"),
                })
            except Exception as exc:
                result["errors"].append(f"pair {pair.base}: {exc}")
    result["elapsed_sec"] = round(time.time() - started, 3)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
