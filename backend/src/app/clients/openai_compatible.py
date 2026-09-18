"""Provider-neutral text generation over any OpenAI-compatible chat endpoint.

Ollama, vLLM, llama.cpp, Groq, OpenRouter, NVIDIA NIM, and the Gemini API's
compatibility layer all speak the same `/chat/completions` shape. Speaking it once,
with plain HTTP and no vendor SDK, is what lets the evaluation compare a self-hosted
open-weight model against a paid API without a new adapter per vendor.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.models.generation import (
    GenerationCapability,
    GenerationErrorCode,
    GenerationProviderError,
    GenerationRequest,
    GenerationResponse,
    GenerationTelemetry,
)

_STATUS_TO_CODE: dict[int, GenerationErrorCode] = {
    # A rejected schema and an unreachable endpoint both used to arrive as UNAVAILABLE,
    # which made a JSON-dialect problem look like a capacity problem.
    400: GenerationErrorCode.INVALID_REQUEST,
    401: GenerationErrorCode.AUTHENTICATION,
    403: GenerationErrorCode.AUTHENTICATION,
    404: GenerationErrorCode.CONFIGURATION,
    422: GenerationErrorCode.INVALID_REQUEST,
    429: GenerationErrorCode.RATE_LIMITED,
}

# Shared-capacity pools answer 429 or a transient 5xx under contention and recover
# within seconds; Google's guidance is exponential backoff. Client errors never retry.
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class OpenAICompatibleTextProvider:
    """`TextProvider` for an OpenAI-style `/chat/completions` endpoint.

    When a request carries a `response_schema` the endpoint is asked for native
    JSON-schema output; endpoints that ignore the field still return text, which the
    caller validates. Token usage is recorded when the endpoint reports it.
    """

    capabilities = frozenset({GenerationCapability.TEXT, GenerationCapability.STRUCTURED_OUTPUT})

    def __init__(
        self,
        *,
        name: str,
        model: str,
        base_url: str,
        api_key: str | None = None,
        timeout_seconds: float = 90.0,
        native_structured_output: bool = True,
        extra_headers: dict[str, str] | None = None,
        reasoning_effort: str | None = None,
        max_retries: int = 0,
        backoff_seconds: float = 1.0,
        sleep: Callable[[float], Awaitable[object]] | None = None,
        bearer_token: Callable[[], str] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.name = name
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.native_structured_output = native_structured_output
        self.reasoning_effort = reasoning_effort
        self.max_retries = max(0, max_retries)
        self.backoff_seconds = backoff_seconds
        self._sleep: Callable[[float], Awaitable[object]] = sleep or asyncio.sleep
        self._bearer_token = bearer_token
        headers = {"Content-Type": "application/json", **(extra_headers or {})}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._headers = headers
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)

    def _request_headers(self) -> dict[str, str]:
        if self._bearer_token is None:
            return self._headers
        # Short-lived credentials such as Google access tokens expire mid-run, so ask for a
        # current one on every request instead of freezing the value at construction.
        return {**self._headers, "Authorization": f"Bearer {self._bearer_token()}"}

    async def aclose(self) -> None:
        await self._client.aclose()

    def _body(self, request: GenerationRequest) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        if request.system_instruction:
            messages.append({"role": "system", "content": request.system_instruction})
        messages.append({"role": "user", "content": request.prompt})
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.response_schema is not None and self.native_structured_output:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "response", "schema": request.response_schema},
            }
        if self.reasoning_effort:
            body["reasoning_effort"] = self.reasoning_effort
        return body

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        started = time.perf_counter()
        retries = 0
        while True:
            try:
                response = await self._client.post(
                    f"{self.base_url}/chat/completions",
                    json=self._body(request),
                    headers=self._request_headers(),
                )
            except httpx.TimeoutException as exc:
                raise GenerationProviderError(
                    GenerationErrorCode.TIMEOUT, f"{self.name} timed out"
                ) from exc
            except httpx.HTTPError as exc:
                raise GenerationProviderError(
                    GenerationErrorCode.UNAVAILABLE, f"{self.name} is unreachable"
                ) from exc
            if response.status_code in _RETRYABLE_STATUS and retries < self.max_retries:
                # Full jitter on top of the exponential step keeps parallel callers
                # from retrying in lockstep against the same pool.
                delay = self.backoff_seconds * (2**retries)
                await self._sleep(delay + random.uniform(0, self.backoff_seconds))
                retries += 1
                continue
            break

        if response.status_code >= 400:
            code = _STATUS_TO_CODE.get(response.status_code, GenerationErrorCode.UNAVAILABLE)
            raise GenerationProviderError(code, f"{self.name} returned HTTP {response.status_code}")

        try:
            data = response.json()
        except ValueError as exc:
            raise GenerationProviderError(
                GenerationErrorCode.INVALID_RESPONSE, f"{self.name} returned non-JSON"
            ) from exc

        finish_reason = _extract_finish_reason(data)
        text = _extract_text(data)
        if not text:
            # A reasoning model that spends its whole budget thinking answers with empty
            # content and no error at all. That is the budget running out, not a broken
            # reply, and the two must not be scored the same way.
            code = (
                GenerationErrorCode.TRUNCATED
                if finish_reason == "length"
                else GenerationErrorCode.INVALID_RESPONSE
            )
            raise GenerationProviderError(code, f"{self.name} returned no content")

        return GenerationResponse(
            text=text,
            telemetry=GenerationTelemetry(
                provider=self.name,
                model=str(data.get("model") or self.model),
                latency_ms=round((time.perf_counter() - started) * 1000),
                usage=_extract_usage(data),
                retries=retries,
                finish_reason=finish_reason,
            ),
        )


# MedGemma 1.5 served by vLLM without a reasoning parser writes its reasoning inline
# between these tokens before the answer. Reasoning must never reach a patient or a
# stored record, so it is removed here rather than by each caller.
_THINKING_START = "<unused94>"
_THINKING_END = "<unused95>"


def _strip_inline_thinking(text: str) -> str:
    start = text.find(_THINKING_START)
    if start == -1:
        return text
    end = text.find(_THINKING_END, start)
    if end == -1:
        # The reasoning never closed, so no answer arrived; never return the reasoning.
        return text[:start].strip()
    return (text[:start] + text[end + len(_THINKING_END) :]).strip()


def _extract_text(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        return ""
    content = (choices[0].get("message") or {}).get("content")
    if isinstance(content, str):
        return _strip_inline_thinking(content).strip()
    if isinstance(content, list):
        # Some servers return a list of typed parts; keep only the text parts.
        parts = [part.get("text", "") for part in content if isinstance(part, dict)]
        return _strip_inline_thinking("".join(parts)).strip()
    return ""


def _extract_finish_reason(data: dict[str, Any]) -> str | None:
    """Why the provider stopped generating, in the provider's own words.

    `length` means the token budget ran out. Everything else is the model deciding it
    had finished, which is the only case where the answer is the model's own work.
    """
    choices = data.get("choices") or []
    if not choices:
        return None
    reason = choices[0].get("finish_reason")
    return reason if isinstance(reason, str) else None


def _extract_usage(data: dict[str, Any]) -> dict[str, int]:
    usage = data.get("usage") or {}
    result: dict[str, int] = {}
    for wire, local in (
        ("prompt_tokens", "input_tokens"),
        ("completion_tokens", "output_tokens"),
        ("total_tokens", "total_tokens"),
    ):
        value = usage.get(wire)
        if isinstance(value, int):
            result[local] = value
    # Thinking is billed and counted inside the completion total, so a reasoning model
    # given the same budget as a plain one has less of it left for the answer.
    reasoning = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
    if isinstance(reasoning, int):
        result["reasoning_tokens"] = reasoning
    return result
