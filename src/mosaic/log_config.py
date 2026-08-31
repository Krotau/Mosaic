"""Structured logging configuration for Mosaic application processes."""

import logging
from typing import cast

import structlog
from structlog.stdlib import BoundLogger, ProcessorFormatter
from structlog.types import Processor

from mosaic.config import LogLevel, Settings

_LOG_LEVEL_VALUES: dict[LogLevel, int] = {
    LogLevel.DEBUG: logging.DEBUG,
    LogLevel.INFO: logging.INFO,
    LogLevel.WARNING: logging.WARNING,
    LogLevel.ERROR: logging.ERROR,
    LogLevel.CRITICAL: logging.CRITICAL,
}


def configure_logging(settings: Settings) -> BoundLogger:
    """Configure JSON logging and return the application logger.

    The composition root calls this once with already-validated settings. Both
    structlog events and standard-library records then pass through the same JSON
    renderer. Only the explicitly safe environment value is bound to every Mosaic
    event; the settings object itself is never added to a record.
    """
    log_level = _LOG_LEVEL_VALUES[settings.log_level]
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared_processors,
            ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )

    formatter = ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    logger = structlog.get_logger("mosaic").bind(environment=settings.environment.value)
    return cast(BoundLogger, logger)


__all__ = ["configure_logging"]
