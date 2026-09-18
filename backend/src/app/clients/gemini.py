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


class AnswerTruncatedError(LLMError):
    """The model ran out of the token budget we set, mid-answer.

    A distinct type because it is the one failure here that resending the identical
    request cannot fix — the budget, not the provider, is what ran out. It is also a
    different fact for a caller to act on: "we cut this off" and "the provider failed"
    lead to different handling, and collapsing them into one generic error is how a
    truncated clinical answer gets retried three times and then reported as an outage.
    """


def _honours_sampling_parameters(model: str) -> bool:
    """Whether `temperature` and its relatives do anything on this model.

    Gemini 3.x manages its own sampling. The API accepts `temperature`, `top_p` and
    `top_k` and silently ignores them, which is worse than rejecting them: a call site
    that passes `temperature=0.2` reads as "make this deterministic for extraction" and
    gets nothing of the sort. Measured on `gemini-3.8-flash` with a high-entropy prompt —
    `temperature=0.0` produced four different answers in four calls, and 0.0, 2.0 and
    omitting it entirely were indistinguishable.

    This is a model-version check, which the transport deliberately is not. Which SDK
    reaches a model is a property of the provider and must never be guessed from a name;
    which parameters a model honours genuinely is a property of the model.
    """
    return not model.startswith("gemini-3")


def _finish_reason(response: Any) -> str | None:
    """The provider's own word for why generation stopped.

    Read defensively: the SDK returns an enum that renders as `FinishReason.MAX_TOKENS`,
    and older shapes returned a bare string. Misreading this is not cosmetic — it decides
    whether a half-written clinical answer is treated as a finished one.
    """
    candidates = getattr(response, "candidates", None)
    if not candidates:
        return None
    reason = getattr(candidates[0], "finish_reason", None)
    if reason is None:
        return None
    return str(getattr(reason, "name", reason)).rsplit(".", 1)[-1]


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
            # Vertex always goes through the Google Gen AI SDK against the global
            # endpoint. The previous implementation chose the SDK from the model name
            # (`startswith("gemini-3.1-")`), so every other model — including 3.8 Flash —
            # was quietly routed through the legacy `vertexai` SDK. Changing a model name
            # in configuration must never change which client path runs.
            from google import genai

            logger.info(
                "Initializing Gemini on Vertex: project=%s, location=%s, model=%s",
                settings.google_project_id,
                settings.vertex_ai_location,
                model,
            )

            # A Vertex init failure used to fall back to AI Studio silently. That hides a
            # misconfigured project behind a different quota, different data handling and
            # a deprecated SDK, and it is how production ended up on AI Studio without
            # anyone choosing it. Fail loudly instead.
            self.genai_client = genai.Client(
                vertexai=True,
                project=settings.google_project_id,
                location=settings.vertex_ai_location,
            )
            self.model_name = model
            logger.info("Initialized GeminiClient on Vertex: %s", model)
        else:
            # AI Studio is the explicit non-Vertex path, selected by leaving
            # `google_project_id` unset. It is still the live production path until that
            # setting is configured, so it stays until Vertex is verified in staging.
            import google.generativeai as genai_studio  # type: ignore[import-untyped]

            genai_studio.configure(api_key=api_key or settings.google_api_key)  # type: ignore[attr-defined]
            self.model = genai_studio.GenerativeModel(model)  # type: ignore[attr-defined,assignment]
            self.genai = genai_studio
            logger.info("Initialized GeminiClient with AI Studio: %s", model)

    async def generate(
        self,
        prompt: str,
        system_instruction: str | None = None,
        image: bytes | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        thinking_level: str | None = None,
        response_model: type[BaseModel] | None = None,
    ) -> str:
        """Generate text completion.

        Args:
            prompt: User prompt
            system_instruction: System instruction (optional)
            image: Image bytes for vision tasks (optional)
            temperature: Sampling temperature (0.0-1.0). Ignored by Gemini 3.x models,
                which manage their own sampling — see `_honours_sampling_parameters`.
            max_tokens: Max output tokens, covering reasoning and answer together
            thinking_level: Reasoning ceiling — LOW, MEDIUM or HIGH (Vertex only)
            response_model: Schema the answer must satisfy, enforced natively by Vertex.
                Ignored on AI Studio, which has no native structured-output path.

        Returns:
            Generated text

        Raises:
            LLMError: If generation fails after retries, or is truncated
        """
        if self.use_vertex_ai:
            return await self._generate_genai_sdk(
                prompt,
                system_instruction,
                image,
                temperature,
                max_tokens,
                thinking_level,
                response_model,
            )
        return await self._generate_ai_studio(
            prompt, system_instruction, image, temperature, max_tokens
        )

    async def _generate_genai_sdk(
        self,
        prompt: str,
        system_instruction: str | None,
        image: bytes | None,
        temperature: float,
        max_tokens: int,
        thinking_level: str | None = None,
        response_model: type[BaseModel] | None = None,
    ) -> str:
        """Generate using the Google Gen AI SDK.

        The caller's token budget is honoured. It used to be raised to
        `max(max_tokens, 8192)` on the belief that the SDK defaulted to something lower;
        measured, the SDK default is `None` and an unset budget produces byte-identical
        output to 8192, so the floor did nothing except bill every caller for up to
        sixteen times what it asked for (protocol §16, §17).

        What the floor did mask is real: thought tokens are charged against this same
        ceiling, so a budget sized for a non-thinking model starves the answer. That is
        handled where it belongs — by sizing budgets per workload, capping reasoning with
        `thinking_level`, and refusing to pass off a truncated answer as a complete one.
        """
        from google.genai import types

        config = types.GenerateContentConfig(
            # Sent only to models that honour it. Gemini 3.x ignores it, and passing a
            # value the model discards makes the call site look like it controls
            # determinism when it does not.
            temperature=(temperature if _honours_sampling_parameters(self.model_name) else None),
            max_output_tokens=max_tokens,
            system_instruction=system_instruction,
            thinking_config=(
                types.ThinkingConfig(thinking_level=thinking_level) if thinking_level else None
            ),
            # Native schema enforcement, rather than asking for a shape in the prompt and
            # hoping. Verified on the locked SDK that this coexists with `thinking_config`
            # — worth checking, because constrained decoding and reasoning collided badly
            # on MedGemma, where the grammar applied from the first token and the model
            # never got to think.
            response_mime_type="application/json" if response_model else None,
            response_schema=response_model,
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
        escalated = False
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

                # Truncation is decided before emptiness: a thinking model that spends its
                # whole budget reasoning returns no text at all, and that is a budget we
                # chose running out, not the model failing.
                if _finish_reason(response) == "MAX_TOKENS":
                    if not escalated:
                        # One regeneration at a larger budget. Deliberately a regeneration
                        # and not a continuation: stitching a second call onto a half
                        # sentence of clinical advice risks duplicated or contradictory
                        # instructions across the seam, and there is no resume API.
                        escalated = True
                        config.max_output_tokens = max_tokens * 2
                        logger.warning(
                            "Gemini answer hit the %d-token ceiling; regenerating at %d",
                            max_tokens,
                            max_tokens * 2,
                        )
                        continue
                    raise AnswerTruncatedError(
                        "Gemini answer was truncated at "
                        f"{max_tokens * 2} tokens. Returning it would present an "
                        "incomplete clinical answer as a finished one."
                    )

                if not response.text:
                    raise LLMError("Empty response from Gemini (Gen AI SDK)")

                return str(response.text)

            except TimeoutError:
                logger.warning(
                    f"Gemini (Gen AI SDK) timeout (attempt {attempt + 1}/{self.max_retries})"
                )
                if attempt == self.max_retries - 1:
                    raise LLMError("Gemini (Gen AI SDK) request timed out") from None
                await asyncio.sleep(2**attempt)

            except AnswerTruncatedError:
                # Terminal on purpose. Resending an identical request cannot widen a
                # budget, so retrying would burn two more calls and several seconds of
                # backoff before reporting the wrong cause. Re-raised ahead of the generic
                # handler so it reaches the caller as truncation rather than as an outage.
                raise

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
        model: Any = self.model
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
        max_tokens: int = 4096,
        thinking_level: str | None = None,
    ) -> T:
        """Generate structured output (Pydantic model).

        Args:
            prompt: User prompt
            response_model: Pydantic model class for output
            system_instruction: System instruction (optional)
            image: Image bytes for vision tasks (optional)
            temperature: Sampling temperature
            max_tokens: Max output tokens, covering reasoning and answer together
            thinking_level: Reasoning ceiling — LOW, MEDIUM or HIGH (Vertex only)

        Returns:
            Parsed Pydantic model instance

        Raises:
            LLMError: If generation or parsing fails
        """
        # Two explicit fixes live here. The budget: this used to call `generate` with no
        # `max_tokens`, taking the 2048 default and then the 8192 floor, so structured
        # calls silently ran at four times their stated budget. And the schema: it used to
        # be pasted into the prompt on every path, which *asks* for a shape rather than
        # constraining one — the approach our own protocol (§3, §11) measured as weaker,
        # and why schema failures surfaced here as unparseable prose rather than as a
        # refused request.
        if self.use_vertex_ai:
            response_text = await self.generate(
                prompt=prompt,
                system_instruction=system_instruction,
                image=image,
                temperature=temperature,
                max_tokens=max_tokens,
                thinking_level=thinking_level,
                response_model=response_model,
            )
        else:
            # AI Studio has no native structured-output path, so the schema goes in the
            # prompt and the parsing below is what actually enforces it.
            schema = response_model.model_json_schema()
            response_text = await self.generate(
                prompt=f"""{prompt}

Respond with valid JSON matching this schema:
{schema}

JSON response:""",
                system_instruction=system_instruction,
                image=image,
                temperature=temperature,
                max_tokens=max_tokens,
                thinking_level=thinking_level,
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
        max_tokens: int = 2048,
        thinking_level: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Generate streaming response (for chat).

        Args:
            prompt: User prompt
            system_instruction: System instruction (optional)
            temperature: Sampling temperature
            max_tokens: Max output tokens, covering reasoning and answer together
            thinking_level: Reasoning ceiling — LOW, MEDIUM or HIGH (Vertex only)

        Yields:
            Text chunks as they arrive

        Raises:
            LLMError: If streaming fails, or the answer was cut off
        """
        if self.use_vertex_ai:
            async for chunk in self._generate_stream_genai_sdk(
                prompt, system_instruction, temperature, max_tokens, thinking_level
            ):
                yield chunk
        else:
            async for chunk in self._generate_stream_ai_studio(
                prompt, system_instruction, temperature
            ):
                yield chunk

    async def _generate_stream_genai_sdk(
        self,
        prompt: str,
        system_instruction: str | None,
        temperature: float,
        max_tokens: int = 2048,
        thinking_level: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Generate streaming response using the Google Gen AI SDK.

        This path previously set no token ceiling and never read `finish_reason`, so a
        reply that ran out of budget simply stopped mid-sentence with no signal anywhere.
        This is the patient-facing path, so that is the worst place for it: the reader has
        no way to tell a finished answer from a severed one.
        """
        from google.genai import types

        config = types.GenerateContentConfig(
            # See `_honours_sampling_parameters`: ignored by Gemini 3.x, so not sent.
            temperature=(temperature if _honours_sampling_parameters(self.model_name) else None),
            system_instruction=system_instruction,
            max_output_tokens=max_tokens,
            thinking_config=(
                types.ThinkingConfig(thinking_level=thinking_level) if thinking_level else None
            ),
        )

        try:
            response = await self.genai_client.aio.models.generate_content_stream(
                model=self.model_name,
                contents=prompt,
                config=config,
            )

            last_reason: str | None = None
            async for chunk in response:
                last_reason = _finish_reason(chunk) or last_reason
                if chunk.text:
                    yield chunk.text

        except Exception as e:
            raise LLMError(f"Gemini (Gen AI SDK) streaming failed: {e}") from e

        if last_reason == "MAX_TOKENS":
            # Raised after the chunks rather than swallowed. The caller already has a
            # fallback for a failed stream, and completing the thought is better than
            # leaving a patient with a sentence that stops halfway.
            raise LLMError(f"Gemini streamed answer was cut off at the {max_tokens}-token ceiling")

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
        model: Any = self.model
        if system_instruction:
            model = self.genai.GenerativeModel(  # type: ignore[attr-defined]
                self.model_name,
                system_instruction=system_instruction,
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
            raise LLMError(f"Gemini (AI Studio) streaming failed: {e}") from e
