"""
SWASTHYA AI CORE — Structured JSON Logger.

Emits machine-parseable JSON log records with correlation_id on every line.
PHI (symptoms, patient details) MUST NEVER be passed to any log call.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from pythonjsonlogger.json import JsonFormatter  # type: ignore[import-untyped]

from src.common.correlation import get_correlation_id
from src.config.settings import get_settings


class _CorrelationAwareFormatter(JsonFormatter):
    """
    Extends JsonFormatter to inject correlation_id into every record
    at formatting time, so it is always present even if the logger
    is called from a context that didn't set one explicitly.
    """

    def add_fields(
        self,
        log_record: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        super().add_fields(log_record, record, message_dict)
        log_record["correlation_id"] = get_correlation_id()
        log_record["module"] = record.module
        log_record.setdefault("level", record.levelname)


def configure_logging() -> None:
    """
    Configure the root logger to emit structured JSON to stdout.

    Call once during application lifespan startup.
    All subsequent `logging.getLogger(name)` calls inherit this config.
    """
    settings = get_settings()
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.app_log_level)

    if root_logger.handlers:
        root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        _CorrelationAwareFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    root_logger.addHandler(handler)

    # Quiet noisy third-party loggers
    for noisy in ("httpx", "httpcore", "aio_pika", "aiormq", "asyncio", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Return a named logger.

    Usage:
        logger = get_logger(__name__)
        logger.info("Processing request", extra={"latency_ms": 42})
    """
    return logging.getLogger(name)
