"""
Structured Logging Architecture.

Configures log formatting and handles asynchronous tracking context
by automatically injecting request correlation tokens into every log message.
"""

import contextvars
import logging
import sys
from typing import Any

# Global context variable tracking execution thread tokens across async states
correlation_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", 
    default="SYSTEM"
)


class CorrelationIdFormatter(logging.Formatter):
    """
    Custom log formatter that injects active correlation IDs 
    into standard log formatting records dynamically.
    """
    def format(self, record: logging.LogRecord) -> str:
        # Pull tracking context from active async thread frame state safely
        record.correlation_id = correlation_id_ctx.get()
        return super().format(record)


def setup_logging(log_level: str = "INFO") -> None:
    """
    Bootstraps the global logging pipeline with structured formatters 
    and standard output stream routing.
    """
    root_logger = logging.getLogger()
    
    # Avoid duplicate handler registrations during reload states
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    log_format = (
        "[%(asctime)s] [%(levelname)s] [CID: %(correlation_id)s] "
        "[%(name)s:%(funcName)s:%(lineno)d] -> %(message)s"
    )

    handler = logging.StreamHandler(sys.stdout)
    formatter = CorrelationIdFormatter(log_format)
    handler.setFormatter(formatter)

    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    # Silence verbose third-party log noise to protect streaming clarity
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)