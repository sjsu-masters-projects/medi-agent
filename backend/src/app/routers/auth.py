"""Auth routes."""

from fastapi import APIRouter

router = APIRouter()


@router.post("/signup")
async def signup() -> dict:
    # TODO: Accept email, trigger Supabase magic link
    return {"message": "signup endpoint"}


@router.post("/login")
async def login() -> dict:
    # TODO: Accept email+password, return Supabase session
    return {"message": "login endpoint"}


@router.post("/refresh")
async def refresh_token() -> dict:
    # TODO: Accept refresh_token, return new access_token
    return {"message": "refresh endpoint"}
