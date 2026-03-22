"""Tests for MedGemmaClient with Hugging Face Inference API."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
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
    """Mock settings with HF token."""
    with patch("app.clients.medgemma.settings") as mock:
        mock.huggingface_api_token = "hf_test_token"
        mock.vertex_ai_medgemma_endpoint = ""
        mock.vertex_ai_endpoint_type = "auto"
        yield mock


@pytest.fixture
def mock_settings_no_token():
    """Mock settings without HF token (fallback mode)."""
    with patch("app.clients.medgemma.settings") as mock:
        mock.huggingface_api_token = ""
        mock.vertex_ai_medgemma_endpoint = ""
        mock.vertex_ai_endpoint_type = "auto"
        yield mock


@pytest.fixture
def mock_gemini_client():
    """Mock GeminiClient for fallback."""
    with patch("app.clients.medgemma.GeminiClient") as mock:
        yield mock


@pytest.fixture
def mock_httpx_client():
    """Mock httpx.AsyncClient."""
    with patch("app.clients.medgemma.httpx.AsyncClient") as mock:
        yield mock


@pytest.fixture
def medgemma_client_hf(mock_settings, mock_httpx_client):
    """Create MedGemmaClient with HF API enabled."""
    return MedGemmaClient(model="google/medgemma-4b-it")


@pytest.fixture
def medgemma_client_fallback(mock_settings_no_token, mock_gemini_client):
    """Create MedGemmaClient in fallback mode."""
    return MedGemmaClient(model="google/medgemma-4b-it")


# ============================================================
# Hugging Face API Tests
# ============================================================


@pytest.mark.asyncio
async def test_generate_hf_success(medgemma_client_hf, mock_httpx_client):
    """Test successful generation via HF API."""
    # Mock HTTP response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [{"generated_text": "This is a medical response"}]

    mock_client_instance = AsyncMock()
    mock_client_instance.post = AsyncMock(return_value=mock_response)
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=None)

    mock_httpx_client.return_value = mock_client_instance

    result = await medgemma_client_hf.generate(prompt="Explain this symptom")

    assert result == "This is a medical response"
    mock_client_instance.post.assert_called_once()


@pytest.mark.asyncio
async def test_generate_hf_with_system_instruction(medgemma_client_hf, mock_httpx_client):
    """Test generation with system instruction."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [{"generated_text": "Medical response"}]

    mock_client_instance = AsyncMock()
    mock_client_instance.post = AsyncMock(return_value=mock_response)
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=None)

    mock_httpx_client.return_value = mock_client_instance

    result = await medgemma_client_hf.generate(
        prompt="Diagnose",
        system_instruction="You are a medical expert",
        temperature=0.5,
        max_tokens=1024,
    )

    assert result == "Medical response"

    # Verify the request payload
    call_args = mock_client_instance.post.call_args
    payload = call_args.kwargs["json"]
    assert "You are a medical expert" in payload["inputs"]
    assert "Diagnose" in payload["inputs"]
    assert payload["parameters"]["temperature"] == 0.5
    assert payload["parameters"]["max_new_tokens"] == 1024


@pytest.mark.asyncio
async def test_generate_hf_model_loading(medgemma_client_hf, mock_httpx_client):
    """Test handling of model loading (503 with estimated_time)."""
    # First response: model loading
    mock_response_loading = MagicMock()
    mock_response_loading.status_code = 503
    mock_response_loading.json.return_value = {"estimated_time": 0.1}

    # Second response: success
    mock_response_success = MagicMock()
    mock_response_success.status_code = 200
    mock_response_success.json.return_value = [{"generated_text": "Success"}]

    mock_client_instance = AsyncMock()
    mock_client_instance.post = AsyncMock(
        side_effect=[mock_response_loading, mock_response_success]
    )
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=None)

    mock_httpx_client.return_value = mock_client_instance

    result = await medgemma_client_hf.generate(prompt="Test")

    assert result == "Success"
    assert mock_client_instance.post.call_count == 2


@pytest.mark.asyncio
async def test_generate_hf_timeout(medgemma_client_hf, mock_httpx_client):
    """Test timeout handling."""
    mock_client_instance = AsyncMock()
    mock_client_instance.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=None)

    mock_httpx_client.return_value = mock_client_instance

    with pytest.raises(LLMError, match="timed out"):
        await medgemma_client_hf.generate(prompt="Test")


@pytest.mark.asyncio
async def test_generate_hf_error_response(medgemma_client_hf, mock_httpx_client):
    """Test handling of error responses."""
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.text = "Bad request"

    mock_client_instance = AsyncMock()
    mock_client_instance.post = AsyncMock(return_value=mock_response)
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=None)

    mock_httpx_client.return_value = mock_client_instance

    with pytest.raises(LLMError, match="HF API error 400"):
        await medgemma_client_hf.generate(prompt="Test")


@pytest.mark.asyncio
async def test_generate_hf_empty_response(medgemma_client_hf, mock_httpx_client):
    """Test handling of empty response."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [{"generated_text": ""}]

    mock_client_instance = AsyncMock()
    mock_client_instance.post = AsyncMock(return_value=mock_response)
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=None)

    mock_httpx_client.return_value = mock_client_instance

    with pytest.raises(LLMError, match="Empty response"):
        await medgemma_client_hf.generate(prompt="Test")


@pytest.mark.asyncio
async def test_generate_structured_hf(medgemma_client_hf, mock_httpx_client):
    """Test structured generation via HF API."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {"generated_text": '{"diagnosis": "Flu", "confidence": 0.85}'}
    ]

    mock_client_instance = AsyncMock()
    mock_client_instance.post = AsyncMock(return_value=mock_response)
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=None)

    mock_httpx_client.return_value = mock_client_instance

    result = await medgemma_client_hf.generate_structured(
        prompt="Diagnose symptoms",
        response_model=TestResponse,
    )

    assert isinstance(result, TestResponse)
    assert result.diagnosis == "Flu"
    assert result.confidence == 0.85


@pytest.mark.asyncio
async def test_generate_stream_hf(medgemma_client_hf, mock_httpx_client):
    """Test streaming (falls back to non-streaming for HF API)."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [{"generated_text": "Complete response"}]

    mock_client_instance = AsyncMock()
    mock_client_instance.post = AsyncMock(return_value=mock_response)
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=None)

    mock_httpx_client.return_value = mock_client_instance

    chunks = []
    async for chunk in medgemma_client_hf.generate_stream(prompt="Test"):
        chunks.append(chunk)

    # HF API doesn't support streaming, so we get one chunk
    assert len(chunks) == 1
    assert chunks[0] == "Complete response"


# ============================================================
# Fallback Mode Tests
# ============================================================


@pytest.mark.asyncio
async def test_generate_fallback_to_gemini(medgemma_client_fallback, mock_gemini_client):
    """Test that MedGemma falls back to Gemini when no HF token."""
    mock_instance = mock_gemini_client.return_value
    mock_instance.generate = AsyncMock(return_value="Fallback response")

    result = await medgemma_client_fallback.generate(prompt="Test prompt")

    assert result == "Fallback response"
    mock_instance.generate.assert_called_once_with(
        prompt="Test prompt",
        system_instruction=None,
        image=None,
        temperature=0.7,
        max_tokens=2048,
    )


@pytest.mark.asyncio
async def test_generate_structured_fallback(medgemma_client_fallback, mock_gemini_client):
    """Test structured generation falls back to Gemini."""
    mock_instance = mock_gemini_client.return_value
    mock_response = TestResponse(diagnosis="Flu", confidence=0.85)
    mock_instance.generate_structured = AsyncMock(return_value=mock_response)

    result = await medgemma_client_fallback.generate_structured(
        prompt="Diagnose symptoms",
        response_model=TestResponse,
    )

    assert isinstance(result, TestResponse)
    assert result.diagnosis == "Flu"
    assert result.confidence == 0.85


@pytest.mark.asyncio
async def test_generate_stream_fallback(medgemma_client_fallback, mock_gemini_client):
    """Test streaming falls back to Gemini."""
    mock_instance = mock_gemini_client.return_value

    async def mock_stream():
        yield "Hello "
        yield "world"

    mock_instance.generate_stream.return_value = mock_stream()

    chunks = []
    async for chunk in medgemma_client_fallback.generate_stream(prompt="Test prompt"):
        chunks.append(chunk)

    assert chunks == ["Hello ", "world"]


# ============================================================
# Initialization Tests
# ============================================================


def test_client_initialization_with_token(mock_settings):
    """Test MedGemmaClient initialization with HF token."""
    client = MedGemmaClient(
        model="google/medgemma-4b-it",
        max_retries=5,
        timeout=120,
    )

    assert client.model_name == "google/medgemma-4b-it"
    assert client.max_retries == 5
    assert client.timeout == 120
    assert client.use_hf is True
    assert "google/medgemma-4b-it" in client.api_url


def test_client_initialization_without_token(mock_settings_no_token, mock_gemini_client):
    """Test MedGemmaClient initialization without HF token (fallback)."""
    client = MedGemmaClient(
        model="google/medgemma-4b-it",
        max_retries=5,
        timeout=120,
    )

    assert client.model_name == "google/medgemma-4b-it"
    assert client.max_retries == 5
    assert client.timeout == 120
    assert client.use_hf is False

    # Verify fallback client was created
    mock_gemini_client.assert_called_once_with(
        model="gemini-2.5-flash",
        max_retries=5,
        timeout=120,
    )


def test_interface_compatibility(medgemma_client_hf):
    """Test that MedGemmaClient has same interface as GeminiClient."""
    # Check that all methods exist
    assert hasattr(medgemma_client_hf, "generate")
    assert hasattr(medgemma_client_hf, "generate_structured")
    assert hasattr(medgemma_client_hf, "generate_stream")

    # Check that methods are callable
    assert callable(medgemma_client_hf.generate)
    assert callable(medgemma_client_hf.generate_structured)
    assert callable(medgemma_client_hf.generate_stream)


# ============================================================
# Prompt Echo Stripping Tests
# ============================================================


def test_strip_prompt_echo_output_pattern():
    """Test stripping of 'Output:' pattern from response."""
    client = MedGemmaClient(model="google/medgemma-27b-it")
    
    response = "Prompt:\nWhat is diabetes?\nOutput:\nDiabetes is a chronic condition..."
    cleaned = client._strip_prompt_echo(response, "What is diabetes?")
    
    assert cleaned == "Diabetes is a chronic condition..."
    assert "Prompt:" not in cleaned
    assert "Output:" not in cleaned


def test_strip_prompt_echo_prefix_match():
    """Test stripping when response starts with prompt text."""
    client = MedGemmaClient(model="google/medgemma-27b-it")
    
    prompt = "Explain hypertension"
    response = "Explain hypertension\n\nHypertension is high blood pressure..."
    cleaned = client._strip_prompt_echo(response, prompt)
    
    assert cleaned == "Hypertension is high blood pressure..."
    assert not cleaned.startswith(prompt)


def test_strip_prompt_echo_no_echo():
    """Test that clean responses pass through unchanged."""
    client = MedGemmaClient(model="google/medgemma-27b-it")
    
    prompt = "What is diabetes?"
    response = "Diabetes is a chronic metabolic disorder..."
    cleaned = client._strip_prompt_echo(response, prompt)
    
    assert cleaned == response


def test_strip_prompt_echo_partial_match():
    """Test handling of partial prompt matches."""
    client = MedGemmaClient(model="google/medgemma-27b-it")
    
    prompt = "Explain the symptoms of flu"
    response = "Explain the symptoms\n\nFlu symptoms include fever, cough..."
    cleaned = client._strip_prompt_echo(response, prompt)
    
    # Should strip the partial match
    assert "Flu symptoms include" in cleaned


def test_strip_prompt_echo_empty_response():
    """Test handling of empty response after stripping."""
    client = MedGemmaClient(model="google/medgemma-27b-it")
    
    prompt = "Test prompt"
    response = "Prompt:\nTest prompt\nOutput:\n"
    cleaned = client._strip_prompt_echo(response, prompt)
    
    # Should return empty string, not None
    assert cleaned == ""


# ============================================================
# Gemma Chat Template Tests
# ============================================================


def test_gemma_chat_template_format():
    """Test Gemma chat template formatting."""
    client = MedGemmaClient(model="google/medgemma-27b-it")
    
    prompt = "What is diabetes?"
    system_instruction = "You are a medical expert."
    
    formatted = client._format_gemma_chat_template(prompt, system_instruction)
    
    # Check for Gemma chat template markers
    assert "<start_of_turn>user" in formatted
    assert "<end_of_turn>" in formatted
    assert "<start_of_turn>model" in formatted
    assert system_instruction in formatted
    assert prompt in formatted


def test_gemma_chat_template_no_system():
    """Test Gemma chat template without system instruction."""
    client = MedGemmaClient(model="google/medgemma-27b-it")
    
    prompt = "Explain hypertension"
    formatted = client._format_gemma_chat_template(prompt, None)
    
    assert "<start_of_turn>user" in formatted
    assert "<end_of_turn>" in formatted
    assert "<start_of_turn>model" in formatted
    assert prompt in formatted


def test_gemma_chat_template_multiline_prompt():
    """Test Gemma chat template with multiline prompt."""
    client = MedGemmaClient(model="google/medgemma-27b-it")
    
    prompt = """Patient: 62yo started Atorvastatin 80mg 3 weeks ago.
Now reports: muscle pain, weakness, dark urine.

Is this an adverse drug reaction?"""
    
    formatted = client._format_gemma_chat_template(prompt, None)
    
    assert "<start_of_turn>user" in formatted
    assert all(line in formatted for line in prompt.split("\n"))


# ============================================================
# Vertex AI vLLM Endpoint Tests
# ============================================================


@pytest.mark.asyncio
async def test_generate_vllm_format_chat_completions():
    """Test generation using vLLM /chat/completions endpoint."""
    with patch("app.clients.medgemma.settings") as mock_settings:
        mock_settings.vertex_ai_medgemma_endpoint = "projects/123/locations/us-central1/endpoints/456"
        mock_settings.vertex_ai_endpoint_type = "vllm"
        mock_settings.huggingface_api_token = ""
        mock_settings.google_project_id = "test-project"
        mock_settings.vertex_ai_location = "us-central1"
        
        with patch("app.clients.medgemma.httpx.AsyncClient") as mock_httpx:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "This is a medical response"}}]
            }
            
            mock_client_instance = AsyncMock()
            mock_client_instance.post = AsyncMock(return_value=mock_response)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            
            mock_httpx.return_value = mock_client_instance
            
            client = MedGemmaClient(model="google/medgemma-27b-it")
            result = await client.generate(prompt="Explain diabetes")
            
            assert result == "This is a medical response"
            
            # Verify OpenAI-compatible format was used (no Gemma template in messages)
            call_args = mock_client_instance.post.call_args
            payload = call_args.kwargs["json"]
            assert "messages" in payload
            assert payload["messages"][0]["role"] == "user"
            # Chat completions uses standard OpenAI format, not Gemma template
            assert "<start_of_turn>" not in payload["messages"][0]["content"]


@pytest.mark.asyncio
async def test_generate_vllm_format_fallback_to_predict():
    """Test fallback from /chat/completions to /predict on 404."""
    with patch("app.clients.medgemma.settings") as mock_settings:
        mock_settings.vertex_ai_medgemma_endpoint = "projects/123/locations/us-central1/endpoints/456"
        mock_settings.vertex_ai_endpoint_type = "vllm"
        mock_settings.huggingface_api_token = ""
        mock_settings.google_project_id = "test-project"
        mock_settings.vertex_ai_location = "us-central1"
        
        with patch("app.clients.medgemma.httpx.AsyncClient") as mock_httpx:
            # First call returns 404 (chat/completions not found)
            mock_response_404 = MagicMock()
            mock_response_404.status_code = 404
            
            # Second call succeeds with /predict
            mock_response_success = MagicMock()
            mock_response_success.status_code = 200
            mock_response_success.json.return_value = {
                "predictions": ["Success response"]
            }
            
            mock_client_instance = AsyncMock()
            mock_client_instance.post = AsyncMock(
                side_effect=[mock_response_404, mock_response_success]
            )
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            
            mock_httpx.return_value = mock_client_instance
            
            client = MedGemmaClient(model="google/medgemma-27b-it")
            result = await client.generate(prompt="Test")
            
            assert result == "Success response"
            assert mock_client_instance.post.call_count == 2
            
            # Verify second call (predict fallback) used Gemma chat template
            second_call_args = mock_client_instance.post.call_args_list[1]
            payload = second_call_args.kwargs["json"]
            assert "prompt" in payload
            assert "<start_of_turn>" in payload["prompt"]
            assert "<end_of_turn>" in payload["prompt"]
