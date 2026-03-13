"""Feed routes."""

from typing import Any

from fastapi import APIRouter

router = APIRouter()


@router.get("/today")
async def get_today_feed() -> Any:
    """Aggregated daily tasks — meds + obligations across all providers."""
    raise NotImplementedError
