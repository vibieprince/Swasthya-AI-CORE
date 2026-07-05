"""
SWASTHYA AI CORE — Abstract LLM Provider.

Defines the contract all LLM providers must implement.
The gateway only depends on this abstraction.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMRequest:
    """Normalised request structure passed to any provider."""

    system_prompt: str
    user_prompt: str
    response_mime_type: str = "application/json"
    temperature: float = 0.1
    max_tokens: int = 8192
    prompt_version: str = "unknown"


@dataclass
class LLMResponse:
    """Normalised response returned by any provider."""

    provider: str
    model: str
    content: str                       # Raw text content (always JSON string)
    parsed: dict[str, Any]             # Already-parsed JSON dict
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    retry_count: int = 0
    failover_triggered: bool = False
    failover_reason: str = ""
    estimated_cost_usd: float = 0.0
    prompt_version: str = "unknown"


class BaseLLMProvider(ABC):
    """Abstract base class for all LLM providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider identifier."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Model identifier as used in API calls."""
        ...

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """
        Send a completion request to the provider.

        Must raise LLMProviderError on recoverable failures.
        Must raise LLMInvalidResponseError if JSON cannot be parsed.
        """
        ...

    @abstractmethod
    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Estimate the cost in USD for the given token counts."""
        ...
