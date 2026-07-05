"""
SWASTHYA AI CORE — Google Gemini REST Provider.

Communicates with Gemini 2.5 Flash exclusively via direct HTTPX requests.
No Gemini SDK. No LangChain.

Implements exponential backoff with configurable retry budget.
Raises LLMProviderError on retryable failures.
Raises LLMInvalidResponseError on bad JSON.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx

from src.common.exceptions import LLMInvalidResponseError, LLMProviderError
from src.common.logging import get_logger
from src.config.settings import get_settings
from src.infrastructure.http.client import get_http_client
from src.infrastructure.llm.providers.base import BaseLLMProvider, LLMRequest, LLMResponse

logger = get_logger(__name__)

# Gemini 2.5 Flash pricing (per million tokens, as of 2025)
_GEMINI_INPUT_COST_PER_M = 0.075
_GEMINI_OUTPUT_COST_PER_M = 0.30

# HTTP status codes that warrant a retry
_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


class GeminiProvider(BaseLLMProvider):
    """
    Google Gemini provider using the generateContent REST endpoint.

    Endpoint pattern:
        POST {base_url}/models/{model}:generateContent?key={api_key}

    Always enforces responseMimeType: application/json.
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._settings.gemini_model

    def _build_url(self) -> str:
        return (
            f"{self._settings.gemini_base_url}/models/"
            f"{self._settings.gemini_model}:generateContent"
            f"?key={self._settings.gemini_api_key}"
        )

    def _build_payload(self, request: LLMRequest) -> dict[str, Any]:
        return {
            "systemInstruction": {
                "parts": [{"text": request.system_prompt}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": request.user_prompt}]
                }
            ],
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
                "responseMimeType": request.response_mime_type,
            },
        }

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            (input_tokens / 1_000_000) * _GEMINI_INPUT_COST_PER_M
            + (output_tokens / 1_000_000) * _GEMINI_OUTPUT_COST_PER_M
        )

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Execute the Gemini completion with exponential backoff retries."""
        settings = self._settings
        max_retries = settings.gemini_max_retries
        timeout = float(settings.gemini_timeout_seconds)
        url = self._build_url()
        payload = self._build_payload(request)
        client = get_http_client()

        last_error: Exception | None = None
        for attempt in range(max_retries):
            t_start = time.monotonic()
            try:
                response = await client.post(
                    url,
                    json=payload,
                    timeout=timeout,
                )
                latency_ms = int((time.monotonic() - t_start) * 1000)

                if response.status_code in _RETRYABLE_STATUS_CODES:
                    wait = (2 ** attempt) * 0.5
                    logger.warning(
                        "Gemini retryable error",
                        extra={
                            "attempt": attempt + 1,
                            "status_code": response.status_code,
                            "wait_seconds": wait,
                        },
                    )
                    last_error = LLMProviderError(
                        provider="gemini",
                        message=f"HTTP {response.status_code}",
                        status_code=response.status_code,
                    )
                    await asyncio.sleep(wait)
                    continue

                if response.status_code != 200:
                    raise LLMProviderError(
                        provider="gemini",
                        message=f"Non-retryable HTTP {response.status_code}: {response.text[:200]}",
                        status_code=response.status_code,
                    )

                body = response.json()
                raw_text = body["candidates"][0]["content"]["parts"][0]["text"]
                usage = body.get("usageMetadata", {})
                input_tokens = usage.get("promptTokenCount", 0)
                output_tokens = usage.get("candidatesTokenCount", 0)

                parsed = self._parse_json(raw_text)

                return LLMResponse(
                    provider="gemini",
                    model=self.model_name,
                    content=raw_text,
                    parsed=parsed,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_ms=latency_ms,
                    retry_count=attempt,
                    estimated_cost_usd=self.estimate_cost(input_tokens, output_tokens),
                    prompt_version=request.prompt_version,
                )

            except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout,
                    httpx.RemoteProtocolError, httpx.NetworkError) as exc:
                wait = (2 ** attempt) * 0.5
                logger.warning(
                    "Gemini network failure",
                    extra={"attempt": attempt + 1, "error": str(exc), "wait_seconds": wait},
                )
                last_error = LLMProviderError(
                    provider="gemini",
                    message=str(exc),
                )
                await asyncio.sleep(wait)

            except LLMInvalidResponseError:
                raise

            except LLMProviderError:
                raise

            except Exception as exc:
                last_error = LLMProviderError(
                    provider="gemini",
                    message=f"Unexpected error: {exc}",
                )
                await asyncio.sleep(0.5)

        raise last_error or LLMProviderError(
            provider="gemini",
            message="All retry attempts exhausted.",
        )

    def _parse_json(self, raw_text: str) -> dict[str, Any]:
        """Parse JSON from model output, stripping markdown fences if present."""
        text = raw_text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
        try:
            return json.loads(text)  # type: ignore[no-any-return]
        except json.JSONDecodeError as exc:
            raise LLMInvalidResponseError(provider="gemini", raw_response=raw_text) from exc
