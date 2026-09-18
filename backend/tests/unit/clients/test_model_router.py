from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.clients.model_router import TASK_MODEL_MAP, ModelRouter, TaskType, get_router
from app.models.generation import GenerationRequest


@pytest.fixture
def clean_router():
    with patch("app.clients.model_router._router", None):
        yield


@patch("app.clients.model_router.GeminiClient")
def test_router_lazy_instantiation(mock_gemini):
    router = ModelRouter()

    # Clients shouldn't be instantiated until accessed
    mock_gemini.assert_not_called()

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


@patch.object(ModelRouter, "flash_client")
@patch.object(ModelRouter, "pro_client")
def test_get_client_routing(mock_pro, mock_flash):
    router = ModelRouter()

    # flash
    assert router.get_client(TaskType.DOCUMENT_PARSING) == mock_flash
    assert router.get_client(TaskType.ADR_DETECTION) == mock_flash
    assert router.get_client(TaskType.CHAT_RESPONSE) == mock_flash

    # pro
    assert router.get_client(TaskType.SOAP_NOTE) == mock_pro

    with pytest.raises(ValueError, match="Unknown task type"):
        router.get_client("invalid_task")  # type: ignore


def test_no_task_routes_to_a_model_the_router_cannot_build():
    """Every name in the map must be one `get_client` knows how to construct.

    A name with no branch raised only when that task was first exercised, which is how
    triage classification reached production routed to a client that always raised.
    """
    buildable = {"flash", "pro"}
    assert set(TASK_MODEL_MAP.values()) <= buildable


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
    assert router.get_client_with_fallback(TaskType.SOAP_NOTE) == "primary_client"

    # Primary fails, fallback to flash
    mock_get_client.side_effect = Exception("Initialization failed")
    assert router.get_client_with_fallback(TaskType.SOAP_NOTE) == mock_flash


@pytest.mark.asyncio
async def test_text_provider_wraps_existing_client_with_normalized_response():
    router = ModelRouter()
    client = MagicMock(model_name="flash-test")
    client.generate = AsyncMock(return_value="Extracted record")
    router.get_client = MagicMock(return_value=client)  # type: ignore[method-assign]

    response = await router.get_text_provider(TaskType.DOCUMENT_PARSING).generate(
        GenerationRequest(prompt="Extract")
    )

    assert response.text == "Extracted record"
    assert response.telemetry.provider == "flash"
    assert response.telemetry.model == "flash-test"


@pytest.mark.asyncio
async def test_generate_text_falls_back_to_flash_provider():
    router = ModelRouter()
    primary = MagicMock(model_name="pro-test")
    primary.generate = AsyncMock(side_effect=RuntimeError("primary unavailable"))
    flash = MagicMock(model_name="flash-test")
    flash.generate = AsyncMock(return_value="Fallback response")

    def get_client(task_type):
        return flash if task_type == TaskType.CHAT_RESPONSE else primary

    router.get_client = MagicMock(side_effect=get_client)  # type: ignore[method-assign]

    assert await router.generate_text(TaskType.SOAP_NOTE, prompt="Summarize") == "Fallback response"


@pytest.mark.asyncio
async def test_generate_text_with_telemetry_reports_which_model_answered():
    """A caller writing a durable record needs the model that actually answered.

    Document ingestion stores extraction candidates; without this, a candidate carries no
    note of which model produced it, so after a model swap there is no way to re-review
    or retire them selectively.
    """
    router = ModelRouter()
    client = MagicMock(model_name="gemini-3.8-flash")
    client.generate = AsyncMock(return_value="Extracted record")
    router.get_client = MagicMock(return_value=client)  # type: ignore[method-assign]

    text, telemetry = await router.generate_text_with_telemetry(
        TaskType.DOCUMENT_PARSING, prompt="Extract"
    )

    assert text == "Extracted record"
    assert telemetry.model == "gemini-3.8-flash"


@pytest.mark.asyncio
async def test_the_reported_model_is_the_one_that_answered_not_the_one_configured():
    """The router falls back, so the configured model is not necessarily the answer.

    Stamping provenance from configuration would therefore record a model that never ran.
    """
    router = ModelRouter()
    primary = MagicMock(model_name="pro-test")
    primary.generate = AsyncMock(side_effect=RuntimeError("primary unavailable"))
    flash = MagicMock(model_name="flash-that-actually-answered")
    flash.generate = AsyncMock(return_value="Fallback response")

    def get_client(task_type):
        return flash if task_type == TaskType.CHAT_RESPONSE else primary

    router.get_client = MagicMock(side_effect=get_client)  # type: ignore[method-assign]

    text, telemetry = await router.generate_text_with_telemetry(
        TaskType.SOAP_NOTE, prompt="Summarize"
    )

    assert text == "Fallback response"
    assert telemetry.model == "flash-that-actually-answered"


@pytest.mark.asyncio
async def test_generate_text_still_returns_only_text():
    """Its six callers want prose; adding telemetry must not change their contract."""
    router = ModelRouter()
    client = MagicMock(model_name="flash-test")
    client.generate = AsyncMock(return_value="Just prose")
    router.get_client = MagicMock(return_value=client)  # type: ignore[method-assign]

    assert await router.generate_text(TaskType.CHAT_RESPONSE, prompt="hi") == "Just prose"


def test_text_provider_falls_back_to_flash_when_primary_cannot_initialize():
    router = ModelRouter()
    flash = MagicMock(model_name="flash-test")

    def get_client(task_type):
        if task_type == TaskType.CHAT_RESPONSE:
            return flash
        raise RuntimeError("primary unavailable")

    router.get_client = MagicMock(side_effect=get_client)  # type: ignore[method-assign]

    provider = router.get_text_provider_with_fallback(TaskType.SOAP_NOTE)

    assert provider.name == "flash"
