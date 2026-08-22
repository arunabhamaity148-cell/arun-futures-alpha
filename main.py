"""ARUN entry point — `python main.py`."""
from __future__ import annotations

import asyncio
import sys

from trader_arun.app import ARUNApp
from trader_arun.core.config import load_config
from trader_arun.core.logger import get_logger

log = get_logger("main")


async def amain() -> int:
    cfg = load_config()
    async with ARUNApp(cfg) as app:
        await app.run_forever()
    return 0


def main() -> int:
    try:
        return asyncio.run(amain())
    except KeyboardInterrupt:
        log.x_warn("interrupted by user")
        return 130


if __name__ == "__main__":
    sys.exit(main())
