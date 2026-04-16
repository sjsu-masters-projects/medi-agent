"""Invite code response schemas for clinician patient onboarding flows."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel

InviteLifecycleState = Literal["active", "claimed", "inactive"]


class InvitePatientSummary(BaseModel):
    id: UUID
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None


class InviteCreatorSummary(BaseModel):
    id: UUID
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None


class InviteCodeRead(BaseModel):
    care_team_id: UUID
    invite_code: str | None = None
    status: str
    role: str | None = None
    created_at: str | None = None
    invite_expires_at: str | None = None
    invite_claimed_at: str | None = None
    is_expired: bool = False
    lifecycle_state: InviteLifecycleState
    patient: InvitePatientSummary | None = None
    created_by: InviteCreatorSummary | None = None


class InviteCounts(BaseModel):
    active: int = 0
    claimed: int = 0
    inactive: int = 0


class InviteCodeListResponse(BaseModel):
    invites: list[InviteCodeRead]
    counts: InviteCounts


class InviteCodeGenerateResponse(BaseModel):
    invite_code: str
    care_team_id: UUID


class CurrentInviteCodeResponse(BaseModel):
    invite_code: str | None = None
    care_team_id: UUID | None = None


class InviteCodeRevokeResponse(BaseModel):
    care_team_id: UUID
    invite_code: str | None = None
    status: str
