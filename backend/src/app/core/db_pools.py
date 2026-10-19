"""Dedicated worker pools for blocking database calls.

``asyncio.to_thread`` shares one default pool of ``min(32, cpu + 4)`` threads (five on the
one-vCPU backend). A burst of slow notification reads used to occupy every thread, so a Nora
turn's own saves and reads queued behind them until the turn expired. Notification reads and
chat-turn control calls now run on separate, bounded pools, so neither can starve the other
or the default pool.
"""

import asyncio
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

from app.core.exceptions import PoolSaturatedError
from app.core.structured_logging import log_event

T = TypeVar("T")

NOTIFICATION_POOL_SIZE = 3
CHAT_TURN_POOL_SIZE = 4
# Running plus waiting calls allowed per pool. Beyond this the call is refused at once (HTTP
# 503 with Retry-After) instead of queueing without bound behind a slow dependency.
NOTIFICATION_MAX_PENDING = 12
CHAT_TURN_MAX_PENDING = 32

_notification_pool = ThreadPoolExecutor(
    max_workers=NOTIFICATION_POOL_SIZE, thread_name_prefix="notification-db"
)
_chat_turn_pool = ThreadPoolExecutor(
    max_workers=CHAT_TURN_POOL_SIZE, thread_name_prefix="chat-turn-db"
)


logger = logging.getLogger(__name__)
# Counters are touched only on the event loop thread (before submit and in the awaiting
# coroutine's finally), so they need no lock.
_pending = {"notification": 0, "chat_turn": 0}


async def _run(name: str, pool: ThreadPoolExecutor, limit: int, call: Callable[[], T]) -> T:
    if _pending[name] >= limit:
        log_event(
            logger,
            "pool.saturated",
            level=logging.WARNING,
            message=f"Worker pool {name} is saturated; request refused",
            outcome="shed",
            operation=name,
        )
        raise PoolSaturatedError(name)
    _pending[name] += 1
    try:
        return await asyncio.get_running_loop().run_in_executor(pool, call)
    finally:
        _pending[name] -= 1


async def run_notification_db(call: Callable[[], T]) -> T:
    return await _run("notification", _notification_pool, NOTIFICATION_MAX_PENDING, call)


async def run_chat_turn_db(call: Callable[[], T]) -> T:
    return await _run("chat_turn", _chat_turn_pool, CHAT_TURN_MAX_PENDING, call)
