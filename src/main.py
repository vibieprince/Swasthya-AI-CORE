"""
SWASTHYA AI CORE — Application Entry Point.

Configures FastAPI, mounts routers, and manages the application lifespan.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.middleware import RequestCorrelationMiddleware
from src.api.routers import context, discovery, tasks
from src.common.logging import configure_logging, get_logger
from src.config.settings import get_settings
from src.infrastructure.execution.executor import get_job_executor, initialize_job_executor
from src.infrastructure.http.client import close_http_client, initialize_http_client
from src.infrastructure.llm.gateway import LLMGateway
from src.infrastructure.redis.client import close_redis, initialize_redis

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.
    Initializes and tears down infrastructure dependencies.
    """
    settings = get_settings()
    configure_logging()
    
    logger.info("Starting Swasthya AI Core", extra={"env": settings.app_env})

    try:
        # ── Initialize Infrastructure ──────────────────────────────────────────
        await initialize_http_client()
        await initialize_redis()
        
        # Initialize internal job executor
        gateway = LLMGateway()
        initialize_job_executor(gateway)
        
        logger.info("Application startup complete.")
        yield

    except Exception as exc:
        logger.critical("Application startup failed", extra={"error": str(exc)}, exc_info=True)
        raise
    finally:
        # ── Teardown Infrastructure ────────────────────────────────────────────
        logger.info("Application shutdown initiated.")
        
        # Wait for background jobs to complete
        try:
            await get_job_executor().shutdown()
        except Exception as exc:
            logger.warning("Error shutting down JobExecutor", extra={"error": str(exc)})
            
        await asyncio.shield(close_redis())
        await asyncio.shield(close_http_client())
        logger.info("Application shutdown complete.")


def create_app() -> FastAPI:
    """FastAPI application factory."""
    
    # We call get_settings here to fail-fast if config is invalid
    settings = get_settings()
    
    app = FastAPI(
        title="SWASTHYA AI CORE",
        description="Stateless Healthcare Intelligence Engine",
        version="1.0.2",
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
    )

    # ── Middleware ─────────────────────────────────────────────────────────────
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Restrict in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Correlation-ID"],
    )
    app.add_middleware(RequestCorrelationMiddleware)

    # ── Routers ────────────────────────────────────────────────────────────────
    
    app.include_router(context.router)
    app.include_router(discovery.router)
    app.include_router(tasks.router)
    
    @app.get("/health", tags=["System"])
    async def health_check() -> dict[str, str]:
        """Liveness probe."""
        return {"status": "healthy"}

    return app


# Uvicorn entry point
app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
