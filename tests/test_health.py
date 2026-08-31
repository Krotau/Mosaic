"""Behavioral tests for Mosaic's public ASGI application seam."""

import asyncio
import json
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from mosaic.app import app, create_app
from mosaic.config import Environment, LogLevel, Settings


def _test_settings() -> Settings:
    """Build explicit deterministic settings for application tests."""
    return Settings(environment=Environment.TEST, log_level=LogLevel.INFO)


async def _request_health(application: FastAPI) -> httpx.Response:
    """Exercise the application through its real in-process ASGI interface."""
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get("/health")


def _json_records(captured: str) -> list[dict[str, Any]]:
    """Decode all structured log records emitted during a lifecycle."""
    records: list[dict[str, Any]] = []
    for line in captured.strip().splitlines():
        decoded: object = json.loads(line)
        if not isinstance(decoded, dict):
            raise AssertionError("structured log record must be a JSON object")
        records.append({str(key): value for key, value in decoded.items()})
    return records


def test_health_operation_returns_stable_machine_readable_document() -> None:
    """A platform probe receives the stable process-availability contract."""
    application = create_app(_test_settings())

    response = asyncio.run(_request_health(application))

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"status": "ok"}


def test_application_factory_constructs_independent_applications() -> None:
    """Tests and process entry points can construct the application repeatedly."""
    first = create_app(_test_settings())
    second = create_app(_test_settings())

    assert isinstance(first, FastAPI)
    assert isinstance(second, FastAPI)
    assert first is not second


def test_uvicorn_import_target_exposes_application() -> None:
    """The public ``mosaic.app:app`` target is directly importable by Uvicorn."""
    assert isinstance(app, FastAPI)


def test_application_lifespan_emits_structured_lifecycle_events(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Application availability transitions are observable as structured logs."""
    application = create_app(_test_settings())

    async def run_lifespan() -> None:
        async with application.router.lifespan_context(application):
            pass

    asyncio.run(run_lifespan())

    records = _json_records(capsys.readouterr().err)
    assert [record["event"] for record in records] == [
        "application_started",
        "application_stopped",
    ]
    assert all(record["environment"] == "test" for record in records)
    assert all(record["level"] == "info" for record in records)
