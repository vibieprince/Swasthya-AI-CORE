"""
SWASTHYA AI CORE — Mistral AI REST Provider (Failover).

Communicates with Mistral Large Latest exclusively via direct HTTPX requests.
No Mistral SDK. No LangChain.

Used exclusively as the secondary failover provider when Gemini is unavailable.
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

# Mistral Large pricing (per million tokens)
_MISTRAL_INPUT_COST_PER_M = 2.0
_MISTRAL_OUTPUT_COST_PER_M = 6.0

_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


class MistralProvider(BaseLLMProvider):
    """
    Mistral AI provider using the /v1/chat/completions endpoint.

    OpenAI-compatible chat format with JSON response mode enforced
    via response_format: {"type": "json_object"}.
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    @property
    def provider_name(self) -> str:
        return "mistral"

    @property
    def model_name(self) -> str:
        return self._settings.mistral_model

    def _build_payload(self, request: LLMRequest) -> dict[str, Any]:
        return {
            "model": self._settings.mistral_model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "response_format": {"type": "json_object"},
        }

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            (input_tokens / 1_000_000) * _MISTRAL_INPUT_COST_PER_M
            + (output_tokens / 1_000_000) * _MISTRAL_OUTPUT_COST_PER_M
        )

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Execute Mistral completion with exponential backoff."""
        settings = self._settings
        url = f"{settings.mistral_base_url}/chat/completions"
        payload = self._build_payload(request)
        client = get_http_client()
        max_retries = settings.mistral_max_retries
        timeout = float(settings.mistral_timeout_seconds)

        last_error: Exception | None = None
        for attempt in range(max_retries):
            t_start = time.monotonic()
            try:
                response = await client.post(
                    url,
                    json=payload,
                    headers={"Authorization": f"Bearer {settings.mistral_api_key}"},
                    timeout=timeout,
                )
                latency_ms = int((time.monotonic() - t_start) * 1000)

                if response.status_code in _RETRYABLE_STATUS_CODES:
                    if response.status_code == 429 and not settings.llm_retry_on_429:
                        raise LLMProviderError(
                            provider="mistral",
                            message="HTTP 429 Rate Limited (fast failover)",
                            status_code=429,
                        )

                    wait = 0.5  # Quick flat retry instead of exponential backoff
                    logger.warning(
                        "Mistral retryable error",
                        extra={
                            "attempt": attempt + 1,
                            "status_code": response.status_code,
                            "wait_seconds": wait,
                        },
                    )
                    last_error = LLMProviderError(
                        provider="mistral",
                        message=f"HTTP {response.status_code}",
                        status_code=response.status_code,
                    )
                    
                    if attempt < max_retries - 1:
                        await asyncio.sleep(wait)
                    continue

                if response.status_code != 200:
                    raise LLMProviderError(
                        provider="mistral",
                        message=f"Non-retryable HTTP {response.status_code}: {response.text[:200]}",
                        status_code=response.status_code,
                    )

                body = response.json()
                raw_text = body["choices"][0]["message"]["content"]
                usage = body.get("usage", {})
                input_tokens = usage.get("prompt_tokens", 0)
                output_tokens = usage.get("completion_tokens", 0)

                parsed = self._parse_json(raw_text)

                return LLMResponse(
                    provider="mistral",
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
                wait = 0.5  # Quick flat retry instead of exponential backoff
                logger.warning(
                    "Mistral network failure",
                    extra={"attempt": attempt + 1, "error": str(exc), "wait_seconds": wait},
                )
                last_error = LLMProviderError(
                    provider="mistral",
                    message=str(exc),
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait)

            except LLMInvalidResponseError:
                raise

            except LLMProviderError:
                raise

            except Exception as exc:
                last_error = LLMProviderError(
                    provider="mistral",
                    message=f"Unexpected error: {exc}",
                )
                await asyncio.sleep(0.5)

        raise last_error or LLMProviderError(
            provider="mistral",
            message="All retry attempts exhausted.",
        )

    def _parse_json(self, raw_text: str) -> dict[str, Any]:
        text = raw_text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
        try:
            return json.loads(text)  # type: ignore[no-any-return]
        except json.JSONDecodeError as exc:
            raise LLMInvalidResponseError(provider="mistral", raw_response=raw_text) from exc
