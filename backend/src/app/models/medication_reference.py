"""Bounded public medication references, separate from clinical candidate evidence."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class MedicationReferenceSource(BaseModel):
    source: Literal["medlineplus", "dailymed"]
    locale: Literal["en-US", "es-MX"]
    title: str = Field(max_length=240)
    url: str = Field(max_length=2048)
    summary: str = Field(max_length=1200)
    source_version: str | None = Field(default=None, max_length=80)
    source_updated: date | None = None
    checked_at: datetime
    stale: bool


class MedicationReferenceRead(BaseModel):
    fact_id: UUID
    status: Literal["found", "not_found", "unavailable"]
    subject: str | None = Field(default=None, max_length=200)
    rxcui: str | None = Field(default=None, max_length=20)
    retrieved_at: datetime
    references: list[MedicationReferenceSource] = Field(default_factory=list, max_length=3)
