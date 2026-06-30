"""
Swasthya AI Intelligence Core Application Entrypoint.

Initializes framework components, registers middleware pipelines, 
sets up logging structures, and exposes system health checks.
"""

from typing import Any, Dict
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from config.settings import settings
from config.logging_config import setup_logging
from src.api.middleware import OperationalContextMiddleware

# 1. Initialize structured logging configuration at launch
setup_logging(log_level=settings.LOG_LEVEL)

app = FastAPI(
    title="Swasthya AI Intelligence Core",
    description="Stateless High-Availability Clinical Analytics Platform",
    version="1.0.0",
    docs_url="/docs" if settings.APP_ENV != "production" else None,
    redoc_url="/redoc" if settings.APP_ENV != "production" else None,
)

# 2. Register Cross-Origin Resource Sharing (CORS) rules
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict this to specific backend domains in production settings
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. Intercept request chains via structural middleware components
app.add_middleware(OperationalContextMiddleware)


@app.get("/health", status_code=status.HTTP_200_OK, tags=["Diagnostics"])
async def health_check() -> dict[str, Any]:
    """
    Exposes a stateless diagnostic endpoint to monitor platform availability.
    Used by container orchestrators to verify service health status.
    """
    return {
        "status": "healthy",
        "environment": settings.APP_ENV,
        "platform": "Swasthya AI Core Engine",
        "version": "1.0.0"
    }


if __name__ == "__main__":
    import uvicorn
    # Start the core application loop
    uvicorn.run(
        "main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=True if settings.APP_ENV == "development" else False
    )