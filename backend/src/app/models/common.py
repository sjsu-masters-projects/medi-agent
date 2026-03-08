"""Shared schemas — error envelopes, pagination."""

from typing import Any

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str = Field(..., examples=["NOT_FOUND"])
    message: str = Field(..., examples=["Patient not found"])


class ErrorResponse(BaseModel):
    """All errors follow this shape: `{ error: { code, message } }`."""

    error: ErrorDetail


class SuccessResponse(BaseModel):
    message: str = "Success"


class PaginatedResponse(BaseModel):
    """Cursor-based — use `next_cursor` for the next page, not offset."""

    data: list[Any] = Field(default_factory=list)
    next_cursor: str | None = None
    has_more: bool = False
    total_count: int | None = None


class TimestampMixin(BaseModel):
    """Mixin for read schemas — ISO-8601 strings from Supabase."""

    created_at: str
    updated_at: str | None = None
