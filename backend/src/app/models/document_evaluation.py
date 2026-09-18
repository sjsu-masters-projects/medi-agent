"""Provider-neutral, offline document-extraction evaluation contracts."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DocumentExtractionEvaluation(BaseModel):
    """One deterministic score for a recorded synthetic extraction output."""

    schema_valid: bool
    candidate_precision: float = Field(ge=0, le=1)
    candidate_recall: float = Field(ge=0, le=1)
    evidence_valid_rate: float = Field(ge=0, le=1)
    abstained: bool
    latency_ms: int | None = Field(default=None, ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    errors: list[str] = Field(default_factory=list)
