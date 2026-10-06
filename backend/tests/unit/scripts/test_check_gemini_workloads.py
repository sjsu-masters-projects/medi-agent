"""Workload checks must use bounded config and exclude private reasoning."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from scripts import check_gemini_workloads as probe

from app.adk.registry import Workload, route_for


def args(tmp_path: Path, **overrides: object) -> argparse.Namespace:
    return argparse.Namespace(
        **{
            "workload": ["triage_classification"],
            "case": ["tri-001"],
            "model": None,
            "thinking": None,
            "fallback": False,
            "dry_run": False,
            "out": tmp_path / "report.json",
            **overrides,
        }
    )


@pytest.mark.asyncio
async def test_dry_run_never_constructs_a_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = MagicMock()
    monkeypatch.setattr(probe.genai, "Client", client)
    assert await probe.run(args(tmp_path, dry_run=True)) == 0
    client.assert_not_called()


@pytest.mark.asyncio
async def test_chat_mode_refuses_ignored_model_overrides(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="registry settings"):
        await probe.run(args(tmp_path, chat=True, model="unreviewed-model", dry_run=True))


@pytest.mark.asyncio
@pytest.mark.parametrize("finish", ["FinishReason.STOP", "FinishReason.MAX_TOKENS"])
async def test_route_settings_final_answers_and_truncation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, finish: str
) -> None:
    response = SimpleNamespace(
        candidates=[
            SimpleNamespace(
                finish_reason=finish,
                content=SimpleNamespace(
                    parts=[
                        SimpleNamespace(text="private-test-sentinel", thought=True),
                        SimpleNamespace(
                            text='{"intent":"symptom","urgency":"emergency","reason":"danger signs"}',
                            thought=False,
                        ),
                    ]
                ),
            )
        ]
    )
    generate = AsyncMock(return_value=response)
    client = MagicMock()
    client.aio.models.generate_content = generate
    client.aio.aclose = AsyncMock()
    constructor = MagicMock(return_value=client)
    monkeypatch.setattr(probe.genai, "Client", constructor)
    monkeypatch.setattr(probe.asyncio, "sleep", AsyncMock())
    options = args(tmp_path)
    assert await probe.run(options) == (1 if finish.endswith("MAX_TOKENS") else 0)
    route = route_for(Workload.TRIAGE)
    sent = generate.call_args.kwargs
    assert sent["model"] == route.primary.model_id
    assert sent["config"].max_output_tokens == route.max_output_tokens
    assert sent["config"].thinking_config.thinking_level.value == route.thinking_level
    assert sent["config"].temperature is None
    assert constructor.call_args.kwargs["location"] == "global"
    assert constructor.call_args.kwargs["http_options"].retry_options.attempts == 1
    report = options.out.read_text()
    assert "private-test-sentinel" not in report
    assert json.loads(report)[0]["deadline_seconds"] == route.budget_seconds
    client.aio.aclose.assert_awaited_once()
