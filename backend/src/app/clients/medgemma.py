"""MedGemma client for medical tasks via Vertex AI."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from app.config import settings
from app.core.exceptions import LLMError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class MedGemmaClient:
    """MedGemma client for medical tasks via Vertex AI.

    Uses same interface as GeminiClient for easy A/B testing.
    MedGemma is Google's medical-specialized model based on Gemma 3.

    Available MedGemma models:
    - google/medgemma-1.5-4b-it
    - google/medgemma-4b-it
    - google/medgemma-27b-it
    """

    def __init__(
        self,
        model: str = "google/medgemma-27b-it",
        max_retries: int = 3,
        timeout: int = 60,
    ) -> None:
        """Initialize MedGemma client strictly for Vertex AI.

        Args:
            model: MedGemma model ID
            max_retries: Max retry attempts
            timeout: Request timeout in seconds
        """
        self.model_name = model
        self.max_retries = max_retries
        self.timeout = timeout

        vertex_endpoint = settings.vertex_ai_medgemma_endpoint
        if not vertex_endpoint:
            raise ValueError("VERTEX_AI_MEDGEMMA_ENDPOINT must be set to use MedGemmaClient.")

        try:
            from google.cloud import aiplatform

            aiplatform.init(
                project=settings.google_project_id,
                location=settings.vertex_ai_location,
            )
            self.endpoint = aiplatform.Endpoint(vertex_endpoint)
            logger.info(f"Initialized MedGemmaClient with Vertex AI endpoint: {vertex_endpoint}")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Vertex AI for MedGemmaClient: {e}") from e

    @staticmethod
    def _strip_prompt_echo(text: str, prompt: str) -> str:
        """Strip echoed prompt from vLLM response."""
        if "\nOutput:" in text:
            parts = text.split("\nOutput:", 1)
            cleaned = parts[1].strip()
            if cleaned:
                return cleaned

        prompt_prefix = prompt.strip()[:80]
        if text.startswith(prompt_prefix):
            prompt_end = text.find("\n\n", len(prompt_prefix))
            if prompt_end != -1:
                cleaned = text[prompt_end:].strip()
                if cleaned:
                    return cleaned

        return text.strip()

    @staticmethod
    def _format_gemma_chat_template(prompt: str, system_instruction: str | None = None) -> str:
        """Format prompt using Gemma/MedGemma chat template."""
        formatted_prompt = ""
        if system_instruction:
            formatted_prompt += (
                f"<start_of_turn>user\n{system_instruction}\n\n{prompt}<end_of_turn>\n"
            )
        else:
            formatted_prompt += f"<start_of_turn>user\n{prompt}<end_of_turn>\n"
        formatted_prompt += "<start_of_turn>model\n"
        return formatted_prompt

    def _build_chat_request(
        self,
        prompt: str,
        system_instruction: str | None,
        temperature: float,
        max_tokens: int,
    ) -> dict[str, Any]:
        """Build OpenAI-compatible chat request body."""
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

    def _build_endpoint_urls(self) -> tuple[str, str]:
        """Build chat and predict endpoint URLs from Vertex AI endpoint path."""
        endpoint_parts = settings.vertex_ai_medgemma_endpoint.split("/")
        endpoint_id = endpoint_parts[-1]
        project_number = endpoint_parts[1]
        location = endpoint_parts[3]

        base_url = f"https://{endpoint_id}.{location}-{project_number}.prediction.vertexai.goog"
        chat_url = f"{base_url}/v1/chat/completions"
        predict_url = f"{base_url}/v1/{settings.vertex_ai_medgemma_endpoint}:predict"

        return chat_url, predict_url

    async def _get_auth_headers(self) -> dict[str, str]:
        """Get authentication headers for Vertex AI requests."""
        import google.auth
        import google.auth.transport.requests

        creds, _project = google.auth.default()
        auth_req = google.auth.transport.requests.Request()
        creds.refresh(auth_req)  # type: ignore[no-untyped-call]
        access_token = creds.token

        return {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    async def _make_vllm_request(
        self,
        chat_url: str,
        predict_url: str,
        headers: dict[str, str],
        request_body: dict[str, Any],
        prompt: str,
        system_instruction: str | None,
        temperature: float,
        max_tokens: int,
    ) -> dict[str, Any]:
        """Make HTTP request to vLLM endpoint with fallback logic."""
        logger.debug("MedGemma vLLM chat URL: %s", chat_url)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(chat_url, headers=headers, json=request_body)

            if response.status_code == 404:
                logger.warning(
                    "Chat completions endpoint not found, "
                    "falling back to predict with Gemma chat template"
                )

                formatted_prompt = self._format_gemma_chat_template(prompt, system_instruction)
                fallback_body = {
                    "prompt": formatted_prompt,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                response = await client.post(predict_url, headers=headers, json=fallback_body)

            if response.status_code != 200:
                raise LLMError(f"vLLM endpoint error {response.status_code}: {response.text}")

            return response.json()  # type: ignore[no-any-return]

    def _parse_vllm_response(self, response_data: dict[str, Any], prompt: str) -> str:
        """Parse vLLM response and strip prompt echo."""
        generated_text = ""

        if "choices" in response_data and len(response_data["choices"]) > 0:
            choice = response_data["choices"][0]
            if "message" in choice and "content" in choice["message"]:
                generated_text = choice["message"]["content"]
            elif "text" in choice:
                generated_text = choice["text"]
            elif "delta" in choice and "content" in choice["delta"]:
                generated_text = choice["delta"]["content"]
            else:
                raise LLMError(f"Unexpected vLLM response format: {response_data}")
        elif "predictions" in response_data and len(response_data["predictions"]) > 0:
            generated_text = response_data["predictions"][0]
            if isinstance(generated_text, dict):
                generated_text = generated_text.get("content", generated_text.get("text", ""))
        elif "text" in response_data:
            generated_text = response_data["text"]
        else:
            raise LLMError(f"Unexpected response format: {response_data}")

        if not generated_text:
            raise LLMError("Empty response from Vertex AI MedGemma")

        generated_text = self._strip_prompt_echo(str(generated_text), prompt)

        if not generated_text:
            raise LLMError("Empty response after stripping prompt echo")

        return generated_text

    async def _generate_vllm_format(
        self,
        prompt: str,
        system_instruction: str | None,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Generate using vLLM/OpenAI-compatible chat format."""
        request_body = self._build_chat_request(prompt, system_instruction, temperature, max_tokens)
        chat_url, predict_url = self._build_endpoint_urls()
        headers = await self._get_auth_headers()

        response_data = await self._make_vllm_request(
            chat_url,
            predict_url,
            headers,
            request_body,
            prompt,
            system_instruction,
            temperature,
            max_tokens,
        )

        return self._parse_vllm_response(response_data, prompt)

    async def _generate_standard_format(
        self,
        prompt: str,
        system_instruction: str | None,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Generate using standard Vertex AI format."""
        full_prompt = prompt
        if system_instruction:
            full_prompt = f"{system_instruction}\n\n{prompt}"

        instances = [{"prompt": full_prompt}]
        parameters = {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        }

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, lambda: self.endpoint.predict(instances=instances, parameters=parameters)
        )

        if response.predictions:
            generated_text = response.predictions[0]
            if isinstance(generated_text, dict):
                generated_text = generated_text.get("content", generated_text.get("text", ""))

            if not generated_text:
                raise LLMError("Empty response from Vertex AI MedGemma")

            return str(generated_text)
        else:
            raise LLMError("No predictions in Vertex AI response")

    async def generate(
        self,
        prompt: str,
        system_instruction: str | None = None,
        image: bytes | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """Generate text completion using Vertex AI endpoint.

        Args:
            prompt: User prompt
            system_instruction: System instruction (optional)
            image: Image bytes (not supported)
            temperature: Sampling temperature
            max_tokens: Max output tokens

        Returns:
            Generated text

        Raises:
            LLMError: If generation fails
        """
        if image:
            logger.warning("Image input not supported by MedGemma. Ignoring image.")

        endpoint_type = settings.vertex_ai_endpoint_type.lower()
        if endpoint_type == "auto":
            endpoint_type = "vllm"

        for attempt in range(self.max_retries):
            try:
                if endpoint_type == "vllm":
                    return await self._generate_vllm_format(
                        prompt, system_instruction, temperature, max_tokens
                    )
                else:
                    return await self._generate_standard_format(
                        prompt, system_instruction, temperature, max_tokens
                    )
            except Exception as e:
                error_msg = str(e)
                if (
                    endpoint_type == "vllm"
                    and settings.vertex_ai_endpoint_type == "auto"
                    and ("Dedicated Endpoint" in error_msg or "domain" in error_msg)
                ):
                    logger.warning("vLLM format failed, trying standard format...")
                    endpoint_type = "standard"
                    continue

                logger.error(
                    f"Vertex AI MedGemma error (attempt {attempt + 1}/{self.max_retries}): {e}"
                )
                if attempt == self.max_retries - 1:
                    raise LLMError(f"Vertex AI MedGemma generation failed: {e}") from e
                await asyncio.sleep(2**attempt)

        raise LLMError("Vertex AI MedGemma generation failed after all retries")

    async def generate_structured(
        self,
        prompt: str,
        response_model: type[T],
        system_instruction: str | None = None,
        image: bytes | None = None,
        temperature: float = 0.7,
    ) -> T:
        """Generate structured output (Pydantic model)."""
        schema = response_model.model_json_schema()
        enhanced_prompt = f"{prompt}\n\nRespond with valid JSON matching this schema:\n{json.dumps(schema, indent=2)}\n\nJSON response:"

        response_text = await self.generate(
            prompt=enhanced_prompt,
            system_instruction=system_instruction,
            image=image,
            temperature=temperature,
        )

        try:
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()

            return response_model.model_validate_json(response_text)
        except Exception as e:
            raise LLMError(f"Failed to parse structured output: {e}") from e

    async def generate_stream(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        """Generate streaming response.

        Note: Vertex AI doesn't support streaming for MedGemma in the current config.
        Falls back to non-streaming generation.
        """
        logger.warning("Streaming not supported by MedGemma. Using non-streaming.")
        response = await self.generate(
            prompt=prompt,
            system_instruction=system_instruction,
            temperature=temperature,
        )
        yield response
