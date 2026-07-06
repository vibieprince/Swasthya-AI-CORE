"""
SWASTHYA AI CORE — Common Exceptions.

Defines a typed exception hierarchy for all domain and infrastructure errors.
No stack traces are ever returned to the client.
"""

from __future__ import annotations


class SwasthyaBaseError(Exception):
    """Root exception for all SWASTHYA errors."""

    def __init__(self, message: str, code: str = "INTERNAL_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


# ── LLM Errors ─────────────────────────────────────────────────────────────────

class LLMProviderError(SwasthyaBaseError):
    """A single LLM provider failed to complete the request."""

    def __init__(self, provider: str, message: str, status_code: int | None = None) -> None:
        super().__init__(message, code="LLM_PROVIDER_ERROR")
        self.provider = provider
        self.status_code = status_code


class LLMGatewayExhaustedError(SwasthyaBaseError):
    """All LLM providers exhausted their retry budgets."""

    def __init__(self, message: str = "All LLM providers are unavailable.") -> None:
        super().__init__(message, code="LLM_GATEWAY_EXHAUSTED")


class LLMInvalidResponseError(SwasthyaBaseError):
    """LLM returned a response that could not be parsed as JSON."""

    def __init__(self, provider: str, raw_response: str) -> None:
        super().__init__(f"Invalid JSON from {provider}", code="LLM_INVALID_RESPONSE")
        self.provider = provider
        self.raw_response = raw_response


# ── Context Pipeline Errors ─────────────────────────────────────────────────────

class ContextPipelineError(SwasthyaBaseError):
    """The context analysis pipeline encountered an unrecoverable error."""

    def __init__(self, stage: str, message: str) -> None:
        super().__init__(message, code="CONTEXT_PIPELINE_ERROR")
        self.stage = stage


class InsufficientContextError(SwasthyaBaseError):
    """Patient context lacks the minimum required clinical signals."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="INSUFFICIENT_CONTEXT")


class ContextExpiredError(SwasthyaBaseError):
    """A context_id was provided but the session has expired from Redis."""

    def __init__(self, context_id: str) -> None:
        super().__init__(
            f"Conversation session '{context_id}' has expired. Please start a new conversation.",
            code="CONTEXT_EXPIRED",
        )
        self.context_id = context_id


# ── Discovery Errors ────────────────────────────────────────────────────────────

class DiscoveryPipelineError(SwasthyaBaseError):
    """The discovery pipeline encountered an unrecoverable error."""

    def __init__(self, stage: str, message: str) -> None:
        super().__init__(message, code="DISCOVERY_PIPELINE_ERROR")
        self.stage = stage


class TavilySearchError(SwasthyaBaseError):
    """Tavily API call failed after retries."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message, code="TAVILY_SEARCH_ERROR")
        self.status_code = status_code


class MapsSearchError(SwasthyaBaseError):
    """Google Maps API call failed after retries."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message, code="MAPS_SEARCH_ERROR")
        self.status_code = status_code


class ScrapingError(SwasthyaBaseError):
    """Web scraping failed on all available engines."""

    def __init__(self, url: str, message: str) -> None:
        super().__init__(message, code="SCRAPING_ERROR")
        self.url = url


# ── Infrastructure Errors ───────────────────────────────────────────────────────

class RedisError(SwasthyaBaseError):
    """Redis operation failed."""

    def __init__(self, operation: str, message: str) -> None:
        super().__init__(message, code="REDIS_ERROR")
        self.operation = operation


class TaskNotFoundError(SwasthyaBaseError):
    """The requested task_id does not exist in Redis."""

    def __init__(self, task_id: str) -> None:
        super().__init__(f"Task '{task_id}' not found.", code="TASK_NOT_FOUND")
        self.task_id = task_id
