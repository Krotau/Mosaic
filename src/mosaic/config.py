"""Validated, environment-backed application configuration."""

from enum import StrEnum

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """Supported Mosaic runtime environments."""

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class LogLevel(StrEnum):
    """Supported application logging thresholds."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class Settings(BaseSettings):
    """Application settings loaded once at the composition root.

    Environment variable names use the ``MOSAIC_`` prefix. The representation
    deliberately allowlists operationally safe fields instead of reflecting all
    model fields, so future secret settings cannot leak into diagnostics by
    default.
    """

    model_config = SettingsConfigDict(
        env_prefix="MOSAIC_",
        case_sensitive=False,
        extra="forbid",
        frozen=True,
    )

    environment: Environment = Environment.DEVELOPMENT
    log_level: LogLevel = LogLevel.INFO

    @field_validator("environment", "log_level", mode="before")
    @classmethod
    def _normalize_enum_case(cls, value: object) -> object:
        """Accept conventional upper- or lower-case environment values."""
        if isinstance(value, str):
            return value.lower()
        return value

    def __repr__(self) -> str:
        """Return a stable representation containing only safe fields."""
        return (
            f"Settings(environment={self.environment.value!r}, log_level={self.log_level.value!r})"
        )


__all__ = ["Environment", "LogLevel", "Settings"]
