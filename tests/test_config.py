"""Tests for Mosaic's public configuration seam."""

import pytest
from pydantic import ValidationError

from mosaic.config import Environment, LogLevel, Settings


def test_settings_use_safe_typed_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Defaults are suitable for a local process and remain strongly typed."""
    monkeypatch.delenv("MOSAIC_ENVIRONMENT", raising=False)
    monkeypatch.delenv("MOSAIC_LOG_LEVEL", raising=False)

    settings = Settings()

    assert settings.environment is Environment.DEVELOPMENT
    assert settings.log_level is LogLevel.INFO


def test_settings_read_case_insensitive_mosaic_environment_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mosaic-prefixed environment variables override the defaults."""
    monkeypatch.setenv("MOSAIC_ENVIRONMENT", "PRODUCTION")
    monkeypatch.setenv("MOSAIC_LOG_LEVEL", "DEBUG")

    settings = Settings()

    assert settings.environment is Environment.PRODUCTION
    assert settings.log_level is LogLevel.DEBUG


@pytest.mark.parametrize(
    ("name", "value", "field", "expected_hint"),
    [
        ("MOSAIC_ENVIRONMENT", "preview", "environment", "development"),
        ("MOSAIC_LOG_LEVEL", "verbose", "log_level", "debug"),
    ],
)
def test_settings_reject_invalid_environment_values_with_actionable_errors(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
    field: str,
    expected_hint: str,
) -> None:
    """Invalid startup configuration identifies the field and accepted values."""
    monkeypatch.setenv(name, value)

    with pytest.raises(ValidationError) as caught:
        Settings()

    message = str(caught.value)
    assert field in message
    assert expected_hint in message


def test_settings_repr_contains_only_the_explicitly_safe_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Diagnostics expose operational settings without copying process secrets."""
    secret = "must-never-appear"
    monkeypatch.setenv("UNRELATED_PROCESS_SECRET", secret)

    representation = repr(Settings())

    assert representation == "Settings(environment='development', log_level='info')"
    assert secret not in representation
