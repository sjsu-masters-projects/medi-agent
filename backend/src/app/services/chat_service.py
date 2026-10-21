"""Chat message storage and history."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from postgrest.exceptions import APIError
from supabase import Client

from app.core.exceptions import ExternalServiceError
from app.models.enums import ChatRole, Language, coerce_locale
from app.services.explanation_service import normalize_patient_summary

logger = logging.getLogger(__name__)

DEFAULT_CHAT_SESSION_ID = "default"
MAX_ATTACHMENTS = 3
MAX_CARD_RESULTS = 60
_HISTORY_COLUMNS = (
    "id, patient_id, session_id, content, role, intent, language, audio_url, created_at"
)
_MISSING_COLUMN_CODES = {"PGRST204", "42703"}


def _missing_attachments_column(error: APIError) -> bool:
    code = str(getattr(error, "code", "") or "")
    return code in _MISSING_COLUMN_CODES and "attachments" in str(getattr(error, "message", error))


# Conversation ids are chosen by the patient app ("day-2026-10-10", "chat-<random>"), so
# they are validated rather than trusted; anything else falls back to the default.
_SESSION_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
TITLE_CHARS = 80
_TURN_SCAN_LIMIT = 500


def _is_past(value: Any, now: datetime) -> bool:
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return False
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment <= now


def normalize_session_id(value: Any) -> str:
    raw = str(value or "").strip()
    return raw if _SESSION_ID.fullmatch(raw) else DEFAULT_CHAT_SESSION_ID


def conversation_title(first_message: str) -> str:
    """A list label from the patient's first message: one line, word-boundary cut."""
    text = " ".join(str(first_message or "").split())
    if len(text) <= TITLE_CHARS:
        return text
    return text[:TITLE_CHARS].rsplit(" ", 1)[0].rstrip(",.;:") + "…"


def is_internal_chat_alert(message: dict[str, Any]) -> bool:
    """Recognize reserved operational notices, including existing stored alerts.

    Keep clinician-authored messages intact; a generic urgent subject alone is not
    enough to identify an automated notice. Do not delete the underlying alert.
    """
    return message.get("subject") == "Urgent patient chat escalation" and str(
        message.get("body") or ""
    ).startswith("Chat escalation flagged (")


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
            "session_id": normalize_session_id(data.get("session_id")),
        }

        attachments = [item for item in data.get("attachments") or [] if isinstance(item, dict)]
        if attachments:
            payload["attachments"] = attachments[:MAX_ATTACHMENTS]
        try:
            result = await self._execute(self.db.table("chat_messages").insert(payload))
        except APIError as exc:
            if "attachments" not in payload or not _missing_attachments_column(exc):
                raise
            # The backend can deploy before migration 062; the reply is saved as text.
            payload.pop("attachments")
            result = await self._execute(self.db.table("chat_messages").insert(payload))
        rows = [row for row in (result.data or []) if isinstance(row, dict)]
        if not rows:
            raise ExternalServiceError("Supabase", "Failed to save chat message")

        return rows[0]

    def result_attachments(self, patient_id: str, document_ids: list[str]) -> list[dict[str, Any]]:
        """Results cards for the documents a reply cited, from this patient's own facts.

        The values are the source-checked rows Records shows, never parsed from the reply.
        Any failure leaves the reply without a card rather than failing the turn.
        """
        from app.services.document_service import DocumentService

        documents = DocumentService(self.db)
        cards: list[dict[str, Any]] = []
        for document_id in list(dict.fromkeys(document_ids))[:MAX_ATTACHMENTS]:
            try:
                key = UUID(str(document_id))
                results = documents.list_document_results(key, UUID(patient_id))
                if not results:
                    continue
                row = documents._get_document_row(key, UUID(patient_id))
            except Exception as exc:  # noqa: BLE001 - a card is optional; the reply is not
                logger.warning("Results card skipped for a cited document: %s", type(exc).__name__)
                continue
            raw_titles = row.get("display_title")
            titles: dict[str, Any] = raw_titles if isinstance(raw_titles, dict) else {}
            cards.append(
                {
                    "type": "document_results",
                    "document_id": str(key),
                    "file_name": str(row.get("file_name") or ""),
                    "title": {
                        locale: str(titles[locale])
                        for locale in ("en-US", "es-MX")
                        if titles.get(locale)
                    },
                    "results": results[:MAX_CARD_RESULTS],
                }
            )
        return cards

    async def get_history(
        self,
        patient_id: str,
        limit: int = 50,
        before: str | None = None,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """The newest ``limit`` messages, oldest first, optionally for one conversation."""
        query = (
            self.db.table("chat_messages")
            .select(_HISTORY_COLUMNS + ", attachments")
            .eq("patient_id", patient_id)
            # Newest first, then reversed: ascending with a limit returned the oldest
            # messages, so a long conversation never showed its latest turns.
            .order("created_at", desc=True)
            .limit(limit)
        )
        if session_id is not None:
            query = query.eq("session_id", normalize_session_id(session_id))
        if before:
            query = query.lt("created_at", before)

        try:
            result = await self._execute(query)
        except APIError as exc:
            if not _missing_attachments_column(exc):
                raise
            # Before migration 062 there are no attachments to read.
            return await self._history_without_attachments(
                patient_id, limit=limit, before=before, session_id=session_id
            )
        rows = [row for row in (result.data or []) if isinstance(row, dict)]
        return list(reversed(rows))

    async def _history_without_attachments(
        self, patient_id: str, *, limit: int, before: str | None, session_id: str | None
    ) -> list[dict[str, Any]]:
        query = (
            self.db.table("chat_messages")
            .select(_HISTORY_COLUMNS)
            .eq("patient_id", patient_id)
            .order("created_at", desc=True)
            .limit(limit)
        )
        if session_id is not None:
            query = query.eq("session_id", normalize_session_id(session_id))
        if before:
            query = query.lt("created_at", before)
        result = await self._execute(query)
        rows = [row for row in (result.data or []) if isinstance(row, dict)]
        return list(reversed(rows))

    async def list_conversations(self, patient_id: str, limit: int = 30) -> list[dict[str, Any]]:
        """This patient's conversations, most recent first, for the conversation list.

        Merges completed-conversation state with sessions that only have saved turns
        (processing, failed, interrupted), so an unfinished reply stays reachable from
        another tab or device.
        """
        states = await self._execute(
            self.db.table("chat_conversation_states")
            .select("session_id, title, turn_count, language, created_at, updated_at")
            .eq("patient_id", patient_id)
            .gt("turn_count", 0)
            .order("updated_at", desc=True)
            .limit(limit)
        )
        merged: dict[str, dict[str, Any]] = {
            str(row["session_id"]): {**row, "status": None}
            for row in (states.data or [])
            if isinstance(row, dict) and row.get("session_id")
        }
        turn_result = await self._execute(
            self.db.table("chat_turns")
            .select(
                "session_id, status, deadline_at, dismissed_at, user_message_id, "
                "created_at, updated_at"
            )
            .eq("patient_id", patient_id)
            .order("created_at", desc=True)
            .limit(_TURN_SCAN_LIMIT)
        )
        by_session: dict[str, list[dict[str, Any]]] = {}
        for turn in turn_result.data or []:
            if isinstance(turn, dict) and turn.get("session_id"):
                by_session.setdefault(str(turn["session_id"]), []).append(turn)  # newest first
        first_message: dict[str, str] = {}
        for session_id, turns in by_session.items():
            if session_id not in merged or not str(merged[session_id].get("title") or ""):
                first_message[session_id] = str(turns[-1].get("user_message_id") or "")
        texts: dict[str, str] = {}
        ids = [value for value in first_message.values() if value]
        if ids:
            message_result = await self._execute(
                self.db.table("chat_messages")
                .select("id, content")
                .eq("patient_id", patient_id)
                .in_("id", ids)
            )
            texts = {
                str(row["id"]): str(row.get("content") or "")
                for row in (message_result.data or [])
                if isinstance(row, dict) and row.get("id")
            }
        now = datetime.now(UTC)
        for session_id, turns in by_session.items():
            latest = turns[0]
            row = merged.get(session_id)
            if row is None:
                row = merged[session_id] = {
                    "session_id": session_id,
                    "title": "",
                    "turn_count": 0,
                    "language": Language.EN.value,
                    "created_at": turns[-1].get("created_at"),
                    "updated_at": latest.get("updated_at") or latest.get("created_at"),
                    "status": None,
                }
            if not str(row.get("title") or ""):
                row["title"] = conversation_title(texts.get(first_message.get(session_id, ""), ""))
            activity = max(str(row.get("updated_at") or ""), str(latest.get("updated_at") or ""))
            row["updated_at"] = activity
            status = str(latest.get("status") or "")
            if status in {"queued", "processing", "failed", "interrupted"} and not latest.get(
                "dismissed_at"
            ):
                row["status"] = "needs_attention"
                expired = _is_past(latest.get("deadline_at"), now)
                row["reply_in_progress"] = status in {"queued", "processing"} and not expired
        for row in merged.values():
            row.setdefault("reply_in_progress", False)
        ordered = sorted(
            merged.values(), key=lambda r: str(r.get("updated_at") or ""), reverse=True
        )
        return ordered[:limit]

    async def set_conversation_title(self, patient_id: str, session_id: str, title: str) -> None:
        """Label a conversation once, from its first message; an existing title stays."""
        if not title:
            return
        await self._execute(
            self.db.table("chat_conversation_states")
            .update({"title": title[:120]})
            .eq("patient_id", patient_id)
            .eq("session_id", normalize_session_id(session_id))
            .eq("title", "")
        )

    async def get_recent_clinician_messages(
        self,
        patient_id: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        result = await self._execute(
            self.db.table("clinician_messages")
            .select("id, clinician_id, patient_id, channel, subject, body, is_read, created_at")
            .eq("patient_id", patient_id)
            .order("created_at", desc=True)
            .limit(limit)
        )
        rows = [row for row in (result.data or []) if isinstance(row, dict)]
        # These rows include clinician inbox alerts, not only clinician replies.
        return list(reversed([row for row in rows if not is_internal_chat_alert(row)]))

    async def get_context(
        self,
        patient_id: str,
        document_id: str | None = None,
    ) -> dict[str, Any]:
        medications = await self._fetch_active_medications(patient_id)
        conditions = await self._fetch_active_conditions(patient_id)
        recent_symptoms_available = True
        try:
            recent_symptoms = await self._fetch_recent_symptoms(patient_id)
        except APIError as exc:
            # During migration-first rollout, never substitute legacy reports
            # when the confirmation boundary cannot be queried.
            if exc.code != "42703" or "confirmation_state" not in (exc.message or ""):
                raise
            recent_symptoms = []
            recent_symptoms_available = False
            logger.warning(
                "Confirmed symptom context unavailable: confirmation schema not installed"
            )
        care_teams = await self._fetch_active_care_teams(patient_id)

        document_context = None
        if document_id:
            document_context = await self._fetch_document_context(patient_id, document_id)

        return {
            "medications": medications,
            "conditions": conditions,
            "recent_symptoms": recent_symptoms,
            "recent_symptoms_available": recent_symptoms_available,
            "care_teams": care_teams,
            "document": document_context,
        }

    async def get_document_catalog(self, patient_id: str, limit: int = 8) -> list[dict[str, Any]]:
        """Return safe portal document metadata for an already-authorized chat patient."""
        result = await self._execute(
            self.db.table("documents")
            .select("id, file_name, document_type, display_title, created_at")
            .eq("patient_id", patient_id)
            .order("created_at", desc=True)
            .limit(limit)
        )
        return [row for row in (result.data or []) if isinstance(row, dict)]

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
            "status": str(updates.get("status") or "active"),
        }
        # The document a conversation is focused on changes only when it is attached,
        # dismissed or found unavailable (see `set_document_context`). Writing it on every
        # turn let a turn resurrect a document the patient had already dismissed.
        if "document_context" in updates:
            payload["document_context"] = updates.get("document_context")

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

    async def set_document_context(
        self,
        patient_id: str,
        session_id: str,
        document_context: dict[str, Any] | None,
    ) -> None:
        """Attach a document to one conversation, or clear it with ``None``.

        Scoped to the patient's own conversation row; the document itself must already
        have been read through `get_document_context` for the same patient.
        """
        await self._execute(
            self.db.table("chat_conversation_states")
            .update({"document_context": document_context})
            .eq("patient_id", patient_id)
            .eq("session_id", normalize_session_id(session_id))
        )

    async def get_document_context(
        self,
        patient_id: str,
        document_id: str,
    ) -> dict[str, Any] | None:
        """The patient's own document as chat context, or None if it is not available."""
        return await self._fetch_document_context(patient_id, document_id)

    async def save_symptom_report(
        self,
        patient_id: str,
        report: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Retired: every new report requires an owned, explicit confirmation RPC."""
        raise ExternalServiceError("Symptom intake", "Explicit patient confirmation required")

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
        body = f"Chat escalation flagged ({urgency}/{intent}). Latest message: {excerpt or 'n/a'}"
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
            .select("id, name, generic_name, rxcui, dosage, frequency, route")
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
            .eq("confirmation_state", "patient_confirmed")
            .eq("patient_id", patient_id)
            .order("created_at", desc=True)
            .limit(6)
        )
        return [row for row in (result.data or []) if isinstance(row, dict)]

    async def _fetch_active_care_teams(self, patient_id: str) -> list[dict[str, Any]]:
        result = await self._execute(
            self.db.table("care_teams")
            .select(
                "id, clinician_id, role, specialty_context, clinic_id, "
                "clinics(display_name), clinicians(first_name, last_name)"
            )
            .eq("patient_id", patient_id)
            .eq("status", "active")
            .limit(5)
        )
        teams = [row for row in (result.data or []) if isinstance(row, dict)]
        for team in teams:
            # The clinic of each link, so Nora can tell a patient's clinics apart (CLN-003).
            clinic = team.pop("clinics", None)
            team["clinic_name"] = clinic.get("display_name") if isinstance(clinic, dict) else None
        return teams

    async def _fetch_document_context(
        self,
        patient_id: str,
        document_id: str,
    ) -> dict[str, Any] | None:
        # The id arrives from the connection URL or a saved conversation; a malformed one
        # names no document rather than failing the whole connection in the database.
        try:
            document_id = str(UUID(str(document_id)))
        except ValueError:
            return None
        result = await self._execute(
            self.db.table("documents")
            .select("id, file_name, display_title, document_type, ai_summary, notes, parse_status")
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
            # The LOC-001 record titles, so an answer can cite the document as Records names it.
            "display_title": row.get("display_title") or {},
            "document_type": row.get("document_type"),
            "summary": normalize_patient_summary(
                str(row.get("ai_summary") or row.get("notes") or "")
            ),
            "parse_status": row.get("parse_status") or "none",
        }

    async def _execute(self, query: Any) -> Any:
        return await asyncio.to_thread(query.execute)

    @staticmethod
    def _normalize_session_id(value: Any) -> str:
        return normalize_session_id(value)

    @staticmethod
    def _coerce_role(value: Any) -> str:
        if isinstance(value, ChatRole):
            return value.value
        raw = str(value or ChatRole.USER.value)
        return raw if raw in {member.value for member in ChatRole} else ChatRole.USER.value

    @staticmethod
    def _coerce_language(value: Any) -> str:
        return coerce_locale(value).value
