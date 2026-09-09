"""Addressing a provider by model name rather than by task.

Task routing answers "what should run this", which binds each task to one model.
Evaluation needs the other question — "run this on that specific model" — and it must
not quietly answer with a different one.
"""

import pytest

from app.clients.model_router import ModelRouter


@pytest.fixture
def router(monkeypatch: pytest.MonkeyPatch) -> ModelRouter:
    """A router whose clients are stubs, so no model is constructed for real."""
    instance = ModelRouter()

    class _Client:
        def __init__(self, model_name: str) -> None:
            self.model_name = model_name

        async def generate(self, **_kwargs: object) -> str:
            return "stub"

    monkeypatch.setattr(type(instance), "medgemma_client", property(lambda _: _Client("medgemma-27b")))
    monkeypatch.setattr(type(instance), "flash_client", property(lambda _: _Client("flash-lite")))
    monkeypatch.setattr(type(instance), "pro_client", property(lambda _: _Client("pro")))
    return instance


@pytest.mark.parametrize(
    ("model_name", "expected_model"),
    [("medgemma", "medgemma-27b"), ("flash", "flash-lite"), ("pro", "pro")],
)
def test_each_model_name_resolves_to_its_own_provider(
    router: ModelRouter, model_name: str, expected_model: str
) -> None:
    provider = router.get_text_provider_for_model(model_name)

    assert provider.name == model_name
    assert provider.model == expected_model


def test_an_unknown_model_is_refused_rather_than_substituted(router: ModelRouter) -> None:
    """Falling back here would attribute one model's output to another."""
    with pytest.raises(ValueError):
        router.get_text_provider_for_model("mystery-model")


def test_the_provider_is_reused_across_calls(router: ModelRouter) -> None:
    first = router.get_text_provider_for_model("medgemma")
    second = router.get_text_provider_for_model("medgemma")

    assert first is second


def test_model_lookup_is_independent_of_task_routing(router: ModelRouter) -> None:
    """The point of the method: reach a model the task map would never select."""
    from app.clients.model_router import TASK_MODEL_MAP, TaskType

    assert TASK_MODEL_MAP[TaskType.DOCUMENT_PARSING] == "medgemma"

    provider = router.get_text_provider_for_model("pro")

    assert provider.name == "pro"
