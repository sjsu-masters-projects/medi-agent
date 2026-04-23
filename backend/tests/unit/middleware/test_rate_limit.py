from unittest.mock import patch

import pytest

from app.middleware.rate_limit import SlidingWindowRateLimiter


@pytest.mark.asyncio
async def test_sliding_window_rate_limiter_blocks_after_limit():
    limiter = SlidingWindowRateLimiter(limit=2, window_seconds=60)

    first = await limiter.check("clinician-1")
    second = await limiter.check("clinician-1")
    third = await limiter.check("clinician-1")

    assert first.allowed is True
    assert second.allowed is True
    assert third.allowed is False
    assert third.retry_after_seconds > 0


@pytest.mark.asyncio
async def test_sliding_window_rate_limiter_resets_after_window():
    limiter = SlidingWindowRateLimiter(limit=1, window_seconds=10)

    with patch("app.middleware.rate_limit.time.monotonic", side_effect=[100.0, 111.5]):
        first = await limiter.check("clinician-2")
        second = await limiter.check("clinician-2")

    assert first.allowed is True
    assert second.allowed is True
