"""Tests for strict MedGemmaClient with Vertex AI."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from app.clients.medgemma import MedGemmaClient
from app.core.exceptions import LLMError


class TestResponse(BaseModel):
    """Test response model."""

    diagnosis: str
    confidence: float


@pytest.fixture
def mock_settings():
    """Mock settings with Vertex AI configuration."""
    with patch("app.clients.medgemma.settings") as mock:
        mock.vertex_ai_medgemma_endpoint = "projects/123/locations/us-central1/endpoints/456"
        mock.vertex_ai_endpoint_type = "auto"
        mock.google_project_id = "test-project"
        mock.vertex_ai_location = "us-central1"
        yield mock


@pytest.fixture
def mock_httpx_client():
    """Mock httpx.AsyncClient."""
    with patch("app.clients.medgemma.httpx.AsyncClient") as mock:
        yield mock


@pytest.fixture
def mock_google_auth():
    """Mock Google auth for Vertex requests."""
    with patch("google.auth.default") as mock_auth:
        creds = MagicMock()
        creds.token = "test-token"
        mock_auth.return_value = (creds, "test-project")
        yield mock_auth


@pytest.fixture
def mock_aiplatform():
    """Mock Google aiplatform."""
    with (
        patch("google.cloud.aiplatform.init") as mock_init,
        patch("google.cloud.aiplatform.Endpoint") as mock_endpoint,
    ):
        yield mock_init, mock_endpoint


@pytest.fixture
def medgemma_client(mock_settings, mock_aiplatform):
    """Create MedGemmaClient for Vertex AI testing."""
    return MedGemmaClient(model="google/medgemma-27b-it")


# ============================================================
# Initialization Tests
# ============================================================


def test_client_initialization_success(mock_settings, mock_aiplatform):
    """Test successful initialization with Vertex AI."""
    mock_init, mock_endpoint = mock_aiplatform
    client = MedGemmaClient()

    assert client.model_name == "google/medgemma-27b-it"
    mock_init.assert_called_once_with(project="test-project", location="us-central1")
    mock_endpoint.assert_called_once_with("projects/123/locations/us-central1/endpoints/456")


def test_client_initialization_missing_endpoint():
    """Test initialization fails without endpoint."""
    with patch("app.clients.medgemma.settings") as mock_settings:
        mock_settings.vertex_ai_medgemma_endpoint = ""
        with pytest.raises(ValueError, match="VERTEX_AI_MEDGEMMA_ENDPOINT must be set"):
            MedGemmaClient()


def test_client_initialization_aiplatform_failure(mock_settings):
    """Test initialization fails when aiplatform fails."""
    with (
        patch("google.cloud.aiplatform.init", side_effect=Exception("Auth error")),
        pytest.raises(RuntimeError, match="Failed to initialize Vertex AI"),
    ):
        MedGemmaClient()


# ============================================================
# Prompt Echo Stripping Tests
# ============================================================


def test_strip_prompt_echo_output_pattern():
    """Test stripping of 'Output:' pattern from response."""
    response = "Prompt:\nWhat is diabetes?\nOutput:\nDiabetes is a chronic condition..."
    cleaned = MedGemmaClient._strip_prompt_echo(response, "What is diabetes?")

    assert cleaned == "Diabetes is a chronic condition..."
    assert "Prompt:" not in cleaned
    assert "Output:" not in cleaned


def test_strip_prompt_echo_prefix_match():
    """Test stripping when response starts with prompt text."""
    prompt = "Explain hypertension"
    response = "Explain hypertension\n\nHypertension is high blood pressure..."
    cleaned = MedGemmaClient._strip_prompt_echo(response, prompt)

    assert cleaned == "Hypertension is high blood pressure..."
    assert not cleaned.startswith(prompt)


def test_strip_prompt_echo_no_echo():
    """Test that clean responses pass through unchanged."""
    prompt = "What is diabetes?"
    response = "Diabetes is a chronic metabolic disorder..."
    cleaned = MedGemmaClient._strip_prompt_echo(response, prompt)

    assert cleaned == response


# ============================================================
# Gemma Chat Template Tests
# ============================================================


def test_gemma_chat_template_format():
    """Test Gemma chat template formatting."""
    prompt = "What is diabetes?"
    system_instruction = "You are a medical expert."

    formatted = MedGemmaClient._format_gemma_chat_template(prompt, system_instruction)

    assert "<start_of_turn>user" in formatted
    assert "<end_of_turn>" in formatted
    assert "<start_of_turn>model" in formatted
    assert system_instruction in formatted
    assert prompt in formatted


def test_gemma_chat_template_no_system():
    """Test Gemma chat template without system instruction."""
    prompt = "Explain hypertension"
    formatted = MedGemmaClient._format_gemma_chat_template(prompt, None)

    assert "<start_of_turn>user" in formatted
    assert "<start_of_turn>model" in formatted
    assert prompt in formatted


# ============================================================
# Vertex AI Request Building Tests
# ============================================================


def test_build_chat_request(medgemma_client):
    """Test building vLLM chat request."""
    request = medgemma_client._build_chat_request(
        prompt="Test", system_instruction="System", temperature=0.5, max_tokens=100
    )

    assert request["model"] == "google/medgemma-27b-it"
    assert request["temperature"] == 0.5
    assert request["max_tokens"] == 100
    assert len(request["messages"]) == 2
    assert request["messages"][0]["content"] == "System"
    assert request["messages"][1]["content"] == "Test"


def test_build_endpoint_urls(medgemma_client):
    """Test building endpoint URLs."""
    chat, predict = medgemma_client._build_endpoint_urls()

    assert chat == "https://456.us-central1-123.prediction.vertexai.goog/v1/chat/completions"
    assert (
        predict
        == "https://456.us-central1-123.prediction.vertexai.goog/v1/projects/123/locations/us-central1/endpoints/456:predict"
    )


@pytest.mark.asyncio
async def test_get_auth_headers(medgemma_client, mock_google_auth):
    """Test fetching auth headers."""
    headers = await medgemma_client._get_auth_headers()
    assert headers["Authorization"] == "Bearer test-token"
    assert headers["Content-Type"] == "application/json"


# ============================================================
# Vertex AI vLLM Generation Tests
# ============================================================


@pytest.mark.asyncio
async def test_generate_vllm_success(medgemma_client, mock_httpx_client, mock_google_auth):
    """Test successful VLLM generation via API."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "This is a medical response"}}]
    }

    mock_client_instance = AsyncMock()
    mock_client_instance.post = AsyncMock(return_value=mock_response)
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=None)

    mock_httpx_client.return_value = mock_client_instance

    result = await medgemma_client.generate(prompt="Explain diabetes")

    assert result == "This is a medical response"
    mock_client_instance.post.assert_called_once()
    assert "chat/completions" in mock_client_instance.post.call_args[0][0]


@pytest.mark.asyncio
async def test_generate_vllm_fallback_to_predict(
    medgemma_client, mock_httpx_client, mock_google_auth
):
    """Test fallback from /chat/completions to /predict on 404."""
    mock_response_404 = MagicMock()
    mock_response_404.status_code = 404

    mock_response_success = MagicMock()
    mock_response_success.status_code = 200
    mock_response_success.json.return_value = {"predictions": [{"content": "Success response"}]}

    mock_client_instance = AsyncMock()
    mock_client_instance.post = AsyncMock(side_effect=[mock_response_404, mock_response_success])
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=None)

    mock_httpx_client.return_value = mock_client_instance

    result = await medgemma_client.generate(prompt="Test fallback")

    assert result == "Success response"
    assert mock_client_instance.post.call_count == 2
    # Verify second call was to predict
    assert ":predict" in mock_client_instance.post.call_args_list[1][0][0]


@pytest.mark.asyncio
async def test_generate_vllm_error_status(medgemma_client, mock_httpx_client, mock_google_auth):
    """Test handling of 500 error from vLLM."""
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"

    mock_client_instance = AsyncMock()
    mock_client_instance.post = AsyncMock(return_value=mock_response)
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=None)

    mock_httpx_client.return_value = mock_client_instance

    # Should retry and then throw LLMError
    with (
        patch("asyncio.sleep"),
        pytest.raises(
            LLMError, match="Vertex AI MedGemma generation failed: vLLM endpoint error 500"
        ),
    ):
        await medgemma_client.generate(prompt="Test failure")


@pytest.mark.asyncio
async def test_parse_vllm_responses(medgemma_client):
    """Test parsing various shapes of vLLM responses."""

    # 1. Normal choices
    payload1 = {"choices": [{"message": {"content": "Text1"}}]}
    assert medgemma_client._parse_vllm_response(payload1, "prompt") == "Text1"

    # 2. Text direct
    payload2 = {"text": "Text2"}
    assert medgemma_client._parse_vllm_response(payload2, "prompt") == "Text2"

    # 3. Predictions dict
    payload3 = {"predictions": [{"content": "Text3"}]}
    assert medgemma_client._parse_vllm_response(payload3, "prompt") == "Text3"

    # 4. Empty text
    with pytest.raises(LLMError, match="Empty response from Vertex"):
        medgemma_client._parse_vllm_response({"text": ""}, "prompt")

    # 5. Unknown structure
    with pytest.raises(LLMError, match="Unexpected vLLM response format"):
        medgemma_client._parse_vllm_response({"choices": [{}]}, "prompt")


# ============================================================
# Standard Generation Tests (Fallback)
# ============================================================


@pytest.mark.asyncio
async def test_generate_standard_format_success(mock_settings, mock_aiplatform):
    """Test generating via standard Vertex AI predict."""
    mock_init, mock_endpoint = mock_aiplatform

    # Configure endpoint behavior
    mock_endpoint_instance = MagicMock()
    mock_response = MagicMock()
    mock_response.predictions = ["Standard Output"]
    mock_endpoint_instance.predict.return_value = mock_response
    mock_endpoint.return_value = mock_endpoint_instance

    with patch("app.clients.medgemma.settings.vertex_ai_endpoint_type", "standard"):
        client = MedGemmaClient()
        result = await client.generate(
            prompt="Test Standard",
            system_instruction="System",
            image=b"data",  # this gets ignored
        )

        assert result == "Standard Output"
        mock_endpoint_instance.predict.assert_called_once()
        args = mock_endpoint_instance.predict.call_args.kwargs
        assert args["instances"][0]["prompt"] == "System\n\nTest Standard"


@pytest.mark.asyncio
async def test_generate_standard_format_empty_prediction(mock_settings, mock_aiplatform):
    """Test standard fallback when prediction is empty."""
    mock_init, mock_endpoint = mock_aiplatform

    mock_endpoint_instance = MagicMock()
    mock_response = MagicMock()
    mock_response.predictions = []
    mock_endpoint_instance.predict.return_value = mock_response
    mock_endpoint.return_value = mock_endpoint_instance

    with (
        patch("app.clients.medgemma.settings.vertex_ai_endpoint_type", "standard"),
        patch("asyncio.sleep"),
    ):
        client = MedGemmaClient()
        with pytest.raises(LLMError, match="No predictions in Vertex AI response"):
            await client.generate("Test failure")


# ============================================================
# Extra Generation Tests
# ============================================================


@pytest.mark.asyncio
async def test_generate_structured(medgemma_client, mock_httpx_client, mock_google_auth):
    """Test generating structured pydantic models."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {"message": {"content": '```json\n{"diagnosis": "Flu", "confidence": 0.95}\n```'}}
        ]
    }

    mock_client_instance = AsyncMock()
    mock_client_instance.post = AsyncMock(return_value=mock_response)
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=None)
    mock_httpx_client.return_value = mock_client_instance

    result = await medgemma_client.generate_structured(
        prompt="Diagnose", response_model=TestResponse
    )

    assert result.diagnosis == "Flu"
    assert result.confidence == 0.95


@pytest.mark.asyncio
async def test_generate_stream(medgemma_client, mock_httpx_client, mock_google_auth):
    """Test that streaming properly cascades to non-streaming generate."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": [{"message": {"content": "Chunk1"}}]}

    mock_client_instance = AsyncMock()
    mock_client_instance.post = AsyncMock(return_value=mock_response)
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=None)
    mock_httpx_client.return_value = mock_client_instance

    chunks = []
    async for chunk in medgemma_client.generate_stream(prompt="Stream this"):
        chunks.append(chunk)

    assert len(chunks) == 1
    assert chunks[0] == "Chunk1"
