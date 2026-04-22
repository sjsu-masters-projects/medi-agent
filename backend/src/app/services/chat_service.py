"""Chat message storage and history."""

from __future__ import annotations

import asyncio
from typing import Any

from supabase import Client

from app.core.exceptions import ExternalServiceError
from app.models.enums import ChatRole, Language, coerce_locale

DEFAULT_CHAT_SESSION_ID = "default"


class ConversationStateConflictError(Exception):
    """Raised when a conversation state update loses an optimistic-lock race."""


class ChatService:
    """Persist and retrieve patient chat messages."""

    def __init__(self, db: Client) -> None:
        self.db = db

    async def save_message(self, patient_id: str, data: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "patient_id": patient_id,
            "content": str(data.get("content", "")).strip(),
            "role": self._coerce_role(data.get("role")),
            "language": self._coerce_language(data.get("language")),
            "audio_url": data.get("audio_url"),
            "intent": data.get("intent"),
        }

        result = await self._execute(self.db.table("chat_messages").insert(payload))
        rows = [row for row in (result.data or []) if isinstance(row, dict)]
        if not rows:
            raise ExternalServiceError("Supabase", "Failed to save chat message")

        return rows[0]

    async def get_history(
        self,
        patient_id: str,
        limit: int = 50,
        before: str | None = None,
    ) -> list[dict[str, Any]]:
        query = (
            self.db.table("chat_messages")
            .select("id, patient_id, content, role, intent, language, audio_url, created_at")
            .eq("patient_id", patient_id)
            .order("created_at")
            .limit(limit)
        )
        if before:
            query = query.lt("created_at", before)

        result = await self._execute(query)
        return [row for row in (result.data or []) if isinstance(row, dict)]

    async def get_context(
        self,
        patient_id: str,
        document_id: str | None = None,
    ) -> dict[str, Any]:
        medications = await self._fetch_active_medications(patient_id)
        conditions = await self._fetch_active_conditions(patient_id)
        recent_symptoms = await self._fetch_recent_symptoms(patient_id)

        document_context = None
        if document_id:
            document_context = await self._fetch_document_context(patient_id, document_id)

        return {
            "medications": medications,
            "conditions": conditions,
            "recent_symptoms": recent_symptoms,
            "document": document_context,
        }

    async def get_or_create_conversation_state(
        self,
        patient_id: str,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        session_id = self._normalize_session_id(options.get("session_id"))
        query = (
            self.db.table("chat_conversation_states")
            .select("*")
            .eq("patient_id", patient_id)
            .eq("session_id", session_id)
            .limit(1)
        )
        result = await self._execute(query)
        rows = [row for row in (result.data or []) if isinstance(row, dict)]
        if rows:
            return rows[0]

        payload: dict[str, Any] = {
            "patient_id": patient_id,
            "session_id": session_id,
            "language": self._coerce_language(options.get("language")),
            "status": "active",
            "turn_count": int(options.get("turn_count") or 0),
            "last_intent": str(options.get("last_intent") or "general"),
            "last_urgency": str(options.get("last_urgency") or "routine"),
            "last_route": str(options.get("last_route") or "triage"),
            "summary": str(options.get("summary") or ""),
            "state_json": options.get("state_json") or {},
            "document_context": options.get("document_context"),
        }
        insert_result = await self._execute(
            self.db.table("chat_conversation_states").insert(payload)
        )
        inserted_rows = [row for row in (insert_result.data or []) if isinstance(row, dict)]
        if not inserted_rows:
            raise ExternalServiceError("Supabase", "Failed to initialize conversation state")

        return inserted_rows[0]

    async def update_conversation_state(
        self,
        patient_id: str,
        updates: dict[str, Any],
        *,
        expected_updated_at: str | None = None,
    ) -> dict[str, Any]:
        session_id = self._normalize_session_id(updates.get("session_id"))
        payload: dict[str, Any] = {
            "language": self._coerce_language(updates.get("language")),
            "turn_count": int(updates.get("turn_count") or 0),
            "last_intent": str(updates.get("last_intent") or "general"),
            "last_urgency": str(updates.get("last_urgency") or "routine"),
            "last_route": str(updates.get("last_route") or "triage"),
            "summary": str(updates.get("summary") or ""),
            "state_json": updates.get("state_json") or {},
            "document_context": updates.get("document_context"),
            "status": str(updates.get("status") or "active"),
        }

        update_query = (
            self.db.table("chat_conversation_states")
            .update(payload)
            .eq("patient_id", patient_id)
            .eq("session_id", session_id)
        )
        if expected_updated_at:
            update_query = update_query.eq("updated_at", expected_updated_at)

        update_result = await self._execute(update_query)
        updated_rows = [row for row in (update_result.data or []) if isinstance(row, dict)]
        if updated_rows:
            return updated_rows[0]

        if expected_updated_at:
            existing = await self._execute(
                self.db.table("chat_conversation_states")
                .select("id")
                .eq("patient_id", patient_id)
                .eq("session_id", session_id)
                .limit(1)
            )
            existing_rows = [row for row in (existing.data or []) if isinstance(row, dict)]
            if existing_rows:
                raise ConversationStateConflictError("Conversation state changed concurrently")

        return await self.get_or_create_conversation_state(
            patient_id,
            {
                "session_id": session_id,
                **payload,
            },
        )

    async def save_symptom_report(
        self,
        patient_id: str,
        report: dict[str, Any],
    ) -> dict[str, Any] | None:
        symptom = str(report.get("symptom", "")).strip()
        severity_raw = report.get("severity")
        try:
            severity = int(severity_raw) if severity_raw is not None else 0
        except (TypeError, ValueError):
            return None
        if not symptom or severity < 1 or severity > 10:
            return None

        payload: dict[str, Any] = {
            "patient_id": patient_id,
            "symptom": symptom,
            "severity": severity,
            "onset": report.get("onset"),
            "duration": report.get("duration"),
            "related_medication_id": report.get("related_medication_id"),
            "related_medication_name": report.get("related_medication_name"),
            "body_area": report.get("body_area"),
            "ai_assessment": report.get("ai_assessment"),
            "flagged_for_adr": bool(report.get("flagged_for_adr", False)),
            "notes": report.get("notes"),
        }

        result = await self._execute(self.db.table("symptom_reports").insert(payload))
        rows = [row for row in (result.data or []) if isinstance(row, dict)]
        return rows[0] if rows else None

    async def notify_assigned_clinicians(
        self,
        patient_id: str,
        payload: dict[str, Any],
    ) -> int:
        assignments = await self._execute(
            self.db.table("care_teams")
            .select("clinician_id")
            .eq("patient_id", patient_id)
            .eq("status", "active")
        )
        clinician_ids = {
            str(row.get("clinician_id"))
            for row in (assignments.data or [])
            if isinstance(row, dict) and row.get("clinician_id")
        }
        if not clinician_ids:
            return 0

        urgency = str(payload.get("urgency", "urgent"))
        intent = str(payload.get("intent", "general"))
        excerpt = str(payload.get("message_excerpt", "")).strip()[:280]
        body = (
            f"Chat escalation flagged ({urgency}/{intent}) for patient {patient_id}. "
            f"Latest message: {excerpt or 'n/a'}"
        )
        rows = [
            {
                "clinician_id": clinician_id,
                "patient_id": patient_id,
                "channel": "in_app",
                "subject": "Urgent patient chat escalation",
                "body": body,
            }
            for clinician_id in clinician_ids
        ]
        await self._execute(self.db.table("clinician_messages").insert(rows))
        return len(rows)

    async def _fetch_active_medications(self, patient_id: str) -> list[dict[str, Any]]:
        result = await self._execute(
            self.db.table("medications")
            .select("id, name, dosage, frequency, route")
            .eq("patient_id", patient_id)
            .eq("is_active", True)
            .order("created_at", desc=True)
            .limit(8)
        )
        return [row for row in (result.data or []) if isinstance(row, dict)]

    async def _fetch_active_conditions(self, patient_id: str) -> list[dict[str, Any]]:
        result = await self._execute(
            self.db.table("conditions")
            .select("id, name, status, notes")
            .eq("patient_id", patient_id)
            .eq("status", "active")
            .limit(8)
        )
        return [row for row in (result.data or []) if isinstance(row, dict)]

    async def _fetch_recent_symptoms(self, patient_id: str) -> list[dict[str, Any]]:
        result = await self._execute(
            self.db.table("symptom_reports")
            .select("id, symptom, severity, onset, duration, created_at")
            .eq("patient_id", patient_id)
            .order("created_at", desc=True)
            .limit(6)
        )
        return [row for row in (result.data or []) if isinstance(row, dict)]

    async def _fetch_document_context(
        self,
        patient_id: str,
        document_id: str,
    ) -> dict[str, Any] | None:
        result = await self._execute(
            self.db.table("documents")
            .select("id, file_name, document_type, ai_summary, notes, parse_status")
            .eq("id", document_id)
            .eq("patient_id", patient_id)
            .limit(1)
        )
        rows = [row for row in (result.data or []) if isinstance(row, dict)]
        if not rows:
            return None

        row = rows[0]
        return {
            "id": row.get("id"),
            "file_name": row.get("file_name"),
            "document_type": row.get("document_type"),
            "summary": row.get("ai_summary") or row.get("notes") or "",
            "parse_status": row.get("parse_status") or "none",
        }

    async def _execute(self, query: Any) -> Any:
        return await asyncio.to_thread(query.execute)

    @staticmethod
    def _normalize_session_id(value: Any) -> str:
        raw = str(value or DEFAULT_CHAT_SESSION_ID).strip()
        return raw or DEFAULT_CHAT_SESSION_ID

    @staticmethod
    def _coerce_role(value: Any) -> str:
        if isinstance(value, ChatRole):
            return value.value
        raw = str(value or ChatRole.USER.value)
        return raw if raw in {member.value for member in ChatRole} else ChatRole.USER.value

    @staticmethod
    def _coerce_language(value: Any) -> str:
        return coerce_locale(value).value
