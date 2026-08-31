"""Tests for Mosaic's public structured-logging seam."""

import pytest

from mosaic.config import Environment, LogLevel, Settings
from mosaic.log_config import configure_logging
from tests.log_records import decode_json_records


def test_configured_logger_emits_stable_lifecycle_fields(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Lifecycle events are machine-readable and carry safe process context."""
    logger = configure_logging(Settings(environment=Environment.TEST, log_level=LogLevel.INFO))

    logger.info("application_started")

    record = decode_json_records(capsys.readouterr().err)[-1]
    assert record["event"] == "application_started"
    assert record["level"] == "info"
    assert record["environment"] == "test"


def test_configured_logger_honors_the_injected_log_level(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Log verbosity is selected once through injected configuration."""
    logger = configure_logging(
        Settings(environment=Environment.DEVELOPMENT, log_level=LogLevel.ERROR)
    )

    logger.info("application_started")
    logger.error("application_stopped")

    captured = capsys.readouterr().err
    assert len(captured.strip().splitlines()) == 1
    assert "application_started" not in captured
    record = decode_json_records(captured)[-1]
    assert record["event"] == "application_stopped"
    assert record["level"] == "error"


def test_configured_logger_does_not_copy_unrelated_process_secrets(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only allowlisted settings become structured logging context."""
    secret = "must-never-appear"
    monkeypatch.setenv("UNRELATED_PROCESS_SECRET", secret)
    logger = configure_logging(
        Settings(environment=Environment.DEVELOPMENT, log_level=LogLevel.INFO)
    )

    logger.info("application_started")

    captured = capsys.readouterr().err
    assert secret not in captured
