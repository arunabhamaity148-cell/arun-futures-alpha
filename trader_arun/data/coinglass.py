"""CoinGlass provider — liquidations + funding (free tier).

The free public CoinGlass endpoints are rate-limited and the open API requires
a key for v3. If the key is missing or the endpoint fails, the provider returns
empty lists and the bot treats liquidations/funding as NOT VERIFIED.

This provider never fabricates data — it returns [] if the request fails.
"""
from __future__ import annotations

from typing import Any

from ..core.exceptions import ProviderError, ProviderUnavailable, SchemaError
from ..core.time_utils import now_ts
from ..core.types import FundingRate, Liquidation, OpenInterest, Side
from .base import Provider


class CoinGlassProvider(Provider):
    name = "coinglass"

    def __init__(self, base_url: str, api_key: str = "", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._verified = bool(api_key)

    async def get_liquidations(self, symbol: str, limit: int = 50) -> list[Liquidation]:
        """Returns recent liquidations across venues for `symbol`.

        Returns [] if the API key is missing or the request fails — never
        fabricates liquidation events.
        """
        if not self._api_key:
            return []
        try:
            payload = await self._request_with_retry(
                "GET", f"{self._base_url}/liquidation/list",
                params={"symbol": symbol, "limit": limit},
                headers={"CG-API-KEY": self._api_key},
            )
        except (ProviderError, ProviderUnavailable, SchemaError):
            return []
        if not isinstance(payload, dict):
            return []
        rows = payload.get("data", [])
        if not isinstance(rows, list):
            return []
        out: list[Liquidation] = []
        for row in rows:
            try:
                side = Side.LONG if str(row.get("side", "")).upper() in ("LONG", "BUY") else Side.SHORT
                out.append(Liquidation(
                    venue=str(row.get("exchangeName", "coinglass")),
                    symbol=symbol,
                    side=side,
                    price=float(row["price"]),
                    size_usd=float(row.get("valueUsd", row.get("size", 0.0))),
                    timestamp=float(row.get("time", row.get("createdAt", 0))),
                ))
            except (KeyError, TypeError, ValueError):
                continue
        return out

    async def get_funding(self, symbol: str) -> FundingRate | None:
        if not self._api_key:
            return None
        try:
            payload = await self._request_with_retry(
                "GET", f"{self._base_url}/funding/ohlc-history",
                params={"symbol": symbol, "limit": 1},
                headers={"CG-API-KEY": self._api_key},
            )
        except (ProviderError, ProviderUnavailable, SchemaError):
            return None
        if not isinstance(payload, dict):
            return None
        data = payload.get("data", [])
        if not isinstance(data, list) or not data:
            return None
        row = data[0]
        try:
            return FundingRate(
                venue="coinglass",
                symbol=symbol,
                rate=float(row.get("fundingRate", 0.0) or 0.0),
                next_funding_time=float(row.get("nextFundingTime", 0) or 0),
                timestamp=float(row.get("time", now_ts())),
            )
        except (TypeError, ValueError):
            return None

    @property
    def verified(self) -> bool:
        return self._verified
