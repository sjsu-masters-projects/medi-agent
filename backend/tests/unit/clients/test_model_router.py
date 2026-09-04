from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.clients.model_router import ModelRouter, TaskType, get_router
from app.models.generation import GenerationRequest


@pytest.fixture
def clean_router():
    with patch("app.clients.model_router._router", None):
        yield


@patch("app.clients.model_router.MedGemmaClient")
@patch("app.clients.model_router.GeminiClient")
def test_router_lazy_instantiation(mock_gemini, mock_medgemma):
    router = ModelRouter()

    # Clients shouldn't be instantiated until accessed
    mock_medgemma.assert_not_called()
    mock_gemini.assert_not_called()

    # Access medgemma
    client1 = router.medgemma_client
    mock_medgemma.assert_called_once()

    # Access again, should be cached
    client2 = router.medgemma_client
    assert mock_medgemma.call_count == 1
    assert client1 is client2

    # Access flash
    flash1 = router.flash_client
    assert mock_gemini.call_count == 1
    flash2 = router.flash_client
    assert mock_gemini.call_count == 1
    assert flash1 is flash2

    # Access pro
    pro1 = router.pro_client
    assert mock_gemini.call_count == 2
    pro2 = router.pro_client
    assert mock_gemini.call_count == 2
    assert pro1 is pro2


def test_get_router_singleton(clean_router):
    router1 = get_router()
    router2 = get_router()
    assert router1 is router2


@patch.object(ModelRouter, "medgemma_client")
@patch.object(ModelRouter, "flash_client")
@patch.object(ModelRouter, "pro_client")
def test_get_client_routing(mock_pro, mock_flash, mock_medgemma):
    router = ModelRouter()

    # medgemma
    assert router.get_client(TaskType.DOCUMENT_PARSING) == mock_medgemma
    assert router.get_client(TaskType.ADR_DETECTION) == mock_medgemma

    # flash
    assert router.get_client(TaskType.CHAT_RESPONSE) == mock_flash

    # pro
    assert router.get_client(TaskType.SOAP_NOTE) == mock_pro

    with pytest.raises(ValueError, match="Unknown task type"):
        router.get_client("invalid_task")  # type: ignore


def test_get_client_unknown_model_name():
    router = ModelRouter()
    with (
        patch.dict("app.clients.model_router.TASK_MODEL_MAP", {"fake_task": "unknown_model"}),
        pytest.raises(ValueError, match="Unknown model name: unknown_model"),
    ):
        router.get_client("fake_task")  # type: ignore


@patch.object(ModelRouter, "get_client")
@patch.object(ModelRouter, "flash_client")
def test_get_client_with_fallback(mock_flash, mock_get_client):
    router = ModelRouter()

    # Primary succeeds
    mock_get_client.return_value = "primary_client"
    assert router.get_client_with_fallback(TaskType.DOCUMENT_PARSING) == "primary_client"

    # Primary fails, fallback to flash
    mock_get_client.side_effect = Exception("Initialization failed")
    assert router.get_client_with_fallback(TaskType.DOCUMENT_PARSING) == mock_flash


@pytest.mark.asyncio
async def test_text_provider_wraps_existing_client_with_normalized_response():
    router = ModelRouter()
    client = MagicMock(model_name="medgemma-test")
    client.generate = AsyncMock(return_value="Extracted record")
    router.get_client = MagicMock(return_value=client)  # type: ignore[method-assign]

    response = await router.get_text_provider(TaskType.DOCUMENT_PARSING).generate(
        GenerationRequest(prompt="Extract")
    )

    assert response.text == "Extracted record"
    assert response.telemetry.provider == "medgemma"
    assert response.telemetry.model == "medgemma-test"


@pytest.mark.asyncio
async def test_generate_text_falls_back_to_flash_provider():
    router = ModelRouter()
    primary = MagicMock(model_name="medgemma-test")
    primary.generate = AsyncMock(side_effect=RuntimeError("primary unavailable"))
    flash = MagicMock(model_name="flash-test")
    flash.generate = AsyncMock(return_value="Fallback response")

    def get_client(task_type):
        return flash if task_type == TaskType.CHAT_RESPONSE else primary

    router.get_client = MagicMock(side_effect=get_client)  # type: ignore[method-assign]

    assert (
        await router.generate_text(TaskType.DOCUMENT_PARSING, prompt="Extract")
        == "Fallback response"
    )


def test_text_provider_falls_back_to_flash_when_primary_cannot_initialize():
    router = ModelRouter()
    flash = MagicMock(model_name="flash-test")

    def get_client(task_type):
        if task_type == TaskType.CHAT_RESPONSE:
            return flash
        raise RuntimeError("primary unavailable")

    router.get_client = MagicMock(side_effect=get_client)  # type: ignore[method-assign]

    provider = router.get_text_provider_with_fallback(TaskType.DOCUMENT_PARSING)

    assert provider.name == "flash"
