"""
SWASTHYA AI CORE — Correlation ID Utilities.

Every request and worker invocation is assigned a unique correlation ID.
This ID is threaded through all log entries, external calls, and responses
to allow end-to-end tracing without a dedicated trace agent.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

_correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


def generate_correlation_id() -> str:
    """Generate a new UUIDv4 correlation ID."""
    return str(uuid.uuid4())


def set_correlation_id(correlation_id: str) -> None:
    """Bind a correlation ID to the current async context."""
    _correlation_id_var.set(correlation_id)


def get_correlation_id() -> str:
    """
    Retrieve the current context's correlation ID.

    Returns a freshly generated ID if none has been set,
    ensuring logs are never missing a correlation context.
    """
    cid = _correlation_id_var.get()
    if not cid:
        cid = generate_correlation_id()
        _correlation_id_var.set(cid)
    return cid
