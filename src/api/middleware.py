"""
SWASTHYA AI CORE — API Middleware.

Provides correlation ID threading, structured logging of requests/responses,
and global exception handling.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.common.correlation import generate_correlation_id, set_correlation_id
from src.common.exceptions import SwasthyaBaseError
from src.common.logging import get_logger

logger = get_logger(__name__)


class RequestCorrelationMiddleware(BaseHTTPMiddleware):
    """
    Assigns a correlation ID to every incoming request.
    If the client provided X-Correlation-ID, we use it. Otherwise, we generate one.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Any],
    ) -> Response:
        
        correlation_id = request.headers.get("X-Correlation-ID")
        if not correlation_id:
            correlation_id = generate_correlation_id()
            
        set_correlation_id(correlation_id)
        
        t_start = time.monotonic()
        
        try:
            response = await call_next(request)
            
            latency_ms = int((time.monotonic() - t_start) * 1000)
            
            # Log successful requests
            logger.info(
                "Request completed",
                extra={
                    "method": request.method,
                    "url": str(request.url.path),
                    "status_code": response.status_code,
                    "latency_ms": latency_ms,
                }
            )
            
            # Ensure correlation ID is returned in response headers
            response.headers["X-Correlation-ID"] = correlation_id
            return response
            
        except Exception as exc:
            latency_ms = int((time.monotonic() - t_start) * 1000)
            
            # Centralized error mapping
            if isinstance(exc, SwasthyaBaseError):
                status_code = getattr(exc, "status_code", 400)
                error_response = {
                    "error": {
                        "code": exc.code,
                        "message": exc.message,
                    }
                }
            else:
                status_code = 500
                error_response = {
                    "error": {
                        "code": "INTERNAL_SERVER_ERROR",
                        "message": "An unexpected internal server error occurred."
                    }
                }
                
            logger.error(
                "Request failed",
                extra={
                    "method": request.method,
                    "url": str(request.url.path),
                    "status_code": status_code,
                    "error_code": error_response["error"]["code"],
                    "latency_ms": latency_ms,
                },
                exc_info=status_code == 500
            )
            
            return JSONResponse(
                status_code=status_code,
                content=error_response,
                headers={"X-Correlation-ID": correlation_id}
            )
