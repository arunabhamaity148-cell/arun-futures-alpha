"""Data provider package — real REST + WS providers, fail-closed."""
from .base import Provider, ProviderRegistry, SchemaValidator

__all__ = ["Provider", "ProviderRegistry", "SchemaValidator"]
