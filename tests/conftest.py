"""Pytest configuration."""
import asyncio
import os
import sys
from pathlib import Path

# Ensure the package is importable.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Disable paper mode for tests so we exercise all paths.
os.environ.setdefault("ARUN_PAPER_MODE", "true")
# Disable Telegram in tests by default.
os.environ.setdefault("ARUN_TELEGRAM_BOT_TOKEN", "")
os.environ.setdefault("ARUN_TELEGRAM_CHAT_ID", "")
# Use temp SQLite path.
os.environ.setdefault("ARUN_SQLITE_PATH", ":memory:")


def pytest_collection_modifyitems(config, items):
    """Mark all async tests with asyncio automatically."""
    for item in items:
        if asyncio.iscoroutinefunction(getattr(item, "function", None)):
            item.add_marker(getattr(__import__("pytest"), "mark").asyncio)
