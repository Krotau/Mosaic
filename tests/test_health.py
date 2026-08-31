"""Behavioral tests for Mosaic's public ASGI application seam."""

import asyncio
from uuid import UUID

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI

from mosaic.app import app, create_app
from mosaic.config import Environment, LogLevel, Settings
from tests.log_records import decode_json_records


def _test_settings() -> Settings:
    """Build explicit deterministic settings for application tests."""
    return Settings(environment=Environment.TEST, log_level=LogLevel.INFO)


async def _request_health(application: FastAPI) -> httpx.Response:
    """Exercise startup, HTTP, and shutdown through public ASGI messages."""
    async with LifespanManager(application) as manager:
        transport = httpx.ASGITransport(app=manager.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get("/health")


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

    asyncio.run(_request_health(application))

    records = decode_json_records(capsys.readouterr().err)
    lifecycle_records = [
        record
        for record in records
        if record["event"] in {"application_started", "application_stopped"}
    ]
    assert [record["event"] for record in lifecycle_records] == [
        "application_started",
        "application_stopped",
    ]
    assert all(record["environment"] == "test" for record in lifecycle_records)
    assert all(record["level"] == "info" for record in lifecycle_records)


def test_http_request_receives_request_and_anonymous_actor_context(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every HTTP request is correlated without claiming an authenticated actor."""
    application = create_app(_test_settings())

    response = asyncio.run(_request_health(application))

    request_id = str(UUID(response.headers["x-request-id"]))
    records = decode_json_records(capsys.readouterr().err)
    request_record = next(
        record for record in records if record["event"] == "http_request_completed"
    )
    assert request_record["request_id"] == request_id
    assert request_record["actor_kind"] == "anonymous"
    assert request_record["method"] == "GET"
    assert request_record["path"] == "/health"
    assert request_record["status_code"] == 200
