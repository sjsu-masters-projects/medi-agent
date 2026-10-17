"""Role-scoped notifications, delegated to atomic authorized database operations."""

import asyncio
from typing import Any, cast
from uuid import UUID

from postgrest.exceptions import APIError
from pydantic import ValidationError as ModelValidationError
from supabase import Client

from app.core.exceptions import AuthorizationError, ExternalServiceError, ValidationError
from app.models.auth import CurrentUser
from app.models.notification_centre import CentrePage, CentreReadThroughResult, CentreSummary
from app.services.notification_centre_presentation import present_item
from app.services.notification_centre_tokens import issue_token, read_token


class NotificationCentreService:
    def __init__(self, db: Client, actor: CurrentUser) -> None:
        self.db, self.actor = db, actor

    async def page(self, options: dict[str, Any]) -> CentrePage:
        payload = {"limit": options.get("limit", 50), "unread": options.get("unread", False)}
        self._add_clinic_filter(payload, options)
        if options.get("cursor"):
            payload["before"] = read_token(self.actor, "cursor", options["cursor"])
        result = cast(dict[str, Any], await self._call("list", payload))
        rows = result.get("items", [])
        ids = result.get("read_ids", [])
        next_cursor = result.get("next_cursor")
        return CentrePage(
            items=[
                present_item(row, self.actor.role, options.get("locale", "en-US")) for row in rows
            ],
            next_cursor=issue_token(self.actor, "cursor", next_cursor) if next_cursor else None,
            read_through=issue_token(self.actor, "read", ids) if ids else None,
        )

    async def summary(self) -> CentreSummary:
        return CentreSummary.model_validate(await self._call("summary"))

    async def action_items(self, options: dict[str, Any]) -> CentrePage:
        self._clinician_only()
        payload = {"category": options.get("category"), "limit": options.get("limit", 50)}
        self._add_clinic_filter(payload, options)
        if options.get("cursor"):
            payload["before"] = read_token(self.actor, "action_cursor", options["cursor"])
        result = cast(dict[str, Any], await self._call("action_items", payload))
        cursor = result.get("next_cursor")
        return CentrePage(
            items=[present_item(row, "clinician", "en-US") for row in result.get("items", [])],
            next_cursor=issue_token(self.actor, "action_cursor", cursor) if cursor else None,
        )

    async def mark_read(self, item_id: UUID) -> Any:
        return await self._call("read", {"id": str(item_id)})

    async def read_through(self, token: str) -> CentreReadThroughResult:
        """Marks what the caller may still see in the signed view; the rest is skipped."""
        ids = read_token(self.actor, "read", token)
        if not isinstance(ids, list) or len(ids) > 1000:
            raise ValidationError("Invalid notification view")
        result = await self._call("read_through", {"ids": ids})
        try:
            return CentreReadThroughResult.model_validate(result)
        except ModelValidationError:
            raise ExternalServiceError(
                "Supabase", "Notifications unavailable. Refresh to try again."
            ) from None

    async def acknowledge(self, item_id: UUID, note: str | None) -> Any:
        self._clinician_only()
        return await self._call("acknowledge", {"id": str(item_id), "note": note})

    def _add_clinic_filter(self, payload: dict[str, Any], options: dict[str, Any]) -> None:
        """A clinician's clinic filter; the database answers empty for a clinic they lack."""
        if self.actor.role == "clinician" and options.get("clinic_id"):
            payload["clinic_id"] = str(options["clinic_id"])

    def _clinician_only(self) -> None:
        if self.actor.role != "clinician":
            raise self._denial()

    async def _call(self, action: str, payload: dict[str, Any] | None = None) -> Any:
        if self.actor.role not in {"patient", "clinician"}:
            raise self._denial()
        try:
            result = await asyncio.to_thread(
                self.db.rpc(
                    "notification_centre_operation",
                    {
                        "p_actor_id": str(self.actor.id),
                        "p_actor_role": self.actor.role,
                        "p_action": action,
                        "p_payload": payload or {},
                    },
                ).execute
            )
        except APIError as exc:
            if exc.code in {"42501", "P0002"}:
                raise self._denial() from None
            if exc.code == "22023":
                raise ValidationError("Invalid notification request") from None
            raise ExternalServiceError(
                "Supabase", "Notifications unavailable. Refresh to try again."
            ) from None
        if not isinstance(result.data, dict):
            raise ExternalServiceError(
                "Supabase", "Notifications unavailable. Refresh to try again."
            )
        return result.data

    def _denial(self) -> AuthorizationError:
        return AuthorizationError(
            "Notification unavailable",
            actor_id=str(self.actor.id),
            actor_role=self.actor.role,
            target_type="notification",
        )
