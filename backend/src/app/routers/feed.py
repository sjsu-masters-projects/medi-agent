"""Feed routes."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/today")
async def get_today_feed() -> dict:
    """Aggregated daily tasks — meds + obligations across all providers."""
    raise NotImplementedError
