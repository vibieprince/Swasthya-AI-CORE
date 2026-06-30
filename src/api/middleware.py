"""
API Processing Layer Middleware.

Intercepts incoming HTTP traffic to manage correlation contexts,
measure tracking latency, and handle runtime execution errors cleanly.
"""

import time
import uuid
import logging
from typing import Any, Awaitable, Callable
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from config.logging_config import correlation_id_ctx

logger = logging.getLogger(__name__)


class OperationalContextMiddleware(BaseHTTPMiddleware):
    """
    Orchestrates transaction lifecycle boundaries by generating correlation tokens,
    tracking route execution speeds, and catching unhandled errors.
    """
    async def dispatch(
        self, 
        request: Request, 
        call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start_time = time.perf_counter()
        
        # Extract existing consumer chain tokens or initialize a fresh tracing session
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        
        # Bind token straight to active asynchronous execution frame context
        token = correlation_id_ctx.set(correlation_id)

        try:
            logger.info(f"Ingress HTTP Request: {request.method} {request.url.path}")
            response = await call_next(request)
            
            duration = time.perf_counter() - start_time
            response.headers["X-Correlation-ID"] = correlation_id
            response.headers["X-Execution-Duration-Seconds"] = f"{duration:.4f}"
            
            logger.info(f"Egress HTTP Response: Completed {response.status_code} in {duration:.4f}s")
            return response

        except Exception as unhandled_error:
            duration = time.perf_counter() - start_time
            logger.critical(
                f"System Exception Intercepted: {str(unhandled_error)} "
                f"Execution lifetime failed at {duration:.4f}s", 
                exc_info=True
            )
            
            # Formulate type-safe production diagnostics block without revealing backend internals
            error_payload = {
                "status": "fail",
                "correlation_id": correlation_id,
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unhandled execution error occurred within Swasthya Core Engine.",
                    "diagnostics": f"Tracking signature reference: {correlation_id}"
                }
            }
            
            return JSONResponse(
                status_code=500,
                content=error_payload,
                headers={"X-Correlation-ID": correlation_id}
            )
            
        finally:
            # Clean up token space post-execution to prevent tracking leaks
            correlation_id_ctx.reset(token)