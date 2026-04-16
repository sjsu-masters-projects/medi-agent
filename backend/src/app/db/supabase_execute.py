"""Shared Supabase execution helpers for retryable backend reads."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any, Protocol

import httpx
from supabase import Client

from app.clients.supabase import refresh_client
from app.core.exceptions import ExternalServiceError

logger = logging.getLogger(__name__)


class HasSupabaseClient(Protocol):
    db: Client


def is_transient_supabase_error(exc: Exception) -> bool:
    """Classify transport-level failures that are safe to retry for reads."""
    if isinstance(exc, httpx.HTTPError):
        return True

    detail = str(exc).lower()
    transient_markers = (
        "resource temporarily unavailable",
        "connection reset",
        "timed out",
        "temporarily unavailable",
        "readerror",
        "server disconnected",
        "connection aborted",
        "network is unreachable",
    )
    return any(marker in detail for marker in transient_markers)


def execute_sync(
    owner: HasSupabaseClient,
    build_query: Callable[[Client], Any],
    *,
    operation: str,
    retry_transient: bool = False,
    max_attempts: int = 2,
) -> Any:
    """Execute a sync Supabase query with transient-failure handling."""
    attempts = max_attempts if retry_transient else 1
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            return build_query(owner.db).execute()
        except Exception as exc:
            if not is_transient_supabase_error(exc):
                raise

            last_error = exc
            if attempt < attempts:
                logger.warning(
                    "Transient Supabase error during %s (attempt %s/%s): %s",
                    operation,
                    attempt,
                    attempts,
                    exc,
                )
                owner.db = refresh_client(owner.db)
                time.sleep(0.2 * attempt)
                continue

            raise ExternalServiceError("Supabase", f"{operation} is temporarily unavailable") from exc

    raise ExternalServiceError("Supabase", f"{operation} is temporarily unavailable") from last_error


async def execute_async(
    owner: HasSupabaseClient,
    build_query: Callable[[Client], Any],
    *,
    operation: str,
    retry_transient: bool = False,
    max_attempts: int = 2,
) -> Any:
    """Execute an async Supabase query with transient-failure handling."""
    attempts = max_attempts if retry_transient else 1
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            query = build_query(owner.db)
            return await asyncio.to_thread(query.execute)
        except Exception as exc:
            if not is_transient_supabase_error(exc):
                raise

            last_error = exc
            if attempt < attempts:
                logger.warning(
                    "Transient Supabase error during %s (attempt %s/%s): %s",
                    operation,
                    attempt,
                    attempts,
                    exc,
                )
                owner.db = refresh_client(owner.db)
                await asyncio.sleep(0.2 * attempt)
                continue

            raise ExternalServiceError("Supabase", f"{operation} is temporarily unavailable") from exc

    raise ExternalServiceError("Supabase", f"{operation} is temporarily unavailable") from last_error
