"""Read side of the model availability counters (AI-003). Clinic admins and operators only."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from supabase import Client

from app.core import authorization_reasons as reasons
from app.core.ai_availability import summarize
from app.core.db_pools import run_events_db
from app.core.exceptions import AuthorizationError, ExternalServiceError
from app.models.auth import CurrentUser
from app.models.enums import ClinicianRole
from app.services.clinic_membership_service import ClinicMembershipService

READ_TIMEOUT_SECONDS = 8
MAX_ROWS = 5000  # 14 days of buckets stay far below this; the cap makes the read bounded anyway


class AiAvailabilityService:
    def __init__(self, db: Client) -> None:
        self.db = db
        self.memberships = ClinicMembershipService(self)

    async def require_admin(self, user: CurrentUser) -> None:
        memberships = await self.memberships.active_memberships(user.id)
        if not any(m.role == ClinicianRole.ADMIN for m in memberships):
            raise AuthorizationError(
                "Only clinic admins can read AI availability",
                reason_code=reasons.ADMIN_SCOPE_ONLY,
                actor_id=str(user.id),
                actor_role="clinician",
            )

    async def window(self, hours: int) -> dict[str, Any]:
        since = datetime.now(UTC) - timedelta(hours=hours)
        query = (
            self.db.table("ai_availability_buckets")
            .select("workload,model,outcome,fallback,attempts,latency_sum_ms,latency_bins")
            .gte("bucket_start", since.isoformat())
            .order("bucket_start", desc=True)
            .limit(MAX_ROWS)
        )
        try:
            response = await asyncio.wait_for(
                run_events_db(query.execute), timeout=READ_TIMEOUT_SECONDS
            )
        except TimeoutError:
            raise ExternalServiceError("AI availability", "Counters are unavailable.") from None
        rows = [r for r in (response.data or []) if isinstance(r, dict)]
        return {
            "window_hours": hours,
            "truncated": len(rows) >= MAX_ROWS,
            "note": (
                "Counts and latency percentiles are approximate: latency is the upper edge of "
                "its histogram bin. No patient data or message text is stored."
            ),
            "items": summarize(rows),
        }
