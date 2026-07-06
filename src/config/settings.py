"""
SWASTHYA AI CORE — Application Settings.

Uses Pydantic Settings v2 with fail-fast validation.
The application REFUSES TO START if any required variable is absent.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Centralised, validated configuration for the entire application.

    All values are sourced from environment variables / .env file.
    Missing REQUIRED fields raise a ValidationError at import time,
    which kills the process before the first request is ever served.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ────────────────────────────────────────────────────────────
    app_env: Literal["development", "staging", "production"] = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # ── Gemini (Primary LLM) — REQUIRED ───────────────────────────────────────
    gemini_api_key: str = Field(..., min_length=10)
    gemini_model: str = "gemini-2.5-flash"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_max_retries: int = Field(default=3, ge=1, le=10)

    # ── Mistral (Failover LLM) — REQUIRED ─────────────────────────────────────
    mistral_api_key: str = Field(..., min_length=10)
    mistral_model: str = "mistral-large-latest"
    mistral_base_url: str = "https://api.mistral.ai/v1"
    mistral_max_retries: int = Field(default=2, ge=1, le=5)

    # ── Tavily Search — REQUIRED ───────────────────────────────────────────────
    tavily_api_key: str = Field(..., min_length=10)
    tavily_base_url: str = "https://api.tavily.com"

    # ── Google Maps — REQUIRED ─────────────────────────────────────────────────
    google_maps_api_key: str = Field(..., min_length=10)

    # ── Redis — REQUIRED ───────────────────────────────────────────────────────
    redis_url: str = Field(..., min_length=10)
    redis_ttl_seconds: int = Field(default=21600, ge=3600)

    # ── RabbitMQ — REQUIRED ────────────────────────────────────────────────────
    rabbitmq_url: str = Field(..., min_length=10)
    rabbitmq_discovery_queue: str = "swasthya.discovery"
    rabbitmq_exchange: str = "swasthya.exchange"
    rabbitmq_prefetch_count: int = Field(default=4, ge=1, le=32)

    # ── LLM Timeouts ───────────────────────────────────────────────────────────
    gemini_timeout_seconds: int = Field(default=30, ge=10, le=120)   # Issue 9
    mistral_timeout_seconds: int = Field(default=30, ge=10, le=120)  # Issue 9

    # ── Scraping & Pipeline Concurrency ────────────────────────────────────────
    scraper_timeout_seconds: float = Field(default=5.0, ge=1.0, le=30.0)
    research_concurrency: int = Field(default=5, ge=1, le=16)
    shortlist_size: int = Field(default=8, ge=1, le=20)

    # ── Pipeline Timeouts ──────────────────────────────────────────────────────
    maps_timeout_seconds: float = Field(default=8.0, ge=1.0)
    tavily_timeout_seconds: float = Field(default=12.0, ge=1.0)
    nabh_timeout_seconds: float = Field(default=8.0, ge=1.0)
    research_timeout_seconds: float = Field(default=6.0, ge=1.0)

    @field_validator("gemini_api_key", "mistral_api_key", "tavily_api_key", "google_maps_api_key", mode="before")
    @classmethod
    def _reject_placeholder(cls, value: str, info: object) -> str:
        placeholders = {"your-gemini-api-key-here", "your-mistral-api-key-here",
                        "your-tavily-api-key-here", "your-google-maps-api-key-here"}
        if value in placeholders:
            raise ValueError(f"Placeholder value detected — set a real API key.")
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Returns the singleton Settings instance.

    The @lru_cache ensures Settings is parsed exactly once.
    Any ValidationError propagates immediately, preventing startup.
    """
    return Settings()
