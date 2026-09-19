"""Tests for GeminiClient."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from app.core.exceptions import LLMError


class TestResponse(BaseModel):
    """Test response model."""

    message: str
    count: int


@pytest.fixture
def mock_genai_module():
    """Mock google.generativeai module used by AI Studio path."""
    mock_module = MagicMock()
    mock_model = AsyncMock()
    mock_module.GenerativeModel.return_value = mock_model
    return mock_module, mock_model


@pytest.fixture
def mock_settings():
    """Mock settings for AI Studio mode (no Vertex AI)."""
    with patch("app.clients.gemini.settings") as mock:
        mock.google_api_key = "test-api-key"
        mock.google_project_id = ""  # No project → AI Studio mode
        mock.vertex_ai_location = "us-central1"
        mock.gemini_vertex_ai_location = "global"
        yield mock


@pytest.fixture
def gemini_client(mock_settings, mock_genai_module):
    """Create GeminiClient in AI Studio mode with mocked genai."""
    mock_module, mock_model = mock_genai_module

    with patch.dict("sys.modules", {"google.generativeai": mock_module}):
        from app.clients.gemini import GeminiClient

        client = GeminiClient(
            model="gemini-2.0-flash-exp",
            api_key="test-key",
        )

    # Override model with our mock for test control
    client.model = mock_model
    client.genai = mock_module
    return client


# ============================================================
# Text Generation Tests
# ============================================================


@pytest.mark.asyncio
async def test_generate_success(gemini_client):
    """Test successful text generation."""
    mock_response = MagicMock()
    mock_response.text = "Generated text response"

    gemini_client.model.generate_content_async = AsyncMock(return_value=mock_response)

    result = await gemini_client.generate(prompt="Test prompt")

    assert result == "Generated text response"
    gemini_client.model.generate_content_async.assert_called_once()


@pytest.mark.asyncio
async def test_generate_with_system_instruction(gemini_client):
    """Test generation with system instruction."""
    mock_response = MagicMock()
    mock_response.text = "Response with system instruction"

    mock_new_model = AsyncMock()
    mock_new_model.generate_content_async = AsyncMock(return_value=mock_response)
    gemini_client.genai.GenerativeModel.return_value = mock_new_model

    result = await gemini_client.generate(
        prompt="Test prompt",
        system_instruction="You are a helpful assistant",
    )

    assert result == "Response with system instruction"
    gemini_client.genai.GenerativeModel.assert_called_with(
        "gemini-2.0-flash-exp",
        system_instruction="You are a helpful assistant",
    )


@pytest.mark.asyncio
async def test_generate_with_image(gemini_client):
    """Test generation with image."""
    mock_response = MagicMock()
    mock_response.text = "Image analysis response"

    gemini_client.model.generate_content_async = AsyncMock(return_value=mock_response)

    image_bytes = b"fake_image_data"
    result = await gemini_client.generate(prompt="Describe this image", image=image_bytes)

    assert result == "Image analysis response"
    call_args = gemini_client.model.generate_content_async.call_args
    parts = call_args.args[0]
    assert len(parts) == 2
    assert parts[0] == "Describe this image"
    assert parts[1]["mime_type"] == "image/jpeg"


@pytest.mark.asyncio
async def test_generate_empty_response(gemini_client):
    """Test handling of empty response."""
    mock_response = MagicMock()
    mock_response.text = ""

    gemini_client.model.generate_content_async = AsyncMock(return_value=mock_response)

    with pytest.raises(LLMError, match="Empty response from Gemini"):
        await gemini_client.generate(prompt="Test prompt")


@pytest.mark.asyncio
async def test_generate_timeout(gemini_client):
    """Test timeout handling with retries."""
    gemini_client.model.generate_content_async = AsyncMock(side_effect=TimeoutError())
    gemini_client.max_retries = 2

    with pytest.raises(LLMError, match="timed out"):
        await gemini_client.generate(prompt="Test prompt")

    assert gemini_client.model.generate_content_async.call_count == 2


@pytest.mark.asyncio
async def test_generate_retry_then_success(gemini_client):
    """Test retry logic with eventual success."""
    mock_response = MagicMock()
    mock_response.text = "Success after retry"

    gemini_client.model.generate_content_async = AsyncMock(
        side_effect=[TimeoutError(), mock_response]
    )
    gemini_client.max_retries = 3

    result = await gemini_client.generate(prompt="Test prompt")

    assert result == "Success after retry"
    assert gemini_client.model.generate_content_async.call_count == 2


@pytest.mark.asyncio
async def test_generate_exception(gemini_client):
    """Test handling of general exceptions."""
    gemini_client.model.generate_content_async = AsyncMock(side_effect=ValueError("API error"))
    gemini_client.max_retries = 2

    with pytest.raises(LLMError, match="generation failed"):
        await gemini_client.generate(prompt="Test prompt")


# ============================================================
# Structured Output Tests
# ============================================================


@pytest.mark.asyncio
async def test_generate_structured_success(gemini_client):
    """Test structured output generation."""
    mock_response = MagicMock()
    mock_response.text = '{"message": "Hello", "count": 42}'

    gemini_client.model.generate_content_async = AsyncMock(return_value=mock_response)

    result = await gemini_client.generate_structured(
        prompt="Generate structured data",
        response_model=TestResponse,
    )

    assert isinstance(result, TestResponse)
    assert result.message == "Hello"
    assert result.count == 42


@pytest.mark.asyncio
async def test_generate_structured_with_markdown(gemini_client):
    """Test structured output with markdown code blocks."""
    mock_response = MagicMock()
    mock_response.text = '```json\n{"message": "Hello", "count": 42}\n```'

    gemini_client.model.generate_content_async = AsyncMock(return_value=mock_response)

    result = await gemini_client.generate_structured(
        prompt="Generate structured data",
        response_model=TestResponse,
    )

    assert isinstance(result, TestResponse)
    assert result.message == "Hello"
    assert result.count == 42


@pytest.mark.asyncio
async def test_generate_structured_invalid_json(gemini_client):
    """Test handling of invalid JSON in structured output."""
    mock_response = MagicMock()
    mock_response.text = "Not valid JSON"

    gemini_client.model.generate_content_async = AsyncMock(return_value=mock_response)

    with pytest.raises(LLMError, match="Failed to parse structured output"):
        await gemini_client.generate_structured(
            prompt="Generate structured data",
            response_model=TestResponse,
        )


# ============================================================
# Streaming Tests
# ============================================================


@pytest.mark.asyncio
async def test_generate_stream(gemini_client):
    """Test streaming generation."""
    mock_chunk1 = MagicMock()
    mock_chunk1.text = "Hello "
    mock_chunk2 = MagicMock()
    mock_chunk2.text = "world"

    async def mock_stream():
        yield mock_chunk1
        yield mock_chunk2

    gemini_client.model.generate_content_async = AsyncMock(return_value=mock_stream())

    chunks = []
    async for chunk in gemini_client.generate_stream(prompt="Test prompt"):
        chunks.append(chunk)

    assert chunks == ["Hello ", "world"]


# `thinking_mode` was removed with the model it gated. It required
# `gemini-2.0-flash-thinking-exp`, retired long ago, and no caller ever passed it. Thinking
# on Gemini 3.x is always on and is shaped by `thinking_level` instead; see
# tests/unit/clients/test_gemini_token_budget.py.


# ============================================================
# Initialization Tests
# ============================================================


def test_client_initialization(mock_settings):
    """Test client initialization in AI Studio mode."""
    mock_genai = MagicMock()

    with patch.dict(
        "sys.modules",
        {"google.generativeai": mock_genai, "google.generativeai.types": MagicMock()},
    ):
        from app.clients.gemini import GeminiClient

        client = GeminiClient(
            model="gemini-2.0-flash-exp",
            api_key="test-key",
            max_retries=5,
            timeout=120,
        )

    assert client.model_name == "gemini-2.0-flash-exp"
    assert client.max_retries == 5
    assert client.timeout == 120
    assert client.use_vertex_ai is False
    # Verify genai module reference was stored on client
    assert hasattr(client, "genai")


# ============================================================
# Vertex AI Tests
# ============================================================


@pytest.fixture
def mock_settings_vertex():
    """Mock settings for Vertex AI mode."""
    with patch("app.clients.gemini.settings") as mock:
        mock.google_api_key = "test-api-key"
        mock.google_project_id = "test-project"
        mock.vertex_ai_location = "us-central1"
        mock.gemini_vertex_ai_location = "global"
        yield mock


@pytest.mark.parametrize(
    "model",
    [
        "gemini-3.1-pro-preview",
        "gemini-3.1-flash-lite",
        # The regression this parametrization exists for: these do not start with
        # "gemini-3.1-", and the old implementation sent them down the legacy Vertex SDK.
        "gemini-3.8-flash",
        "gemini-1.5-pro",
    ],
)
def test_vertex_always_uses_the_genai_sdk_regardless_of_model_name(mock_settings_vertex, model):
    """Which SDK runs must depend on the provider, never on how the model is named."""
    with patch("google.genai.Client") as mock_client:
        from app.clients.gemini import GeminiClient

        client = GeminiClient(model=model, use_vertex_ai=True)

    assert client.model_name == model
    assert client.use_vertex_ai is True
    mock_client.assert_called_once_with(vertexai=True, project="test-project", location="global")


def test_a_failed_vertex_init_raises_instead_of_downgrading_to_ai_studio(mock_settings_vertex):
    """A misconfigured project must not silently become a consumer API-key call.

    The old behaviour swallowed the failure and reconfigured onto AI Studio, which is a
    different quota, different data handling and a deprecated SDK — and is how production
    ended up there without anyone choosing it.
    """
    with patch("google.genai.Client", side_effect=RuntimeError("bad project")):
        from app.clients.gemini import GeminiClient

        with pytest.raises(RuntimeError, match="bad project"):
            GeminiClient(model="gemini-3.8-flash", use_vertex_ai=True)


@pytest.mark.asyncio
async def test_generate_genai_sdk_success(mock_settings_vertex):
    """Test generation via Gen AI SDK."""
    with patch("google.genai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "GenAI SDK response"

        async def mock_generate_content(*args, **kwargs):
            return mock_response

        mock_client.aio.models.generate_content = mock_generate_content
        mock_client_cls.return_value = mock_client

        from app.clients.gemini import GeminiClient

        client = GeminiClient(model="gemini-3.1-pro-preview", use_vertex_ai=True)

        result = await client.generate("Test prompt")
        assert result == "GenAI SDK response"
