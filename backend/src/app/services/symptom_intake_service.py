"""Owned intake orchestration; database transactions own mutation and confirmation."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, cast
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from postgrest.exceptions import APIError
from supabase import Client

from app.config import settings
from app.core.exceptions import AuthorizationError, ValidationError
from app.intake.conversation import interpret, source_suggestions
from app.intake.library import Bundle, load_library, select_question, validate_value
from app.intake.preview import retrieve_context, summarize, verify_context
from app.models.auth import CurrentUser
from app.models.symptom_intake import (
    IntakeAnswer,
    IntakeConfirm,
    IntakeMutation,
    IntakeReply,
    IntakeStart,
)
from app.safety.intake_gate import IntakeSafetyDecision, evaluate_intake_safety, safety_response
from app.safety.triage_floor import SafetyVerdict
from app.services.a2a_task_service import A2ATaskService
from app.services.chat_safety_service import ChatSafetyService
from app.utils.localization import written_language

logger = logging.getLogger(__name__)


class SymptomIntakeService:
    def __init__(self, db: Client, actor: CurrentUser) -> None:
        self.db = db
        self.actor = actor

    def library(self, version: str | None = None) -> Bundle:
        if not settings.symptom_intake_enabled:
            raise ValidationError("Intake unavailable", code="INTAKE_LIBRARY_UNAVAILABLE")
        return load_library(version)

    async def _call(self, action: str, payload: dict[str, Any]) -> Any:
        if self.actor.role != "patient":
            raise self._denial()
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    self.db.rpc(
                        "symptom_intake_operation",
                        {
                            "p_patient_id": str(self.actor.id),
                            "p_action": action,
                            "p_payload": payload,
                        },
                    ).execute
                ),
                timeout=8,
            )
        except APIError as exc:
            if exc.code == "42501":
                raise self._denial() from None
            codes = {
                "INTAKE_REVISION_CONFLICT",
                "INTAKE_MUTATION_CONFLICT",
                "INTAKE_TERMINAL",
                "INTAKE_PREVIEW_STALE",
                "INTAKE_LIBRARY_UNAVAILABLE",
            }
            code = exc.message if exc.message in codes else "INTAKE_PERSISTENCE_UNAVAILABLE"
            raise ValidationError("Intake operation unavailable", code=code) from None
        except (TimeoutError, OSError, httpx.TransportError):
            raise ValidationError(
                "Intake persistence uncertain", code="INTAKE_PERSISTENCE_UNAVAILABLE"
            ) from None
        return result.data

    def _denial(self) -> AuthorizationError:
        return AuthorizationError(
            "Intake unavailable",
            actor_id=str(self.actor.id),
            actor_role=self.actor.role,
            target_type="symptom_intake",
            reason_code="PATIENT_SCOPE_SELF_ONLY",
        )

    async def read(self, intake_id: UUID | str) -> dict[str, Any]:
        return await self._visible(await self._read_row(intake_id))

    async def _read_row(self, intake_id: UUID | str) -> dict[str, Any]:
        return cast(dict[str, Any], await self._call("read", {"intake_id": str(intake_id)}))

    async def active(self, session_id: str) -> dict[str, Any] | None:
        row = await self._call("active", {"session_id": session_id})
        return await self._visible(row) if isinstance(row, dict) else None

    async def _visible(self, row: dict[str, Any]) -> dict[str, Any]:
        response = self.describe(row)
        if row["status"] in {"collecting", "ready_for_confirmation"}:
            source = await self._source(
                IntakeStart(
                    source_message_id=row["source_message_id"], session_id=row["session_id"]
                )
            )
            response["suggestions"] = source_suggestions(str(source["content"]))
        if row.get("preview"):
            try:
                visible = await verify_context(self.db, row)
            except ValidationError:
                visible = False
            if not visible:
                response.update(preview=None, can_confirm=False, context_stale=True)
        return response

    async def report(self, report_id: UUID) -> dict[str, Any]:
        report = cast(dict[str, Any], await self._call("report", {"report_id": str(report_id)}))
        content = report.get("confirmed_content") or {}
        row = {"id": report["intake_id"], "patient_id": str(self.actor.id), "preview": content}
        try:
            visible = await verify_context(self.db, row)
        except ValidationError:
            visible = False
        if not visible:
            report["confirmed_content"] = {**content, "context": None, "context_unavailable": True}
        return report

    async def start(self, data: IntakeStart) -> dict[str, Any]:
        source = await self._source(data)
        decision = evaluate_intake_safety(str(source["content"]), str(source["language"]))
        if decision:
            record = await ChatSafetyService(self.db).record_safely(
                str(self.actor.id),
                {
                    "turn_id": str(source["id"]),
                    "session_id": source["session_id"],
                    "content": source["content"],
                    "audio_url": source.get("audio_url"),
                    "language": source["language"],
                    "intent": decision.verdict.intent,
                    **self._safety(decision),
                },
            )
            return {
                "status": "interrupted_safety",
                "safety": self._safety(decision),
                "persistence_status": record["persistence_status"],
            }
        bundle = self.library()
        profile = await asyncio.to_thread(
            self.db.table("patients")
            .select("timezone")
            .eq("id", str(self.actor.id))
            .single()
            .execute
        )
        timezone, fallback = self._timezone(
            cast(dict[str, Any], profile.data or {}).get("timezone")
        )
        row = await self._call(
            "start",
            {
                **data.model_dump(mode="json"),
                "library_version": bundle.version,
                "library_hash": bundle.checksum,
                "timezone": timezone,
                "timezone_fallback": fallback,
            },
        )
        response = self.describe(row)
        response["suggestions"] = (
            source_suggestions(str(source["content"]))
            if row["source_message_id"] == str(data.source_message_id)
            else {}
        )
        response["existing_draft"] = row["source_message_id"] != str(data.source_message_id)
        return response

    async def _source(self, data: IntakeStart) -> dict[str, Any]:
        result = await asyncio.to_thread(
            self.db.table("chat_messages")
            .select("id,content,language,session_id,role,audio_url")
            .eq("patient_id", str(self.actor.id))
            .eq("id", str(data.source_message_id))
            .execute
        )
        rows = cast(list[dict[str, Any]], result.data or [])
        if (
            not rows
            or rows[0].get("role") != "user"
            or rows[0].get("session_id") != data.session_id
        ):
            raise self._denial()
        return rows[0]

    @staticmethod
    def _timezone(value: Any) -> tuple[str, bool]:
        try:
            ZoneInfo(str(value))
            return str(value), False
        except (ZoneInfoNotFoundError, ValueError):
            return "UTC", True

    def describe(self, row: dict[str, Any]) -> dict[str, Any]:
        response = {
            **row,
            "intake_id": row["id"],
            "current_question": None,
            "library_available": False,
            "can_review": False,
            "can_confirm": False,
        }
        try:
            bundle = self.library(row["library_version"])
        except ValidationError:
            return response
        if bundle.checksum != row["library_hash"] or row.get("database_library_available") is False:
            return response
        response["library_available"] = True
        if row["status"] in {"collecting", "ready_for_confirmation"}:
            question = select_question(bundle, row["answers"])
            response["current_question"] = question.model_dump(mode="json") if question else None
            response["can_review"] = question is None
            response["can_confirm"] = question is None and row["status"] == "ready_for_confirmation"
        response["questions"] = [q.model_dump(mode="json") for q in bundle.questions]
        response["progress"] = {"resolved": len(row["answers"]), "budget": bundle.budget}
        return response

    async def answer(self, intake_id: UUID, data: IntakeAnswer) -> dict[str, Any]:
        row = await self._read_row(intake_id)
        decision = evaluate_intake_safety(self._answer_text(data), data.locale)
        if decision:
            return await self.interrupt(row, data.model_dump(mode="json"), decision)
        bundle = self.library(row["library_version"])
        question = bundle.question(data.question_id)
        if (
            data.question_id not in row["answers"]
            and select_question(bundle, row["answers"]) != question
        ):
            raise ValidationError("Answer the current question", code="INTAKE_ANSWER_INVALID")
        validate_value(question, data.state, data.value)
        if data.state == "answered" and data.value is True and question.positive_safety_rule:
            verdict = SafetyVerdict(
                intent="mental_health" if "mental" in question.positive_safety_rule else "symptom",
                urgency="emergency",
                reason="Reviewed structured answer mapping",
                safety_rule=question.positive_safety_rule,
            )
            return await self.interrupt(
                row,
                data.model_dump(mode="json"),
                IntakeSafetyDecision(verdict, safety_response(verdict, data.locale)),
            )
        payload = {
            "intake_id": str(intake_id),
            "expected_revision": data.expected_revision,
            "mutation_id": str(data.mutation_id),
            "answer": data.model_dump(mode="json", exclude={"expected_revision", "mutation_id"}),
        }
        return self.describe(await self._call("answer", payload))

    async def reply(self, intake_id: UUID, data: IntakeReply) -> dict[str, Any]:
        row = await self._read_row(intake_id)
        locale = written_language(data.text, data.locale).value
        decision = evaluate_intake_safety(data.text, locale)
        if decision:
            return await self.interrupt(row, data.model_dump(mode="json"), decision)
        bundle = self.library(row["library_version"])
        question = bundle.question(data.question_id)
        if (
            data.question_id not in row["answers"]
            and select_question(bundle, row["answers"]) != question
        ):
            raise ValidationError("Answer the current question", code="INTAKE_ANSWER_INVALID")
        state, value = interpret(question, data.text)
        return await self.answer(
            intake_id,
            IntakeAnswer(
                expected_revision=data.expected_revision,
                mutation_id=data.mutation_id,
                question_id=data.question_id,
                state=state,
                value=value,
                wording=data.text,
                locale=locale,
                input_mode=data.input_mode,
            ),
        )

    @staticmethod
    def _answer_text(data: IntakeAnswer) -> str:
        value = data.value
        if isinstance(value, dict):
            text = " ".join(str(v) for v in value.values() if isinstance(v, str))
        else:
            text = value if isinstance(value, str) else ""
        return f"{data.wording} {text}"

    @staticmethod
    def _safety(decision: IntakeSafetyDecision) -> dict[str, Any]:
        return {
            "safety_rule": decision.verdict.safety_rule,
            "rule_version": decision.rule_version,
            "result": "interrupted_safety",
            "response_text": decision.response_text,
        }

    async def interrupt(
        self, row: dict[str, Any], request: dict[str, Any], decision: IntakeSafetyDecision
    ) -> dict[str, Any]:
        safety = self._safety(decision)
        payload = {
            "intake_id": row["id"],
            "expected_revision": request.get("expected_revision", row["revision"]),
            "mutation_id": request.get("mutation_id", str(uuid4())),
            "safety": safety,
        }
        try:
            result = self.describe(await self._call("interrupt", payload))
            result["safety"] = safety
            return result
        except ValidationError:
            return {
                "intake_id": row["id"],
                "status": "interrupted_safety",
                "safety": safety,
                "persistence_status": "uncertain",
            }

    async def cancel(self, intake_id: UUID, data: IntakeMutation) -> dict[str, Any]:
        return self.describe(
            await self._call(
                "cancel", {"intake_id": str(intake_id), **data.model_dump(mode="json")}
            )
        )

    async def preview(self, intake_id: UUID, expected_revision: int) -> dict[str, Any]:
        row = await self._read_row(intake_id)
        decision = self._ledger_safety(row, None)
        if decision:
            return await self.interrupt(row, {}, decision)
        bundle = self.library(row["library_version"])
        decision = self._ledger_safety(row, bundle)
        if decision:
            return await self.interrupt(row, {}, decision)
        if (
            row["status"] == "ready_for_confirmation"
            and row["revision"] == expected_revision + 1
            and await verify_context(self.db, row)
        ):
            return self.describe(row)
        if select_question(bundle, row["answers"]) is not None:
            raise ValidationError("Resolve required questions", code="INTAKE_ANSWER_INVALID")
        context = await retrieve_context(self.db, row)
        summary = summarize(row, bundle)
        product = row["answers"].get("product", {})
        if product.get("state") == "answered" and product.get("value", {}).get("concern") is True:
            name = str(product["value"].get("name", ""))
            matched = any(
                str(m.get("name", "")).strip().casefold() == name.strip().casefold()
                for m in context.get("medications", [])
            )
            label = (
                (
                    "Producto reportado por el paciente — sin verificar"
                    if matched
                    else "Producto reportado por el paciente, no encontrado en la lista actual — sin verificar"
                )
                if row["locale"] == "es-MX"
                else (
                    "Patient-reported product — unverified"
                    if matched
                    else "Patient-reported product, not on the current medication list — unverified"
                )
            )
            summary += f"\n{label}: {name}"
        if row["answers"].get("concomitant", {}).get("state") == "answered":
            summary += "\n" + (
                "Los productos y cambios adicionales son reportados por el paciente, sin verificar."
                if row["locale"] == "es-MX"
                else "Additional products and changes are patient-reported and unverified."
            )
        snapshot = {
            "schema_version": "symptom-report/1",
            "answers": row["answers"],
            "context": context,
            "summary": summary,
            "source_message_id": row["source_message_id"],
            "session_id": row["session_id"],
            "locale": row["locale"],
            "timezone": row["timezone"],
            "library_version": bundle.version,
            "library_hash": bundle.checksum,
            "safety": {"rule_version": "triage-floor/1", "result": "no_existing_rule_matched"},
            "selection": self._selection(bundle, row["answers"]),
        }
        return self.describe(
            await self._call(
                "preview",
                {
                    "intake_id": str(intake_id),
                    "expected_revision": expected_revision,
                    "preview": snapshot,
                },
            )
        )

    @staticmethod
    def _selection(bundle: Bundle, answers: dict[str, Any]) -> dict[str, Any]:
        product = answers.get("product", {})
        return {
            q.id: {
                "state": "not_applicable"
                if q.applies_if
                and (
                    product.get("state") != "answered"
                    or product.get("value", {}).get("concern") is not True
                )
                else "not_asked",
                "reason": "no_patient_supplied_product_concern"
                if q.applies_if
                else "question_budget",
            }
            for q in bundle.questions
            if q.id not in answers
        }

    @staticmethod
    def _ledger_safety(row: dict[str, Any], bundle: Bundle | None) -> IntakeSafetyDecision | None:
        for key, answer in row["answers"].items():
            question = bundle.question(key) if bundle else None
            if not answer:
                continue
            text = str(answer.get("wording", "")) + " "
            value = answer.get("value")
            text += (
                " ".join(str(v) for v in value.values() if isinstance(v, str))
                if isinstance(value, dict)
                else (value if isinstance(value, str) else "")
            )
            decision = evaluate_intake_safety(text, row["locale"])
            if decision:
                return decision
            if value is True and question and question.positive_safety_rule:
                verdict = SafetyVerdict(
                    intent="mental_health"
                    if "mental" in question.positive_safety_rule
                    else "symptom",
                    urgency="emergency",
                    reason="Reviewed structured mapping",
                    safety_rule=question.positive_safety_rule,
                )
                return IntakeSafetyDecision(verdict, safety_response(verdict, row["locale"]))
        return None

    async def confirm(self, intake_id: UUID, data: IntakeConfirm) -> dict[str, Any]:
        row = await self._read_row(intake_id)
        payload = {"intake_id": str(intake_id), **data.model_dump(mode="json")}
        if row["status"] == "confirmed":
            confirmed = self.describe(await self._call("confirm", payload))
            return await self._handoff_confirmed_product_concern(confirmed)
        decision = self._ledger_safety(row, None)
        if decision:
            return await self.interrupt(row, {}, decision)
        bundle = self.library(row["library_version"])
        decision = self._ledger_safety(row, bundle)
        if decision:
            return await self.interrupt(row, {}, decision)
        if not self.describe(row)["can_confirm"] or not await verify_context(self.db, row):
            raise ValidationError("Preview must be rebuilt", code="INTAKE_PREVIEW_STALE")
        confirmed = self.describe(await self._call("confirm", payload))
        return await self._handoff_confirmed_product_concern(confirmed)

    async def _handoff_confirmed_product_concern(self, confirmed: dict[str, Any]) -> dict[str, Any]:
        report_id = str(confirmed.get("confirmed_report_id") or "").strip()
        if not report_id:
            return confirmed
        try:
            report = cast(dict[str, Any], await self._call("report", {"report_id": report_id}))
            if not A2ATaskService.confirmed_product_concern(report):
                return confirmed
            medication_id, _medication_name = A2ATaskService.confirmed_medication(report)
            if not medication_id:
                return {
                    **confirmed,
                    "adr_handoff": {
                        "task_id": None,
                        "status": "requires_medication_reconciliation",
                    },
                }
            handoff = await A2ATaskService(self.db).run_symptom_to_pharmacovigilance(
                patient_id=str(self.actor.id),
                payload={
                    "session_id": confirmed.get("session_id") or "default",
                    "symptom_report": report,
                },
            )
            return {
                **confirmed,
                "adr_handoff": {
                    "task_id": handoff.get("task_id"),
                    "status": handoff.get("status"),
                },
            }
        except Exception:
            # Confirmation is authoritative and must not become ambiguous because a
            # downstream worker is temporarily unavailable. An idempotent retry of
            # the same confirmation will retry the report-scoped handoff.
            logger.exception("Confirmed symptom ADR handoff failed", extra={"report_id": report_id})
            return {**confirmed, "adr_handoff": {"task_id": None, "status": "pending"}}
