"""Dedicated worker pools for blocking database calls.

``asyncio.to_thread`` shares one default pool of ``min(32, cpu + 4)`` threads (five on the
one-vCPU backend). A burst of slow notification reads used to occupy every thread, so a Nora
turn's own saves and reads queued behind them until the turn expired. Notification reads and
chat-turn control calls now run on separate, bounded pools, so neither can starve the other
or the default pool.
"""

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

T = TypeVar("T")

NOTIFICATION_POOL_SIZE = 3
CHAT_TURN_POOL_SIZE = 4

_notification_pool = ThreadPoolExecutor(
    max_workers=NOTIFICATION_POOL_SIZE, thread_name_prefix="notification-db"
)
_chat_turn_pool = ThreadPoolExecutor(
    max_workers=CHAT_TURN_POOL_SIZE, thread_name_prefix="chat-turn-db"
)


async def run_notification_db(call: Callable[[], T]) -> T:
    return await asyncio.get_running_loop().run_in_executor(_notification_pool, call)


async def run_chat_turn_db(call: Callable[[], T]) -> T:
    return await asyncio.get_running_loop().run_in_executor(_chat_turn_pool, call)
