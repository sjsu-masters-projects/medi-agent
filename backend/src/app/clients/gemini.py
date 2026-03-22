"""Gemini LLM client with retry, rate limiting, and structured output.

Supports both AI Studio (free tier) and Vertex AI (production) modes.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import Any, TypeVar, cast

from pydantic import BaseModel

from app.config import settings
from app.core.exceptions import LLMError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class GeminiClient:
    """Production-grade Gemini client.

    Supports two modes:
    1. AI Studio API (free tier, for development)
    2. Vertex AI (production-grade, recommended for benchmarking)

    Features:
    - Automatic retry with exponential backoff
    - Rate limiting
    - Structured output (Pydantic models)
    - Vision support (images + PDFs)
    - Streaming

    Example:
        # AI Studio (free tier)
        client = GeminiClient(model="gemini-3-flash")

        # Vertex AI (production)
        client = GeminiClient(model="gemini-3.1-pro", use_vertex_ai=True)

        response = await client.generate(
            prompt="Explain this medical document",
            image=document_bytes
        )
    """

    def __init__(
        self,
        model: str = "gemini-3-flash",
        api_key: str | None = None,
        use_vertex_ai: bool | None = None,
        max_retries: int = 3,
        timeout: int = 60,
    ) -> None:
        """Initialize Gemini client.

        Args:
            model: Model name (gemini-3-flash, gemini-3.1-pro, etc.)
            api_key: Google API key (defaults to settings.google_api_key)
            use_vertex_ai: Use Vertex AI instead of AI Studio (auto-detects if None)
            max_retries: Max retry attempts on failure
            timeout: Request timeout in seconds
        """
        self.model_name = model
        self.max_retries = max_retries
        self.timeout = timeout

        # Auto-detect Vertex AI usage
        if use_vertex_ai is None:
            # Use Vertex AI if project ID is configured
            use_vertex_ai = bool(settings.google_project_id)

        self.use_vertex_ai = use_vertex_ai

        if self.use_vertex_ai:
            # Initialize Vertex AI
            try:
                # Gemini 3.x preview models require Google Gen AI SDK with location="global"
                is_preview_model = "3." in model and "preview" in model

                if is_preview_model:
                    # Use Google Gen AI SDK for preview models
                    from google import genai

                    logger.info(
                        f"Attempting Google Gen AI SDK init: project={settings.google_project_id}, location=global, model={model}"
                    )

                    self.genai_client = genai.Client(
                        vertexai=True,
                        project=settings.google_project_id,
                        location="global",
                    )
                    self.model_name = model
                    self.is_genai_sdk = True
                    logger.info(
                        f"✅ Successfully initialized GeminiClient with Google Gen AI SDK: {model} (location: global)"
                    )
                else:
                    # Use Vertex AI SDK for non-preview models
                    import vertexai
                    from vertexai.generative_models import GenerativeModel

                    location = settings.vertex_ai_location
                    logger.info(
                        f"Attempting Vertex AI init: project={settings.google_project_id}, location={location}, model={model}"
                    )

                    vertexai.init(
                        project=settings.google_project_id,
                        location=location,
                    )
                    self.model = GenerativeModel(model)
                    self.vertex_ai_model = GenerativeModel  # Store for system instruction
                    self.is_genai_sdk = False
                    logger.info(
                        f"✅ Successfully initialized GeminiClient with Vertex AI: {model} (location: {location})"
                    )
            except Exception as e:
                logger.error(f"❌ Failed to initialize Vertex AI: {type(e).__name__}: {e}")
                logger.error("Falling back to AI Studio (free tier with quotas)")
                self.use_vertex_ai = False
                self.is_genai_sdk = False

        if not self.use_vertex_ai:
            # Use AI Studio API
            import google.generativeai as genai  # type: ignore[import-untyped]

            genai.configure(api_key=api_key or settings.google_api_key)  # type: ignore[attr-defined]
            self.model = genai.GenerativeModel(model)  # type: ignore[attr-defined]
            self.genai = genai
            self.is_genai_sdk = False
            logger.info(f"Initialized GeminiClient with AI Studio: {model}")

    async def generate(
        self,
        prompt: str,
        system_instruction: str | None = None,
        image: bytes | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        thinking_mode: bool = False,
    ) -> str:
        """Generate text completion.

        Args:
            prompt: User prompt
            system_instruction: System instruction (optional)
            image: Image bytes for vision tasks (optional)
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Max output tokens
            thinking_mode: Enable thinking mode (Pro only)

        Returns:
            Generated text

        Raises:
            LLMError: If generation fails after retries
        """
        if thinking_mode and "thinking" not in self.model_name:
            raise ValueError("Thinking mode requires gemini-2.0-flash-thinking-exp model")

        if self.use_vertex_ai and hasattr(self, "is_genai_sdk") and self.is_genai_sdk:
            return await self._generate_genai_sdk(
                prompt, system_instruction, image, temperature, max_tokens
            )
        elif self.use_vertex_ai:
            return await self._generate_vertex_ai(
                prompt, system_instruction, image, temperature, max_tokens
            )
        else:
            return await self._generate_ai_studio(
                prompt, system_instruction, image, temperature, max_tokens
            )

    async def _generate_vertex_ai(
        self,
        prompt: str,
        system_instruction: str | None,
        image: bytes | None,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Generate using Vertex AI."""
        from vertexai.generative_models import (
            GenerationConfig,
            HarmBlockThreshold,
            HarmCategory,
            Part,
        )

        config = GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )

        # Disable safety filters for medical content
        safety_settings = {
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        }

        # Build content parts
        parts: list[Any] = [prompt]
        if image:
            parts.append(Part.from_data(data=image, mime_type="image/jpeg"))

        # Create model with system instruction if provided
        model = self.model
        if system_instruction:
            model = self.vertex_ai_model(
                self.model_name,
                system_instruction=[system_instruction],
            )

        # Retry logic
        for attempt in range(self.max_retries):
            try:
                response = await asyncio.wait_for(
                    model.generate_content_async(
                        parts,
                        generation_config=config,
                        safety_settings=safety_settings,
                    ),
                    timeout=self.timeout,
                )

                # Log finish reason for debugging
                if hasattr(response, "candidates") and response.candidates:
                    finish_reason = response.candidates[0].finish_reason
                    logger.debug(f"Vertex AI finish_reason: {finish_reason}")

                if not response.text:
                    raise LLMError("Empty response from Gemini (Vertex AI)")

                return str(response.text)

            except TimeoutError:
                logger.warning(
                    f"Gemini (Vertex AI) timeout (attempt {attempt + 1}/{self.max_retries})"
                )
                if attempt == self.max_retries - 1:
                    raise LLMError("Gemini (Vertex AI) request timed out") from None
                await asyncio.sleep(2**attempt)

            except Exception as e:
                logger.error(
                    f"Gemini (Vertex AI) error (attempt {attempt + 1}/{self.max_retries}): {e}"
                )
                if attempt == self.max_retries - 1:
                    raise LLMError(f"Gemini (Vertex AI) generation failed: {e}") from e
                await asyncio.sleep(2**attempt)

        raise LLMError("Gemini (Vertex AI) generation failed after all retries")

    async def _generate_genai_sdk(
        self,
        prompt: str,
        system_instruction: str | None,
        image: bytes | None,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Generate using Google Gen AI SDK (for Gemini 3.1 preview models)."""
        from google.genai import types

        # Gen AI SDK seems to have a lower default max_output_tokens
        # Increase it significantly to avoid truncation
        effective_max_tokens = max(max_tokens, 8192)

        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=effective_max_tokens,
            system_instruction=system_instruction,
        )

        # Build content parts
        contents: list[Any] = [prompt]
        if image:
            contents.append(
                types.Part.from_bytes(
                    data=image,
                    mime_type="image/jpeg",
                )
            )

        # Retry logic
        for attempt in range(self.max_retries):
            try:
                response = await asyncio.wait_for(
                    self.genai_client.aio.models.generate_content(
                        model=self.model_name,
                        contents=contents,
                        config=config,
                    ),
                    timeout=self.timeout,
                )

                # Log finish reason for debugging
                if hasattr(response, "candidates") and response.candidates:
                    finish_reason = getattr(response.candidates[0], "finish_reason", "UNKNOWN")
                    logger.debug(f"Gen AI SDK finish_reason: {finish_reason}")
                    logger.debug(f"Gen AI SDK response type: {type(response)}")
                    logger.debug(
                        f"Gen AI SDK response.text length: {len(response.text) if response.text else 0}"
                    )

                if not response.text:
                    raise LLMError("Empty response from Gemini (Gen AI SDK)")

                # The response.text property should contain the full response
                # If it's truncated, we need to check the finish_reason
                full_text = str(response.text)

                if hasattr(response, "candidates") and response.candidates:
                    finish_reason = getattr(response.candidates[0], "finish_reason", None)
                    if finish_reason and finish_reason != "STOP":
                        logger.warning(
                            f"Gen AI SDK response may be incomplete. Finish reason: {finish_reason}"
                        )

                return full_text

            except TimeoutError:
                logger.warning(
                    f"Gemini (Gen AI SDK) timeout (attempt {attempt + 1}/{self.max_retries})"
                )
                if attempt == self.max_retries - 1:
                    raise LLMError("Gemini (Gen AI SDK) request timed out") from None
                await asyncio.sleep(2**attempt)

            except Exception as e:
                logger.error(
                    f"Gemini (Gen AI SDK) error (attempt {attempt + 1}/{self.max_retries}): {e}"
                )
                if attempt == self.max_retries - 1:
                    raise LLMError(f"Gemini (Gen AI SDK) generation failed: {e}") from e
                await asyncio.sleep(2**attempt)

        raise LLMError("Gemini (Gen AI SDK) generation failed after all retries")

    async def _generate_ai_studio(
        self,
        prompt: str,
        system_instruction: str | None,
        image: bytes | None,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Generate using AI Studio."""
        from google.generativeai.types import (  # type: ignore[import-untyped]
            GenerateContentResponse,
            GenerationConfig,
        )

        config = GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )

        # Build content parts
        parts: list[Any] = [prompt]
        if image:
            parts.append({"mime_type": "image/jpeg", "data": image})

        # Create model with system instruction if provided
        model = self.model
        if system_instruction:
            model = self.genai.GenerativeModel(  # type: ignore[attr-defined]
                self.model_name,
                system_instruction=system_instruction,
            )

        # Retry logic
        for attempt in range(self.max_retries):
            try:
                response_coro = model.generate_content_async(
                    parts,
                    generation_config=config,
                )
                response = cast(
                    GenerateContentResponse,
                    await asyncio.wait_for(response_coro, timeout=self.timeout),  # type: ignore[arg-type]
                )

                if not response.text:
                    raise LLMError("Empty response from Gemini (AI Studio)")

                return str(response.text)

            except TimeoutError:
                logger.warning(
                    f"Gemini (AI Studio) timeout (attempt {attempt + 1}/{self.max_retries})"
                )
                if attempt == self.max_retries - 1:
                    raise LLMError("Gemini (AI Studio) request timed out") from None
                await asyncio.sleep(2**attempt)

            except Exception as e:
                logger.error(
                    f"Gemini (AI Studio) error (attempt {attempt + 1}/{self.max_retries}): {e}"
                )
                if attempt == self.max_retries - 1:
                    raise LLMError(f"Gemini (AI Studio) generation failed: {e}") from e
                await asyncio.sleep(2**attempt)

        raise LLMError("Gemini (AI Studio) generation failed after all retries")

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
            image: Image bytes for vision tasks (optional)
            temperature: Sampling temperature

        Returns:
            Parsed Pydantic model instance

        Raises:
            LLMError: If generation or parsing fails
        """
        # Add JSON schema to prompt
        schema = response_model.model_json_schema()
        enhanced_prompt = f"""{prompt}

Respond with valid JSON matching this schema:
{schema}

JSON response:"""

        response_text = await self.generate(
            prompt=enhanced_prompt,
            system_instruction=system_instruction,
            image=image,
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
        """Generate streaming response (for chat).

        Args:
            prompt: User prompt
            system_instruction: System instruction (optional)
            temperature: Sampling temperature

        Yields:
            Text chunks as they arrive

        Raises:
            LLMError: If streaming fails
        """
        if self.use_vertex_ai and hasattr(self, "is_genai_sdk") and self.is_genai_sdk:
            async for chunk in self._generate_stream_genai_sdk(
                prompt, system_instruction, temperature
            ):
                yield chunk
        elif self.use_vertex_ai:
            async for chunk in self._generate_stream_vertex_ai(
                prompt, system_instruction, temperature
            ):
                yield chunk
        else:
            async for chunk in self._generate_stream_ai_studio(
                prompt, system_instruction, temperature
            ):
                yield chunk

    async def _generate_stream_vertex_ai(
        self,
        prompt: str,
        system_instruction: str | None,
        temperature: float,
    ) -> AsyncGenerator[str, None]:
        """Generate streaming response using Vertex AI."""
        from vertexai.generative_models import GenerationConfig

        config = GenerationConfig(temperature=temperature)

        # Create model with system instruction if provided
        model = self.model
        if system_instruction:
            model = self.vertex_ai_model(
                self.model_name,
                system_instruction=[system_instruction],
            )

        try:
            response = await model.generate_content_async(
                prompt,
                generation_config=config,
                stream=True,
            )

            async for chunk in response:
                if chunk.text:
                    yield chunk.text

        except Exception as e:
            raise LLMError(f"Gemini (Vertex AI) streaming failed: {e}") from e

    async def _generate_stream_genai_sdk(
        self,
        prompt: str,
        system_instruction: str | None,
        temperature: float,
    ) -> AsyncGenerator[str, None]:
        """Generate streaming response using Google Gen AI SDK."""
        from google.genai import types

        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_instruction,
        )

        try:
            response = await self.genai_client.aio.models.generate_content_stream(
                model=self.model_name,
                contents=prompt,
                config=config,
            )

            async for chunk in response:
                if chunk.text:
                    yield chunk.text

        except Exception as e:
            raise LLMError(f"Gemini (Gen AI SDK) streaming failed: {e}") from e

    async def _generate_stream_ai_studio(
        self,
        prompt: str,
        system_instruction: str | None,
        temperature: float,
    ) -> AsyncGenerator[str, None]:
        """Generate streaming response using AI Studio."""
        from google.generativeai.types import GenerationConfig  # type: ignore[import-untyped]

        config = GenerationConfig(temperature=temperature)

        # Create model with system instruction if provided
        model = self.model
        if system_instruction:
            model = self.genai.GenerativeModel(  # type: ignore[attr-defined]
                self.model_name,
                system_instruction=system_instruction,
            )

        try:
            response = await model.generate_content_async(  # type: ignore[call-arg]
                prompt,
                generation_config=config,
                stream=True,
            )

            async for chunk in response:
                if chunk.text:
                    yield chunk.text

        except Exception as e:
            raise LLMError(f"Gemini (AI Studio) streaming failed: {e}") from e
