"""Observability utilities for agents."""

import logging
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


@asynccontextmanager
async def trace_agent_execution(
    agent_name: str, input_data: dict[str, Any]
) -> AsyncGenerator[str, None]:
    """Context manager for tracing agent execution.

    Usage:
        async with trace_agent_execution("ingestion", {"doc_id": doc_id}) as trace_id:
            result = await agent.process(input)
    """
    trace_id = str(uuid4())
    start_time = time.time()

    logger.info(
        f"Agent {agent_name} started",
        extra={
            "trace_id": trace_id,
            "agent": agent_name,
            "input": input_data,
        },
    )

    try:
        yield trace_id
        duration = time.time() - start_time
        logger.info(
            f"Agent {agent_name} completed",
            extra={
                "trace_id": trace_id,
                "agent": agent_name,
                "duration_ms": int(duration * 1000),
                "status": "success",
            },
        )
    except Exception as e:
        duration = time.time() - start_time
        logger.error(
            f"Agent {agent_name} failed",
            extra={
                "trace_id": trace_id,
                "agent": agent_name,
                "duration_ms": int(duration * 1000),
                "status": "error",
                "error": str(e),
            },
            exc_info=True,
        )
        raise
