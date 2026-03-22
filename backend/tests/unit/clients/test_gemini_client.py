"""Tests for GeminiClient."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from app.clients.gemini import GeminiClient
from app.core.exceptions import LLMError


class TestResponse(BaseModel):
    """Test response model."""

    message: str
    count: int


@pytest.fixture
def mock_genai():
    """Mock google.generativeai module."""
    with patch("app.clients.gemini.genai") as mock:
        yield mock


@pytest.fixture
def gemini_client(mock_genai):
    """Create GeminiClient with mocked genai."""
    return GeminiClient(model="gemini-2.0-flash-exp", api_key="test-key")


@pytest.mark.asyncio
async def test_generate_success(gemini_client, mock_genai):
    """Test successful text generation."""
    # Mock response
    mock_response = MagicMock()
    mock_response.text = "Generated text response"

    # Mock model
    mock_model = AsyncMock()
    mock_model.generate_content_async = AsyncMock(return_value=mock_response)
    gemini_client.model = mock_model

    result = await gemini_client.generate(prompt="Test prompt")

    assert result == "Generated text response"
    mock_model.generate_content_async.assert_called_once()


@pytest.mark.asyncio
async def test_generate_with_system_instruction(gemini_client, mock_genai):
    """Test generation with system instruction."""
    mock_response = MagicMock()
    mock_response.text = "Response with system instruction"

    # Mock the new model created with system instruction
    mock_new_model = AsyncMock()
    mock_new_model.generate_content_async = AsyncMock(return_value=mock_response)
    mock_genai.GenerativeModel.return_value = mock_new_model

    result = await gemini_client.generate(
        prompt="Test prompt",
        system_instruction="You are a helpful assistant",
    )

    assert result == "Response with system instruction"
    # Verify a new model was created with system instruction
    mock_genai.GenerativeModel.assert_called_with(
        "gemini-2.0-flash-exp",
        system_instruction="You are a helpful assistant",
    )


@pytest.mark.asyncio
async def test_generate_with_image(gemini_client):
    """Test generation with image."""
    mock_response = MagicMock()
    mock_response.text = "Image analysis response"

    mock_model = AsyncMock()
    mock_model.generate_content_async = AsyncMock(return_value=mock_response)
    gemini_client.model = mock_model

    image_bytes = b"fake_image_data"
    result = await gemini_client.generate(prompt="Describe this image", image=image_bytes)

    assert result == "Image analysis response"
    call_args = mock_model.generate_content_async.call_args
    parts = call_args.args[0]
    assert len(parts) == 2
    assert parts[0] == "Describe this image"
    assert parts[1]["mime_type"] == "image/jpeg"


@pytest.mark.asyncio
async def test_generate_empty_response(gemini_client):
    """Test handling of empty response."""
    mock_response = MagicMock()
    mock_response.text = ""

    mock_model = AsyncMock()
    mock_model.generate_content_async = AsyncMock(return_value=mock_response)
    gemini_client.model = mock_model

    with pytest.raises(LLMError, match="Empty response from Gemini"):
        await gemini_client.generate(prompt="Test prompt")


@pytest.mark.asyncio
async def test_generate_timeout(gemini_client):
    """Test timeout handling with retries."""
    mock_model = AsyncMock()
    mock_model.generate_content_async = AsyncMock(side_effect=TimeoutError())
    gemini_client.model = mock_model
    gemini_client.max_retries = 2

    with pytest.raises(LLMError, match="Gemini request timed out"):
        await gemini_client.generate(prompt="Test prompt")

    assert mock_model.generate_content_async.call_count == 2


@pytest.mark.asyncio
async def test_generate_retry_then_success(gemini_client):
    """Test retry logic with eventual success."""
    mock_response = MagicMock()
    mock_response.text = "Success after retry"

    mock_model = AsyncMock()
    # Fail once, then succeed
    mock_model.generate_content_async = AsyncMock(
        side_effect=[TimeoutError(), mock_response]
    )
    gemini_client.model = mock_model
    gemini_client.max_retries = 3

    result = await gemini_client.generate(prompt="Test prompt")

    assert result == "Success after retry"
    assert mock_model.generate_content_async.call_count == 2


@pytest.mark.asyncio
async def test_generate_exception(gemini_client):
    """Test handling of general exceptions."""
    mock_model = AsyncMock()
    mock_model.generate_content_async = AsyncMock(side_effect=ValueError("API error"))
    gemini_client.model = mock_model
    gemini_client.max_retries = 2

    with pytest.raises(LLMError, match="Gemini generation failed"):
        await gemini_client.generate(prompt="Test prompt")


@pytest.mark.asyncio
async def test_generate_structured_success(gemini_client):
    """Test structured output generation."""
    mock_response = MagicMock()
    mock_response.text = '{"message": "Hello", "count": 42}'

    mock_model = AsyncMock()
    mock_model.generate_content_async = AsyncMock(return_value=mock_response)
    gemini_client.model = mock_model

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

    mock_model = AsyncMock()
    mock_model.generate_content_async = AsyncMock(return_value=mock_response)
    gemini_client.model = mock_model

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

    mock_model = AsyncMock()
    mock_model.generate_content_async = AsyncMock(return_value=mock_response)
    gemini_client.model = mock_model

    with pytest.raises(LLMError, match="Failed to parse structured output"):
        await gemini_client.generate_structured(
            prompt="Generate structured data",
            response_model=TestResponse,
        )


@pytest.mark.asyncio
async def test_generate_stream(gemini_client):
    """Test streaming generation."""
    # Mock streaming response
    mock_chunk1 = MagicMock()
    mock_chunk1.text = "Hello "
    mock_chunk2 = MagicMock()
    mock_chunk2.text = "world"

    async def mock_stream():
        yield mock_chunk1
        yield mock_chunk2

    mock_model = AsyncMock()
    mock_model.generate_content_async = AsyncMock(return_value=mock_stream())
    gemini_client.model = mock_model

    chunks = []
    async for chunk in gemini_client.generate_stream(prompt="Test prompt"):
        chunks.append(chunk)

    assert chunks == ["Hello ", "world"]


@pytest.mark.asyncio
async def test_thinking_mode_requires_pro_model():
    """Test that thinking mode requires pro model."""
    client = GeminiClient(model="gemini-2.0-flash-exp")

    with pytest.raises(ValueError, match="Thinking mode requires"):
        await client.generate(prompt="Test", thinking_mode=True)


@pytest.mark.asyncio
async def test_thinking_mode_with_pro_model(mock_genai):
    """Test thinking mode with pro model."""
    client = GeminiClient(model="gemini-2.0-flash-thinking-exp-01-21")

    mock_response = MagicMock()
    mock_response.text = "Thinking response"

    mock_model = AsyncMock()
    mock_model.generate_content_async = AsyncMock(return_value=mock_response)
    client.model = mock_model

    result = await client.generate(prompt="Test", thinking_mode=True)

    assert result == "Thinking response"


def test_client_initialization(mock_genai):
    """Test client initialization."""
    client = GeminiClient(
        model="gemini-2.0-flash-exp",
        api_key="test-key",
        max_retries=5,
        timeout=120,
    )

    assert client.model_name == "gemini-2.0-flash-exp"
    assert client.max_retries == 5
    assert client.timeout == 120
    mock_genai.configure.assert_called_once_with(api_key="test-key")
