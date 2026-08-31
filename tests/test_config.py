"""Tests for Mosaic's public configuration seam."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from mosaic.config import Environment, LogLevel, Settings

_EXAMPLE_ENV = Path(__file__).resolve().parents[1] / ".env.example"


@pytest.fixture(autouse=True)
def _run_without_repository_dotenv(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Keep every settings test independent of a contributor's local dotenv file."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MOSAIC_ENVIRONMENT", raising=False)
    monkeypatch.delenv("MOSAIC_LOG_LEVEL", raising=False)


def test_settings_use_safe_typed_defaults() -> None:
    """Defaults are suitable for a local process and remain strongly typed."""
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


def test_settings_read_local_dotenv_values(tmp_path: Path) -> None:
    """Non-default local values are loaded from ``.env``."""
    tmp_path.joinpath(".env").write_text(
        "MOSAIC_ENVIRONMENT=production\nMOSAIC_LOG_LEVEL=warning\n",
        encoding="utf-8",
    )

    settings = Settings()

    assert settings.environment is Environment.PRODUCTION
    assert settings.log_level is LogLevel.WARNING


def test_documented_env_example_can_be_copied_and_loaded(tmp_path: Path) -> None:
    """The exact committed example is a valid local dotenv file."""
    tmp_path.joinpath(".env").write_text(
        _EXAMPLE_ENV.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    settings = Settings()

    assert settings.environment is Environment.DEVELOPMENT
    assert settings.log_level is LogLevel.INFO


def test_environment_variables_override_the_local_dotenv_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Deployment environment values retain precedence over local dotenv values."""
    tmp_path.joinpath(".env").write_text(
        "MOSAIC_ENVIRONMENT=development\nMOSAIC_LOG_LEVEL=info\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MOSAIC_ENVIRONMENT", "production")
    monkeypatch.setenv("MOSAIC_LOG_LEVEL", "error")

    settings = Settings()

    assert settings.environment is Environment.PRODUCTION
    assert settings.log_level is LogLevel.ERROR


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
