"""MedGemma client for medical task evaluation via Hugging Face Inference API."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from app.clients.gemini import GeminiClient
from app.config import settings
from app.core.exceptions import LLMError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class MedGemmaClient:
    """MedGemma client for medical tasks via Hugging Face Inference API.

    Uses same interface as GeminiClient for easy A/B testing.
    MedGemma is Google's medical-specialized model based on Gemma 3.

    Supports two deployment modes:
    1. Hugging Face Inference API (benchmarking) - requires HUGGINGFACE_API_TOKEN
    2. Gemini fallback (development) - used when HF token not configured

    Available MedGemma models:
    - google/medgemma-1.5-4b-it (smallest, fastest)
    - google/medgemma-4b-it (medium)
    - google/medgemma-27b-it (largest, best quality)

    Example:
        # Swap GeminiClient for MedGemmaClient
        client = MedGemmaClient(model="google/medgemma-4b-it")
        response = await client.generate(prompt="Explain this lab result")
    """

    # Hugging Face Serverless Inference API base URL
    HF_API_BASE = "https://api-inference.huggingface.co/models"

    def __init__(
        self,
        model: str = "google/medgemma-4b-it",
        api_token: str | None = None,
        max_retries: int = 3,
        timeout: int = 60,
    ) -> None:
        """Initialize MedGemma client.

        Args:
            model: MedGemma model ID (google/medgemma-4b-it, google/medgemma-27b-it, etc.)
            api_token: Hugging Face API token (defaults to settings.huggingface_api_token)
            max_retries: Max retry attempts
            timeout: Request timeout in seconds
        """
        self.model_name = model
        self.max_retries = max_retries
        self.timeout = timeout

        # Get API token
        self.api_token = api_token or settings.huggingface_api_token

        # Check if Vertex AI endpoint is configured
        vertex_endpoint = settings.vertex_ai_medgemma_endpoint

        if vertex_endpoint:
            # Use Vertex AI
            try:
                from google.cloud import aiplatform

                aiplatform.init(
                    project=settings.google_project_id,
                    location=settings.vertex_ai_location,
                )
                self.endpoint = aiplatform.Endpoint(vertex_endpoint)
                self.use_vertex = True
                self.use_hf = False
                logger.info(f"Initialized MedGemmaClient with Vertex AI endpoint: {vertex_endpoint}")
            except Exception as e:
                logger.warning(f"Failed to initialize Vertex AI: {e}. Trying HF API.")
                self.use_vertex = False
                self.use_hf = bool(self.api_token)
        elif self.api_token:
            # Use Hugging Face Inference API
            self.use_hf = True
            self.use_vertex = False
            self.api_url = f"{self.HF_API_BASE}/{model}"
            self.headers = {"Authorization": f"Bearer {self.api_token}"}
            logger.info(f"Initialized MedGemmaClient with Hugging Face API: {model}")
        else:
            # Fallback to Gemini
            logger.warning(
                "Neither VERTEX_AI_MEDGEMMA_ENDPOINT nor HUGGINGFACE_API_TOKEN set. Falling back to Gemini."
            )
            self.use_hf = False
            self.use_vertex = False
            self._fallback_client = GeminiClient(
                model="gemini-2.5-flash",
                max_retries=max_retries,
                timeout=timeout,
            )

    async def _generate_vertex_ai(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """Generate text using Vertex AI endpoint.
        
        Automatically detects endpoint type (standard vs vLLM) or uses configured type.

        Args:
            prompt: User prompt
            system_instruction: System instruction (optional)
            temperature: Sampling temperature
            max_tokens: Max output tokens

        Returns:
            Generated text

        Raises:
            LLMError: If generation fails
        """
        # Determine endpoint type
        endpoint_type = settings.vertex_ai_endpoint_type.lower()
        
        if endpoint_type == "auto":
            # Auto-detect: vLLM endpoints typically have "vllm" in serving spec or use dedicated domains
            # Try vLLM format first (more common for MedGemma), fall back to standard
            endpoint_type = "vllm"
        
        # Try the detected/configured format
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
                
                # If auto-detect and we get a format error, try the other format
                if endpoint_type == "vllm" and settings.vertex_ai_endpoint_type == "auto":
                    if "Dedicated Endpoint" in error_msg or "domain" in error_msg:
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

    @staticmethod
    def _strip_prompt_echo(text: str, prompt: str) -> str:
        """Strip echoed prompt from vLLM response.

        vLLM endpoints often echo the full prompt before the response.
        Common patterns:
          - '{prompt}\nOutput:\n{response}'
          - '{prompt}\n\n{response}'
          - '{system}\n\n{prompt}\nOutput:\n{response}'
        """
        # Pattern 1: explicit "Output:" separator
        if "\nOutput:" in text:
            parts = text.split("\nOutput:", 1)
            cleaned = parts[1].strip()
            if cleaned:
                return cleaned

        # Pattern 2: response starts with prompt text (echo)
        # Check if the first ~80 chars of the prompt appear at the start
        prompt_prefix = prompt.strip()[:80]
        if text.startswith(prompt_prefix):
            # Find where the prompt ends and response begins
            # Look for double-newline after the prompt
            prompt_end = text.find("\n\n", len(prompt_prefix))
            if prompt_end != -1:
                cleaned = text[prompt_end:].strip()
                if cleaned:
                    return cleaned

        # No echo detected — return as-is
        return text.strip()

    @staticmethod
    def _format_gemma_chat_template(prompt: str, system_instruction: str | None = None) -> str:
        """Format prompt using Gemma/MedGemma chat template.

        This is critical: MedGemma-it is instruction-tuned and expects
        this exact format. Without it, the model does text completion
        instead of instruction following.

        Args:
            prompt: User prompt
            system_instruction: Optional system instruction

        Returns:
            Formatted prompt with Gemma chat template markers
        """
        formatted_prompt = ""
        if system_instruction:
            formatted_prompt += f"<start_of_turn>user\n{system_instruction}\n\n{prompt}<end_of_turn>\n"
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
        """Build chat and predict endpoint URLs from Vertex AI endpoint path.

        Returns:
            Tuple of (chat_url, predict_url)
        """
        # Extract endpoint ID from the full endpoint path
        # Format: projects/PROJECT_NUMBER/locations/LOCATION/endpoints/ENDPOINT_ID
        endpoint_parts = settings.vertex_ai_medgemma_endpoint.split('/')
        endpoint_id = endpoint_parts[-1]
        project_number = endpoint_parts[1]
        location = endpoint_parts[3]

        # Build dedicated endpoint URL
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
        creds.refresh(auth_req)
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
            # Try chat completions endpoint first
            response = await client.post(chat_url, headers=headers, json=request_body)

            if response.status_code == 404:
                # Chat completions not available — fall back to raw predict
                # with Gemma chat template format
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

            return response.json()

    def _parse_vllm_response(self, response_data: dict[str, Any], prompt: str) -> str:
        """Parse vLLM response and strip prompt echo."""
        generated_text = ""

        if "choices" in response_data and len(response_data["choices"]) > 0:
            # OpenAI chat completions format
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
            # Vertex AI predict format
            generated_text = response_data["predictions"][0]
            if isinstance(generated_text, dict):
                generated_text = generated_text.get("content", generated_text.get("text", ""))
        elif "text" in response_data:
            generated_text = response_data["text"]
        else:
            raise LLMError(f"Unexpected response format: {response_data}")

        if not generated_text:
            raise LLMError("Empty response from Vertex AI MedGemma")

        # Safety: strip any residual prompt echo
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
        """Generate using vLLM/OpenAI-compatible chat format (for dedicated endpoints).

        Uses the OpenAI-compatible ``/v1/chat/completions`` endpoint exposed by
        vLLM on Vertex AI dedicated endpoints.  This gives proper system/user
        message separation and eliminates prompt-echo issues.
        """
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
        # Build prompt with system instruction
        full_prompt = prompt
        if system_instruction:
            full_prompt = f"{system_instruction}\n\n{prompt}"

        # Prepare prediction request
        instances = [{"prompt": full_prompt}]
        parameters = {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        }

        # Make prediction (synchronous call, but we're in async context)
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.endpoint.predict(instances=instances, parameters=parameters)
        )

        # Extract generated text from response
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
        """Generate text completion.

        Args:
            prompt: User prompt
            system_instruction: System instruction (optional)
            image: Image bytes for vision tasks (optional, not supported by MedGemma)
            temperature: Sampling temperature
            max_tokens: Max output tokens

        Returns:
            Generated text

        Raises:
            LLMError: If generation fails
        """
        # Use Vertex AI if configured
        if self.use_vertex:
            return await self._generate_vertex_ai(
                prompt=prompt,
                system_instruction=system_instruction,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        # Use Hugging Face if configured
        if not self.use_hf:
            return await self._fallback_client.generate(
                prompt=prompt,
                system_instruction=system_instruction,
                image=image,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        # Hugging Face API implementation
        # Image not supported by MedGemma text models
        if image:
            logger.warning("Image input not supported by MedGemma. Ignoring image.")

        # Build prompt with system instruction
        full_prompt = prompt
        if system_instruction:
            full_prompt = f"{system_instruction}\n\n{prompt}"

        # Retry logic with exponential backoff
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        self.api_url,
                        headers=self.headers,
                        json={
                            "inputs": full_prompt,
                            "parameters": {
                                "temperature": temperature,
                                "max_new_tokens": max_tokens,
                                "return_full_text": False,
                            },
                        },
                    )

                    # Handle rate limiting (503) - model is loading
                    if response.status_code == 503:
                        error_data = response.json()
                        if "estimated_time" in error_data:
                            wait_time = error_data["estimated_time"]
                            logger.warning(
                                f"Model loading, waiting {wait_time}s "
                                f"(attempt {attempt + 1}/{self.max_retries})"
                            )
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            logger.warning(
                                f"Service unavailable (attempt {attempt + 1}/{self.max_retries})"
                            )
                            await asyncio.sleep(2**attempt)
                            continue

                    # Handle other errors
                    if response.status_code != 200:
                        error_msg = f"HF API error {response.status_code}: {response.text}"
                        logger.error(error_msg)
                        if attempt == self.max_retries - 1:
                            raise LLMError(error_msg)
                        await asyncio.sleep(2**attempt)
                        continue

                    # Parse response
                    result = response.json()

                    # HF API returns list of dicts with "generated_text" key
                    if isinstance(result, list) and len(result) > 0:
                        generated_text = result[0].get("generated_text", "")
                    elif isinstance(result, dict):
                        generated_text = result.get("generated_text", "")
                    else:
                        raise LLMError(f"Unexpected HF API response format: {result}")

                    if not generated_text:
                        raise LLMError("Empty response from MedGemma")

                    return str(generated_text)

            except httpx.TimeoutException:
                logger.warning(
                    f"MedGemma timeout (attempt {attempt + 1}/{self.max_retries})"
                )
                if attempt == self.max_retries - 1:
                    raise LLMError("MedGemma request timed out") from None
                await asyncio.sleep(2**attempt)

            except Exception as e:
                logger.error(
                    f"MedGemma error (attempt {attempt + 1}/{self.max_retries}): {e}"
                )
                if attempt == self.max_retries - 1:
                    raise LLMError(f"MedGemma generation failed: {e}") from e
                await asyncio.sleep(2**attempt)

        raise LLMError("MedGemma generation failed after all retries")

    async def generate_structured(
        self,
        prompt: str,
        response_model: type[T],
        system_instruction: str | None = None,
        image: bytes | None = None,
        temperature: float = 0.7,
    ) -> T:
        """Generate structured output (Pydantic model).

        Args:
            prompt: User prompt
            response_model: Pydantic model class for output
            system_instruction: System instruction (optional)
            image: Image bytes for vision tasks (optional, not supported)
            temperature: Sampling temperature

        Returns:
            Parsed Pydantic model instance

        Raises:
            LLMError: If generation or parsing fails
        """
        # Use fallback client if neither Vertex AI nor HF configured
        if not self.use_hf and not self.use_vertex:
            return await self._fallback_client.generate_structured(
                prompt=prompt,
                response_model=response_model,
                system_instruction=system_instruction,
                image=image,
                temperature=temperature,
            )

        # Add JSON schema to prompt
        schema = response_model.model_json_schema()
        enhanced_prompt = f"""{prompt}

Respond with valid JSON matching this schema:
{json.dumps(schema, indent=2)}

JSON response:"""

        response_text = await self.generate(
            prompt=enhanced_prompt,
            system_instruction=system_instruction,
            temperature=temperature,
        )

        # Parse JSON response
        try:
            # Extract JSON from markdown code blocks if present
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

        Note: Vertex AI and HF Inference API don't support streaming for MedGemma.
        Falls back to non-streaming generation.

        Args:
            prompt: User prompt
            system_instruction: System instruction (optional)
            temperature: Sampling temperature

        Yields:
            Text chunks (single chunk for non-streaming)

        Raises:
            LLMError: If streaming fails
        """
        # Use fallback client if neither Vertex AI nor HF configured
        if not self.use_hf and not self.use_vertex:
            async for chunk in self._fallback_client.generate_stream(
                prompt=prompt,
                system_instruction=system_instruction,
                temperature=temperature,
            ):
                yield chunk
            return

        # Neither Vertex AI nor HF Inference API support streaming for MedGemma
        # Fall back to non-streaming and yield as single chunk
        logger.warning("Streaming not supported by MedGemma. Using non-streaming.")
        response = await self.generate(
            prompt=prompt,
            system_instruction=system_instruction,
            temperature=temperature,
        )
        yield response
