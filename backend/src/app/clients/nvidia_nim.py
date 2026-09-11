"""NVIDIA NIM client, for comparing a third provider against MedGemma and Gemini.

`EVA-001` selects a default and fallback provider from measured results. Comparing two
providers that are both Google-hosted answers a narrower question than the evaluation
asks, so this adds an independent one.

NIM's cloud API speaks the OpenAI chat-completions dialect over a plain bearer token,
which makes this client considerably smaller than the MedGemma one: no Vertex
initialization, no `:predict` fallback, and no prompt echo to strip. The interface
matches the other clients so `ClientTextProvider` can wrap it unchanged.

Configured by `NVIDIA_NIM_API_KEY`, with `NVIDIA_NIM_MODEL` and `NVIDIA_NIM_BASE_URL`
overridable — the catalog changes often enough that pinning a model in code would date
badly.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings
from app.core.exceptions import LLMError

logger = logging.getLogger(__name__)


class NvidiaNimClient:
    """Text generation against an OpenAI-compatible NVIDIA NIM endpoint."""

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        timeout: int = 60,
    ) -> None:
        self.model_name = model or settings.nvidia_nim_model
        self.base_url = (base_url or settings.nvidia_nim_base_url).rstrip("/")
        self.timeout = timeout

        if not settings.nvidia_nim_api_key:
            raise ValueError("NVIDIA_NIM_API_KEY must be set to use NvidiaNimClient.")

        logger.info("Initialized NvidiaNimClient with model: %s", self.model_name)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {settings.nvidia_nim_api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _body(
        self,
        prompt: str,
        system_instruction: str | None,
        temperature: float,
        max_tokens: int,
    ) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})
        return {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

    @staticmethod
    def _extract_text(payload: dict[str, Any]) -> str:
        """Pull the reply out of an OpenAI-shaped response.

        Both message and text shapes are accepted because NIM hosts many models and the
        older completion form still appears. An unrecognized shape raises rather than
        returning an empty string, which would otherwise read downstream as a model that
        answered with nothing.
        """
        choices = payload.get("choices") or []
        if not choices:
            raise LLMError(f"NIM response contained no choices: {payload}")

        choice = choices[0]
        message = choice.get("message") or {}
        text = message.get("content") or choice.get("text")
        if not isinstance(text, str):
            raise LLMError(f"Unexpected NIM response format: {payload}")
        return text.strip()

    async def generate(
        self,
        prompt: str,
        system_instruction: str | None = None,
        image: bytes | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """Generate a completion. Raises `LLMError` on any failure.

        `image` is accepted and ignored to keep the signature interchangeable with the
        other clients; NIM text models take no image input.
        """
        if image:
            logger.warning("Image input is not supported by this NIM model. Ignoring image.")

        url = f"{self.base_url}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    url,
                    headers=self._headers(),
                    json=self._body(prompt, system_instruction, temperature, max_tokens),
                )
        except httpx.HTTPError as exc:
            raise LLMError(f"NIM request failed: {exc}") from exc

        if response.status_code != 200:
            # The body can echo the prompt, so only the status reaches the log and the
            # exception. Comparisons run over clinical scenario text.
            logger.warning("NIM endpoint returned %s", response.status_code)
            raise LLMError(f"NIM endpoint error {response.status_code}")

        return self._extract_text(response.json())
