"""Mosaic's application composition root and Uvicorn import target."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from mosaic.config import Settings
from mosaic.http.health import router as health_router
from mosaic.log_config import configure_logging


def create_app(settings: Settings) -> FastAPI:
    """Construct an independent Mosaic application from validated settings."""
    logger = configure_logging(settings)

    @asynccontextmanager
    async def lifespan(_application: FastAPI) -> AsyncIterator[None]:
        logger.info("application_started")
        try:
            yield
        finally:
            logger.info("application_stopped")

    application = FastAPI(title="Mosaic", lifespan=lifespan)
    application.include_router(health_router)
    return application


app = create_app(Settings())

__all__ = ["app", "create_app"]
