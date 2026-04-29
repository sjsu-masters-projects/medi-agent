"""A2A task lifecycle persistence for cross-agent delegation."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import httpx
from supabase import Client

from app.core.exceptions import ExternalServiceError, ValidationError


class A2ATaskService:
    """Store and update A2A task lifecycle states."""

    DEFAULT_MAX_RETRIES = 3
    MAX_JSON_PAYLOAD_BYTES = 256_000
    EXECUTE_MAX_ATTEMPTS = 3

    def __init__(self, db: Client) -> None:
        self.db = db

    async def submit_task(self, patient_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        symptom_event_id = self._coerce_symptom_event_id(payload.get("symptom_event_id"))
        idempotency_key = self._build_idempotency_key(
            payload=payload,
            symptom_event_id=symptom_event_id,
        )

        existing = await self._get_task_by_idempotency_key(
            patient_id=patient_id,
            idempotency_key=idempotency_key,
        )
        if existing:
            return existing

        row = {
            "patient_id": patient_id,
            "conversation_session_id": str(payload.get("session_id") or "default"),
            "source_agent": str(payload.get("source_agent") or "triage"),
            "target_agent": str(payload.get("target_agent") or "pharmacovigilance"),
            "task_type": str(payload.get("task_type") or "delegate"),
            "status": "submitted",
            "symptom_event_id": symptom_event_id,
            "idempotency_key": idempotency_key,
            "input_payload": payload.get("input_payload") or {},
            "worker_payload": payload.get("worker_payload") or {},
            "error_message": None,
            "retry_attempt": 0,
            "max_retries": int(payload.get("max_retries") or self.DEFAULT_MAX_RETRIES),
            "next_retry_at": None,
            "dead_lettered_at": None,
        }
        self._validate_payload_sizes(row)
        try:
            return await self._insert_task(row)
        except Exception as exc:
            if not self._is_unique_violation(exc):
                raise

        existing_after_collision = await self._get_task_by_idempotency_key(
            patient_id=patient_id,
            idempotency_key=idempotency_key,
        )
        if existing_after_collision:
            return existing_after_collision
        raise ExternalServiceError("Supabase", "Failed to submit idempotent A2A task")

    async def mark_working(self, task_id: str, worker_payload: dict[str, Any]) -> dict[str, Any]:
        updates = {
            "status": "working",
            "worker_payload": worker_payload,
            "started_at": datetime.now(UTC).isoformat(),
            "error_message": None,
            "next_retry_at": None,
        }
        return await self._update_task(task_id, updates)

    async def mark_completed(self, task_id: str, output_payload: dict[str, Any]) -> dict[str, Any]:
        updates = {
            "status": "completed",
            "output_payload": output_payload,
            "completed_at": datetime.now(UTC).isoformat(),
            "error_message": None,
            "next_retry_at": None,
        }
        return await self._update_task(task_id, updates)

    async def mark_failed(self, task_id: str, error_message: str) -> dict[str, Any]:
        task = await self._get_task(task_id)
        current_attempt = int(task.get("retry_attempt") or 0)
        next_attempt = current_attempt + 1
        max_retries = int(task.get("max_retries") or self.DEFAULT_MAX_RETRIES)

        if next_attempt <= max_retries:
            retry_delay_seconds = self._calculate_retry_delay_seconds(next_attempt)
            retry_at = datetime.now(UTC).timestamp() + retry_delay_seconds
            updates = {
                "status": "retrying",
                "retry_attempt": next_attempt,
                "next_retry_at": datetime.fromtimestamp(retry_at, UTC).isoformat(),
                "error_message": error_message,
                "completed_at": None,
            }
            return await self._update_task(task_id, updates)

        updates = {
            "status": "dead_letter",
            "retry_attempt": next_attempt,
            "next_retry_at": None,
            "error_message": error_message,
            "completed_at": datetime.now(UTC).isoformat(),
            "dead_lettered_at": datetime.now(UTC).isoformat(),
        }
        return await self._update_task(task_id, updates)

    async def list_timeline(
        self,
        patient_id: str,
        *,
        session_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 200))
        query = (
            self.db.table("a2a_tasks")
            .select("*")
            .eq("patient_id", patient_id)
            .order("created_at", desc=True)
            .limit(safe_limit)
        )
        if session_id:
            query = query.eq("conversation_session_id", session_id)

        result = await self._execute(query)
        return [row for row in (result.data or []) if isinstance(row, dict)]

    async def list_due_retry_tasks(self, limit: int = 25) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 200))
        now_iso = datetime.now(UTC).isoformat()
        result = await self._execute(
            self.db.table("a2a_tasks")
            .select("*")
            .eq("status", "retrying")
            .lte("next_retry_at", now_iso)
            .order("next_retry_at", desc=False)
            .limit(safe_limit)
        )
        return [row for row in (result.data or []) if isinstance(row, dict)]

    async def retry_task(self, task_id: str) -> dict[str, Any]:
        task = await self._get_task(task_id)
        current_attempt = int(task.get("retry_attempt") or 0)

        await self.mark_working(
            task_id=task_id,
            worker_payload={
                "step": "retry_execution",
                "attempt": current_attempt + 1,
                "engine": "rule_based_v1",
            },
        )

        input_payload = task.get("input_payload")
        if not isinstance(input_payload, dict):
            input_payload = {}

        try:
            task_type = str(task.get("task_type") or "")
            if task_type == "symptom_adr_screen":
                output_payload = self._build_pharmacovigilance_result(input_payload)
            else:
                raise ValueError(f"Unsupported retry task type: {task_type or 'unknown'}")

            return await self.mark_completed(task_id=task_id, output_payload=output_payload)
        except Exception as exc:
            return await self.mark_failed(task_id=task_id, error_message=str(exc))

    async def process_due_retries(self, batch_size: int = 25) -> dict[str, int]:
        due_tasks = await self.list_due_retry_tasks(limit=batch_size)
        summary = {
            "scanned": len(due_tasks),
            "completed": 0,
            "rescheduled": 0,
            "dead_lettered": 0,
            "failed": 0,
        }

        for task in due_tasks:
            task_id = str(task.get("id") or "").strip()
            if not task_id:
                continue

            result = await self.retry_task(task_id)
            status = str(result.get("status") or "")
            if status == "completed":
                summary["completed"] += 1
            elif status == "retrying":
                summary["rescheduled"] += 1
            elif status == "dead_letter":
                summary["dead_lettered"] += 1
            else:
                summary["failed"] += 1

        return summary

    async def run_symptom_to_pharmacovigilance(
        self,
        patient_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        submitted = await self.submit_task(
            patient_id=patient_id,
            payload={
                "session_id": payload.get("session_id") or "default",
                "source_agent": "symptom",
                "target_agent": "pharmacovigilance",
                "task_type": "symptom_adr_screen",
                "input_payload": payload,
            },
        )
        events = [self._to_event(submitted)]

        task_id = str(submitted.get("id"))
        try:
            working = await self.mark_working(
                task_id=task_id,
                worker_payload={
                    "step": "naranjo_pre_screen",
                    "engine": "rule_based_v1",
                },
            )
            events.append(self._to_event(working))

            output_payload = self._build_pharmacovigilance_result(payload)
            completed = await self.mark_completed(task_id=task_id, output_payload=output_payload)
            events.append(self._to_event(completed))

            return {
                "task_id": task_id,
                "status": "completed",
                "events": events,
                "output": output_payload,
            }
        except Exception as exc:
            failed = await self.mark_failed(task_id=task_id, error_message=str(exc))
            events.append(self._to_event(failed))
            return {
                "task_id": task_id,
                "status": str(failed.get("status") or "failed"),
                "events": events,
                "error": str(exc),
            }

    async def _insert_task(self, row: dict[str, Any]) -> dict[str, Any]:
        result = await self._execute(self.db.table("a2a_tasks").insert(row))
        rows = [item for item in (result.data or []) if isinstance(item, dict)]
        if not rows:
            raise ExternalServiceError("Supabase", "Failed to submit A2A task")
        return rows[0]

    async def _update_task(self, task_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        result = await self._execute(self.db.table("a2a_tasks").update(updates).eq("id", task_id))
        rows = [item for item in (result.data or []) if isinstance(item, dict)]
        if rows:
            return rows[0]

        read_result = await self._execute(
            self.db.table("a2a_tasks").select("*").eq("id", task_id).limit(1)
        )
        read_rows = [item for item in (read_result.data or []) if isinstance(item, dict)]
        if not read_rows:
            raise ExternalServiceError("Supabase", f"A2A task {task_id} not found")
        return read_rows[0]

    async def _get_task(self, task_id: str) -> dict[str, Any]:
        result = await self._execute(
            self.db.table("a2a_tasks").select("*").eq("id", task_id).limit(1)
        )
        rows = [item for item in (result.data or []) if isinstance(item, dict)]
        if not rows:
            raise ExternalServiceError("Supabase", f"A2A task {task_id} not found")
        return rows[0]

    async def _get_task_by_idempotency_key(
        self,
        *,
        patient_id: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        result = await self._execute(
            self.db.table("a2a_tasks")
            .select("*")
            .eq("patient_id", patient_id)
            .eq("idempotency_key", idempotency_key)
            .limit(1)
        )
        rows = [item for item in (result.data or []) if isinstance(item, dict)]
        return rows[0] if rows else None

    async def _execute(self, query: Any) -> Any:
        for attempt in range(1, self.EXECUTE_MAX_ATTEMPTS + 1):
            try:
                return await asyncio.to_thread(query.execute)
            except Exception as exc:
                is_last_attempt = attempt >= self.EXECUTE_MAX_ATTEMPTS
                if is_last_attempt or not self.is_transient_supabase_error(exc):
                    raise
                await asyncio.sleep(self._calculate_execute_retry_delay_seconds(attempt))
        raise ExternalServiceError("Supabase", "A2A task query did not execute")

    @staticmethod
    def _is_unique_violation(exc: Exception) -> bool:
        code = str(getattr(exc, "code", "")).strip()
        if code == "23505":
            return True

        text = str(exc).lower()
        return "duplicate key" in text or "23505" in text

    @staticmethod
    def is_transient_supabase_error(exc: Exception) -> bool:
        if isinstance(
            exc,
            httpx.ConnectError
            | httpx.ConnectTimeout
            | httpx.ReadError
            | httpx.ReadTimeout
            | httpx.WriteError
            | httpx.WriteTimeout
            | httpx.PoolTimeout
            | httpx.RemoteProtocolError,
        ):
            return True

        text = str(exc).lower()
        transient_patterns = (
            "connection reset by peer",
            "operation timed out",
            "timed out",
            "temporarily unavailable",
            "connection refused",
            "connection aborted",
            "server disconnected",
            "network is unreachable",
            "name or service not known",
            "service unavailable",
            "gateway timeout",
        )
        return any(pattern in text for pattern in transient_patterns)

    @staticmethod
    def _calculate_retry_delay_seconds(attempt: int) -> int:
        # Exponential backoff with a cap to avoid runaway delays.
        return int(min(2 ** max(attempt, 1), 300))

    @staticmethod
    def _calculate_execute_retry_delay_seconds(attempt: int) -> float:
        # Keep transport retries short to avoid blocking worker cycles.
        return float(min(0.25 * (2 ** max(attempt - 1, 0)), 2.0))

    @staticmethod
    def _coerce_symptom_event_id(raw_value: Any) -> str | None:
        if raw_value is None:
            return None
        value = str(raw_value).strip()
        return value or None

    def _build_idempotency_key(
        self,
        *,
        payload: dict[str, Any],
        symptom_event_id: str | None,
    ) -> str:
        explicit_key = str(payload.get("idempotency_key") or "").strip()
        if explicit_key:
            return explicit_key

        if symptom_event_id:
            return f"symptom_event:{symptom_event_id}"

        # Fallback only for non-symptom workflows where no symptom event id exists.
        session_id = str(payload.get("session_id") or "default")
        task_type = str(payload.get("task_type") or "delegate")
        source_agent = str(payload.get("source_agent") or "triage")
        digest = hashlib.sha256(f"{session_id}:{task_type}:{source_agent}".encode()).hexdigest()
        return f"fallback:{digest}"

    def _validate_payload_sizes(self, row: dict[str, Any]) -> None:
        for key in ("input_payload", "worker_payload"):
            payload = row.get(key)
            try:
                encoded = json.dumps(
                    payload or {}, ensure_ascii=False, separators=(",", ":")
                ).encode()
            except TypeError as exc:
                raise ValidationError(f"A2A {key} is not JSON serializable") from exc

            if len(encoded) > self.MAX_JSON_PAYLOAD_BYTES:
                raise ValidationError(f"A2A {key} exceeds {self.MAX_JSON_PAYLOAD_BYTES} bytes")

    @staticmethod
    def _to_event(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "task_id": row.get("id"),
            "status": row.get("status"),
            "target_agent": row.get("target_agent"),
            "retry_attempt": row.get("retry_attempt"),
        }

    @staticmethod
    def _build_pharmacovigilance_result(payload: dict[str, Any]) -> dict[str, Any]:
        report = payload.get("symptom_report") or {}
        severity = int(report.get("severity") or 0)
        symptom = str(report.get("symptom") or "reported symptom")
        flagged_for_adr = bool(report.get("flagged_for_adr") or payload.get("flagged_for_adr"))

        requires_review = flagged_for_adr or severity >= 7
        priority = "high" if severity >= 8 or flagged_for_adr else "medium"

        if requires_review:
            recommendation = (
                "Open clinician ADR review queue entry and evaluate suspect medication linkage."
            )
        else:
            recommendation = "Monitor symptoms and continue routine follow-up."

        return {
            "requires_clinician_review": requires_review,
            "priority": priority,
            "symptom": symptom,
            "severity": severity,
            "recommendation": recommendation,
        }
