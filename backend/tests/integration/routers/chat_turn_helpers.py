"""Run a server-owned turn to completion inside a test."""

from typing import Any

from app.routers import chat
from app.services.chat_turn_runner import TurnRun


async def run_turn(
    socket: Any, service: Any, context: dict[str, Any], request: dict[str, Any]
) -> Any:
    started = await chat._process_durable_message(socket, service, context, request)
    if isinstance(started, TurnRun):
        assert started.task is not None
        await started.task
        return started.result
    return started
