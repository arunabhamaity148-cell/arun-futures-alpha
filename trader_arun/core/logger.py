"""Structured single-line logger for ARUN.

Emits single-line JSON-ish records that are easy to grep/ship.
Never logs raw secrets, raw ticks, or progress bars.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any

_CONFIGURED = False
_LEVEL = logging.INFO

# Secrets we always redact if they accidentally appear.
_SECRET_KEYS = {
    "telegram_bot_token",
    "telegram_chat_id",
    "coindcx_api_key",
    "coindcx_api_secret",
    "binance_api_key",
    "binance_api_secret",
    "bybit_api_key",
    "bybit_api_secret",
    "fred_api_key",
    "password",
    "secret",
    "token",
}


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("***REDACTED***" if k.lower() in _SECRET_KEYS else _redact(v))
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(v) for v in value]
    return value


class _StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": int(time.time()),
            "lvl": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Attach structured extras if present.
        for k, v in getattr(record, "_arun_extras", {}).items():
            payload[k] = _redact(v)
        # If exception present, append short repr (no traceback spam in production).
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)[:600]
        return json.dumps(payload, ensure_ascii=False, default=str)


def _configure_once() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_StructuredFormatter())
    root = logging.getLogger("arun")
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(_LEVEL)
    root.propagate = False
    _CONFIGURED = True


def set_log_level(level: int | str) -> None:
    global _LEVEL
    _LEVEL = level if isinstance(level, int) else logging.getLevelName(level.upper())
    logging.getLogger("arun").setLevel(_LEVEL)
    _configure_once()


def get_logger(name: str = "arun") -> logging.Logger:
    _configure_once()
    if not name.startswith("arun"):
        name = f"arun.{name}"
    logger = logging.getLogger(name)
    logger.setLevel(_LEVEL)

    def _log_with_extras(self, level, msg, *args, **kwargs):
        extras = kwargs.pop("extras", None)
        if extras:
            record_extra = {"_arun_extras": extras}
        else:
            record_extra = {}
        self._log(level, msg, args, extra=record_extra)

    if not hasattr(logger, "_arun_patched"):
        # Bind helpers without clobbering stdlib methods.
        logger.x = lambda level, msg, **kw: _log_with_extras(logger, level, msg, **kw)
        logger.x_info = lambda msg, **kw: _log_with_extras(logger, logging.INFO, msg, **kw)
        logger.x_warn = lambda msg, **kw: _log_with_extras(logger, logging.WARNING, msg, **kw)
        logger.x_error = lambda msg, **kw: _log_with_extras(logger, logging.ERROR, msg, **kw)
        logger.x_debug = lambda msg, **kw: _log_with_extras(logger, logging.DEBUG, msg, **kw)
        logger._arun_patched = True
    return logger


# Silence noisy libs by default.
for _n in ("urllib3", "asyncio", "aiohttp.access"):
    logging.getLogger(_n).setLevel(logging.WARNING)

# Env-driven level override.
_env_level = os.environ.get("ARUN_LOG_LEVEL", "").upper()
if _env_level:
    try:
        set_log_level(_env_level)
    except (TypeError, ValueError):
        pass
