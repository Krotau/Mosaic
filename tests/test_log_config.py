"""Tests for Mosaic's public structured-logging seam."""

import json
from typing import Any

import pytest

from mosaic.config import Environment, LogLevel, Settings
from mosaic.log_config import configure_logging


def _last_json_record(captured: str) -> dict[str, Any]:
    """Decode the most recently emitted structured record."""
    decoded: object = json.loads(captured.strip().splitlines()[-1])
    if not isinstance(decoded, dict):
        raise AssertionError("structured log record must be a JSON object")
    return {str(key): value for key, value in decoded.items()}


def test_configured_logger_emits_stable_lifecycle_fields(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Lifecycle events are machine-readable and carry safe process context."""
    logger = configure_logging(Settings(environment=Environment.TEST, log_level=LogLevel.INFO))

    logger.info("application_started")

    record = _last_json_record(capsys.readouterr().err)
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
    record = _last_json_record(captured)
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
