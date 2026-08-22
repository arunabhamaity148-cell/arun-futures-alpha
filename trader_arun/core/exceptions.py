"""Custom exception hierarchy for ARUN."""
from __future__ import annotations


class ARUNError(Exception):
    """Base class for all ARUN errors."""


class ConfigError(ARUNError):
    """Configuration loading or validation failed."""


class ProviderError(ARUNError):
    """Generic data provider error."""


class ProviderUnavailable(ProviderError):
    """Provider is unreachable or in circuit-break state."""


class SchemaError(ProviderError):
    """Provider payload failed schema validation."""


class StaleDataError(ProviderError):
    """Data freshness check failed."""


class DataQualityError(ARUNError):
    """Data failed quality gate (NaN, impossible price, bad spread, etc.)."""


class RiskViolation(ARUNError):
    """Risk gate returned NO_TRADE."""


class VetoTriggered(ARUNError):
    """A veto engine gate returned HARD veto."""


class ShutdownRequested(ARUNError):
    """Operator or signal requested graceful shutdown."""
