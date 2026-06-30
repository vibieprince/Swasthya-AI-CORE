"""
Configuration Subsystem Settings Module.

Responsible for loading, parsing, and validating all system environment
variables using Pydantic Settings to guarantee a fail-fast startup.
"""

from typing import Literal
from pydantic import Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Operational Mode Specifications
    APP_ENV: Literal["development", "staging", "production"] = Field(
        default="development",
        alias="APP_ENV"
    )
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        alias="LOG_LEVEL"
    )

    # Networking Core Bindings
    API_HOST: str = Field(default="127.0.0.1", alias="API_HOST")
    API_PORT: int = Field(default=8000, alias="API_PORT")

    # Distributed Task Broker & Cache Infrastructure
    REDIS_URL: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # Vector Storage Engine Persistence
    DATABASE_URL: str = Field(
        default="postgresql://swasthya_admin:secure_pass@localhost:5432/swasthya_intelligence",
        alias="DATABASE_URL"
    )

    # Core AI Provider Credentials
    GEMINI_API_KEY: str = Field(..., alias="GEMINI_API_KEY")
    MISTRAL_API_KEY: str = Field(..., alias="MISTRAL_API_KEY")

    # Deep Research & Scraping Services
    TAVILY_API_KEY: str = Field(..., alias="TAVILY_API_KEY")
    GOOGLE_MAPS_API_KEY: str = Field(..., alias="GOOGLE_MAPS_API_KEY")

    # Enforce reading from local configuration environment profiles
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True
    )


# Instantiate a singleton instance across the application layer scope
settings = Settings()