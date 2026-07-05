"""
SWASTHYA AI CORE — Shared HTTPX Async Client.

Single shared AsyncClient instance for the entire application.
Configured with timeouts, retries, and keep-alive pooling.
"""

from __future__ import annotations

import httpx

from src.config.settings import get_settings

_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    """
    Return the shared HTTPX AsyncClient.

    Must be called AFTER startup (lifespan has initialized the client).
    """
    if _client is None:
        raise RuntimeError(
            "HTTP client has not been initialized. "
            "Ensure the application lifespan startup has completed."
        )
    return _client


async def initialize_http_client() -> None:
    """Create and configure the shared HTTPX AsyncClient. Called on startup."""
    global _client
    settings = get_settings()

    _client = httpx.AsyncClient(
        timeout=httpx.Timeout(
            connect=10.0,
            read=float(settings.gemini_timeout_seconds),
            write=30.0,
            pool=10.0,
        ),
        limits=httpx.Limits(
            max_connections=200,
            max_keepalive_connections=50,
            keepalive_expiry=30.0,
        ),
        headers={
            "User-Agent": "SwasthyaAICore/1.0",
            "Accept": "application/json",
        },
        follow_redirects=True,
    )


async def close_http_client() -> None:
    """Gracefully close the shared HTTPX AsyncClient. Called on shutdown."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
