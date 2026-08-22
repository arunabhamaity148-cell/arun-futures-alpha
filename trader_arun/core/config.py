"""Configuration loader.

Reads from environment variables and an optional .env file.
Never raises on missing optional keys; raises ConfigError on missing required keys.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

try:
    from dotenv import load_dotenv  # type: ignore
except ImportError:  # pragma: no cover - optional dep
    def load_dotenv(*_args, **_kwargs) -> bool:  # type: ignore
        return False

from .exceptions import ConfigError
from .logger import get_logger

log = get_logger("config")


def _get_int(key: str, default: int) -> int:
    raw = os.environ.get(key)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{key}={raw!r} not int") from exc


def _get_float(key: str, default: float) -> float:
    raw = os.environ.get(key)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{key}={raw!r} not float") from exc


def _get_bool(key: str, default: bool) -> bool:
    raw = os.environ.get(key)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class PairConfig:
    """A single CoinDCX futures pair configuration."""

    rank: int
    base: str
    quote: str
    coindcx_spot_symbol: str
    coindcx_futures_symbol: str  # NOT VERIFIED until CoinDCX instrument-list API confirms
    binance_symbol: str
    hyperliquid_asset: str | None  # None if not listed on Hyperliquid
    kraken_pair: str | None  # None if not on Kraken
    bybit_symbol: str | None
    primary_discovery: str  # "binance" | "bybit" | "hyperliquid" | "kraken"
    best_strategy: str
    primary_veto: str
    notes: str = ""


@dataclass(frozen=True)
class Config:
    """Loaded configuration."""

    # Identity / brand.
    brand: str = "ARUN"

    # Operator.
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    operator_whitelist: tuple[str, ...] = ()

    # CoinDCX.
    coindcx_rest_url: str = "https://api.coindcx.com"
    coindcx_api_key: str = ""
    coindcx_api_secret: str = ""

    # External providers.
    hyperliquid_rest_url: str = "https://api.hyperliquid.xyz"
    hyperliquid_ws_url: str = "wss://api.hyperliquid.xyz/ws"
    kraken_rest_url: str = "https://api.kraken.com"
    kraken_ws_url: str = "wss://ws.kraken.com"
    binance_fapi_rest_url: str = "https://fapi.binance.com"
    binance_fapi_ws_url: str = "wss://fstream.binance.com"
    bybit_rest_url: str = "https://api.bybit.com"
    bybit_ws_url: str = "wss://stream.bybit.com/v5/public/linear"
    coinglass_url: str = "https://open-api-v3.coinglass.com/api/futures"
    coinglass_api_key: str = ""
    gdelt_url: str = "https://api.gdeltproject.org/api/v2"
    fred_url: str = "https://fred.stlouisfed.org/graph/fredgraph.csv"
    fred_api_key: str = ""
    tokenunlocks_url: str = "https://token.unlocks.app"

    # Watchlist (final Top 10 from research; futures symbols NOT VERIFIED).
    pairs: tuple[PairConfig, ...] = field(default_factory=lambda: _default_pairs())

    # Engine.
    loop_interval_sec: float = 5.0
    decision_interval_sec: float = 30.0
    signal_min_cooldown_sec: float = 600.0
    entry_validity_window_sec: float = 900.0  # 15 min realistic manual execution window.
    paper_mode: bool = True  # Always True — bot is signal-only.

    # Data freshness.
    max_data_age_sec: dict[str, int] = field(default_factory=lambda: {
        "ticker": 30,
        "orderbook": 15,
        "candle_1m": 90,
        "candle_5m": 360,
        "funding": 9 * 3600,  # 8h cycle + slack
        "oi": 300,
        "liquidations": 120,
    })

    # Limits.
    max_open_signals: int = 3
    max_correlated_exposure: float = 2.0  # sum of |notional/equity| for high-corr group
    max_leverage: float = 10.0
    default_risk_pct: float = 0.01
    daily_loss_kill_pct: float = 0.03
    consecutive_loss_latch: int = 3

    # Persistence.
    sqlite_path: str = "data/arun.db"

    # Performance.
    rss_warning_mb: int = 350
    rss_critical_mb: int = 600
    event_loop_lag_warning_sec: float = 0.5
    event_loop_lag_critical_sec: float = 2.0
    queue_hwm_warning: int = 5000

    # Misc.
    request_timeout_sec: float = 8.0
    connect_timeout_sec: float = 4.0
    max_concurrent_requests: int = 16
    log_level: str = "INFO"

    # Risk thresholds (defaults; calibration NOT VERIFIED until 90-day live data).
    mismatch_normal_max: float = 25.0
    mismatch_watch_max: float = 40.0
    mismatch_no_trade: float = 60.0
    correlation_min_15m: float = 0.95
    spread_max_median_multiple: float = 3.0
    slippage_max_edge_ratio: float = 0.25
    risk_score_no_trade: float = 75.0
    risk_score_watch: float = 60.0
    risk_score_reduced: float = 40.0

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for f in self.__dataclass_fields__:
            v = getattr(self, f)
            if isinstance(v, tuple) and v and isinstance(v[0], PairConfig):
                out[f] = [p.__dict__ for p in v]
            else:
                out[f] = v
        return out


# Default Top 10 watchlist per research file §22.
# Spot symbols are FACT (CoinDCX 997 markets verified).
# Futures symbols are NOT VERIFIED — CoinDCX Futures instrument-list API was geo-blocked
# from the research sandbox. The bot will attempt to confirm them at startup; if any
# cannot be confirmed, that pair is forced into NO-TRADE.
def _default_pairs() -> tuple[PairConfig, ...]:
    return (
        PairConfig(
            rank=1, base="BTC", quote="USDT",
            coindcx_spot_symbol="B-BTC_USDT",
            coindcx_futures_symbol="BTCUSDT",
            binance_symbol="BTCUSDT",
            hyperliquid_asset="BTC",
            kraken_pair="XXBTZUSD",
            bybit_symbol="BTCUSDT",
            primary_discovery="binance",
            best_strategy="S2/S1",
            primary_veto="V1",
            notes="Depth/price anchor; 100x available",
        ),
        PairConfig(
            rank=2, base="ETH", quote="USDT",
            coindcx_spot_symbol="B-ETH_USDT",
            coindcx_futures_symbol="ETHUSDT",
            binance_symbol="ETHUSDT",
            hyperliquid_asset="ETH",
            kraken_pair="XETHZUSD",
            bybit_symbol="ETHUSDT",
            primary_discovery="binance",
            best_strategy="S2/S3",
            primary_veto="V5",
            notes="2nd depth; ETF-flow sensitive",
        ),
        PairConfig(
            rank=3, base="XRP", quote="USDT",
            coindcx_spot_symbol="B-XRP_USDT",
            coindcx_futures_symbol="XRPUSDT",
            binance_symbol="XRPUSDT",
            hyperliquid_asset="XRP",
            kraken_pair="XXRPZUSD",
            bybit_symbol="XRPUSDT",
            primary_discovery="binance",
            best_strategy="S1/S2",
            primary_veto="V3",
            notes="HL OI ~$158.7M snapshot",
        ),
        PairConfig(
            rank=4, base="DOGE", quote="USDT",
            coindcx_spot_symbol="B-DOGE_USDT",
            coindcx_futures_symbol="DOGEUSDT",
            binance_symbol="DOGEUSDT",
            hyperliquid_asset="DOGE",
            kraken_pair="XDGUSD",
            bybit_symbol="DOGEUSDT",
            primary_discovery="hyperliquid",
            best_strategy="S1/S3",
            primary_veto="V4",
            notes="HL OI ~$727M snapshot — best cascade signal source",
        ),
        PairConfig(
            rank=5, base="ADA", quote="USDT",
            coindcx_spot_symbol="B-ADA_USDT",
            coindcx_futures_symbol="ADAUSDT",
            binance_symbol="ADAUSDT",
            hyperliquid_asset="ADA",
            kraken_pair="ADAUSD",
            bybit_symbol="ADAUSDT",
            primary_discovery="binance",
            best_strategy="S1",
            primary_veto="V3",
            notes="Steady OI; retail favourite",
        ),
        PairConfig(
            rank=6, base="SOL", quote="USDT",
            coindcx_spot_symbol="B-SOL_USDT",
            coindcx_futures_symbol="SOLUSDT",
            binance_symbol="SOLUSDT",
            hyperliquid_asset="SOL",
            kraken_pair="SOLUSD",
            bybit_symbol="SOLUSDT",
            primary_discovery="binance",
            best_strategy="S2",
            primary_veto="V1",
            notes="HL OI thin (~$4.8M); use Binance/Bybit as primary",
        ),
        PairConfig(
            rank=7, base="SUI", quote="USDT",
            coindcx_spot_symbol="B-SUI_USDT",
            coindcx_futures_symbol="SUIUSDT",
            binance_symbol="SUIUSDT",
            hyperliquid_asset="SUI",
            kraken_pair=None,
            bybit_symbol="SUIUSDT",
            primary_discovery="bybit",
            best_strategy="S8/S1",
            primary_veto="V3/V5",
            notes="Unlock-alpha; moderate OI",
        ),
        PairConfig(
            rank=8, base="BNB", quote="USDT",
            coindcx_spot_symbol="B-BNB_USDT",
            coindcx_futures_symbol="BNBUSDT",
            binance_symbol="BNBUSDT",
            hyperliquid_asset=None,
            kraken_pair=None,
            bybit_symbol="BNBUSDT",
            primary_discovery="binance",
            best_strategy="S9",
            primary_veto="V3",
            notes="Binance-ecosystem liquidity",
        ),
        PairConfig(
            rank=9, base="PEPE", quote="USDT",
            coindcx_spot_symbol="B-PEPE_USDT",
            coindcx_futures_symbol="1000PEPEUSDT",
            binance_symbol="1000PEPEUSDT",
            hyperliquid_asset="PEPE",
            kraken_pair=None,
            bybit_symbol="1000PEPEUSDT",
            primary_discovery="binance",
            best_strategy="S1",
            primary_veto="V3/V4",
            notes="1000x prefix symbol mapping (NOT VERIFIED on CoinDCX)",
        ),
        PairConfig(
            rank=10, base="LINK", quote="USDT",
            coindcx_spot_symbol="B-LINK_USDT",
            coindcx_futures_symbol="LINKUSDT",
            binance_symbol="LINKUSDT",
            hyperliquid_asset="LINK",
            kraken_pair="LINKUSD",
            bybit_symbol="LINKUSDT",
            primary_discovery="binance",
            best_strategy="S3",
            primary_veto="V2",
            notes="DeFi-core; HL funding +0.00011/8h",
        ),
    )


def load_config(env_file: str | None = ".env") -> Config:
    """Load configuration from env file + environment variables."""
    if env_file:
        load_dotenv(env_file, override=False)

    pairs = _default_pairs()
    operator_whitelist_raw = os.environ.get("ARUN_OPERATOR_WHITELIST", "")
    operator_whitelist = tuple(
        t.strip() for t in operator_whitelist_raw.split(",") if t.strip()
    )

    cfg = Config(
        telegram_bot_token=os.environ.get("ARUN_TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.environ.get("ARUN_TELEGRAM_CHAT_ID", ""),
        operator_whitelist=operator_whitelist,
        coindcx_api_key=os.environ.get("ARUN_COINDCX_API_KEY", ""),
        coindcx_api_secret=os.environ.get("ARUN_COINDCX_API_SECRET", ""),
        coinglass_api_key=os.environ.get("ARUN_COINGLASS_API_KEY", ""),
        fred_api_key=os.environ.get("ARUN_FRED_API_KEY", ""),
        sqlite_path=os.environ.get("ARUN_SQLITE_PATH", "data/arun.db"),
        loop_interval_sec=_get_float("ARUN_LOOP_INTERVAL_SEC", 5.0),
        decision_interval_sec=_get_float("ARUN_DECISION_INTERVAL_SEC", 30.0),
        signal_min_cooldown_sec=_get_float("ARUN_SIGNAL_MIN_COOLDOWN_SEC", 600.0),
        entry_validity_window_sec=_get_float("ARUN_ENTRY_VALIDITY_WINDOW_SEC", 900.0),
        paper_mode=_get_bool("ARUN_PAPER_MODE", True),
        max_open_signals=_get_int("ARUN_MAX_OPEN_SIGNALS", 3),
        max_leverage=_get_float("ARUN_MAX_LEVERAGE", 10.0),
        default_risk_pct=_get_float("ARUN_DEFAULT_RISK_PCT", 0.01),
        daily_loss_kill_pct=_get_float("ARUN_DAILY_LOSS_KILL_PCT", 0.03),
        consecutive_loss_latch=_get_int("ARUN_CONSECUTIVE_LOSS_LATCH", 3),
        rss_warning_mb=_get_int("ARUN_RSS_WARNING_MB", 350),
        rss_critical_mb=_get_int("ARUN_RSS_CRITICAL_MB", 600),
        log_level=os.environ.get("ARUN_LOG_LEVEL", "INFO").upper(),
        pairs=pairs,
    )
    set_log_level_safe(cfg.log_level)
    log.x_info("config loaded", extras={
        "paper_mode": cfg.paper_mode,
        "pairs_count": len(cfg.pairs),
        "max_leverage": cfg.max_leverage,
        "operator_whitelist_count": len(cfg.operator_whitelist),
    })
    return cfg


def set_log_level_safe(level: str) -> None:
    from .logger import set_log_level as _sll
    try:
        _sll(level)
    except (TypeError, ValueError):
        _sll("INFO")
