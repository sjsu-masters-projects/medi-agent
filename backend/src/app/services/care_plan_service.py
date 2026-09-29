"""Automatic draft, clinician review, and deterministic care-plan publication."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from pydantic import ValidationError as PydanticValidationError
from supabase import Client

from app.clients.model_router import TaskType, get_router
from app.core import authorization_reasons as reasons
from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.models.care_plan import CarePlanCategory, CarePlanDraftProposal, CarePlanDraftUpdate
from app.models.clinical_fact import (
    ClinicalFactCreate,
    ConfidenceBand,
    EvidenceCitationCreate,
    SourceArtifactType,
    SourceProvenanceCreate,
)
from app.models.generation import GenerationErrorCode, GenerationProviderError
from app.services.care_plan_prompts import CARE_PLAN_DRAFT_SYSTEM, CARE_PLAN_DRAFT_USER
from app.services.clinical_fact_service import ClinicalFactService

_LOW_CONFIDENCE = 0.7
_RETRY_DELAYS = (timedelta(minutes=5), timedelta(minutes=15), timedelta(hours=1))
_TRANSIENT_PROVIDER_FAILURES = frozenset(
    {
        GenerationErrorCode.RATE_LIMITED,
        GenerationErrorCode.TIMEOUT,
        GenerationErrorCode.UNAVAILABLE,
    }
)


class CarePlanService:
    """Own the care-plan lifecycle; callers never publish a projection directly."""

    def __init__(self, db: Client) -> None:
        self.db = db

    def request_generation(self, patient_id: UUID, source_watermark: datetime) -> None:
        self.db.rpc(
            "request_care_plan_generation",
            {"p_patient_id": str(patient_id), "p_source_watermark": source_watermark.isoformat()},
        ).execute()

    async def process_pending(self, *, limit: int) -> dict[str, int]:
        claims = cast(
            list[dict[str, Any]],
            self.db.rpc("claim_pending_care_plan_generation", {"p_limit": limit}).execute().data
            or [],
        )
        counts = {
            "care_plans_claimed": len(claims),
            "care_plans_ready": 0,
            "care_plans_retry": 0,
            "care_plans_failed": 0,
        }
        for claim in claims:
            try:
                await self._generate(claim)
                counts["care_plans_ready"] += 1
            except Exception as error:  # noqa: BLE001 - classification owns the safe boundary
                counts[self._record_generation_failure(claim, error)] += 1
        return counts

    def get_for_clinician(self, clinician_id: UUID, patient_id: UUID) -> dict[str, Any] | None:
        self._require_assignment(clinician_id, patient_id)
        plans = self._plans(patient_id)
        return self._hydrate_plan(plans[0]) if plans else None

    def generation_for_clinician(
        self, clinician_id: UUID, patient_id: UUID
    ) -> dict[str, Any] | None:
        """Return durable draft state without exposing unassigned patient work."""
        self._require_assignment(clinician_id, patient_id)
        result = (
            self.db.table("care_plan_generation_requests")
            .select("*")
            .eq("patient_id", str(patient_id))
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = cast(list[dict[str, Any]], result.data or [])
        return rows[0] if rows else None

    def get_for_patient(self, patient_id: UUID) -> dict[str, Any] | None:
        result = (
            self.db.table("care_plan_versions")
            .select("*")
            .eq("patient_id", str(patient_id))
            .eq("status", "approved")
            .order("version_number", desc=True)
            .limit(1)
            .execute()
        )
        rows = cast(list[dict[str, Any]], result.data or [])
        return self._hydrate_plan(rows[0]) if rows else None

    def update_draft(
        self, clinician_id: UUID, patient_id: UUID, plan_id: UUID, update: CarePlanDraftUpdate
    ) -> dict[str, Any]:
        self._require_assignment(clinician_id, patient_id)
        plan = self._draft(plan_id, patient_id)
        known = {str(row["id"]): row for row in self._items(UUID(str(plan["id"])))}
        if set(str(item.id) for item in update.items) != set(known):
            raise ValidationError("The draft changed; reload before saving your review")
        for item in update.items:
            original = known[str(item.id)]
            blocker = self._blocker(
                category=str(original["category"]),
                title=item.title,
                instructions=item.instructions,
                frequency=item.frequency,
                medication=item.medication,
                confidence=original.get("confidence_score"),
                conflict=cast(dict[str, Any], original.get("conflict") or {}),
                removed=item.is_removed,
                confirmed=item.clinician_confirmed,
            )
            self.db.table("care_plan_items").update(
                {
                    "title": item.title.strip(),
                    "instructions": item.instructions.strip(),
                    "frequency": item.frequency.strip(),
                    "schedule": item.schedule,
                    "medication": item.medication,
                    "is_removed": item.is_removed,
                    "blocker_reason": blocker,
                }
            ).eq("id", str(item.id)).eq("plan_version_id", str(plan_id)).execute()
        self._audit(plan_id, clinician_id, "draft_edited", {"item_count": len(update.items)})
        return self._hydrate_plan(self._plan(plan_id, patient_id))

    def approve(
        self, clinician_id: UUID, patient_id: UUID, plan_id: UUID, note: str
    ) -> dict[str, Any]:
        self._require_assignment(clinician_id, patient_id)
        self._draft(plan_id, patient_id)
        result = self.db.rpc(
            "approve_care_plan_version",
            {
                "p_plan_version_id": str(plan_id),
                "p_reviewer_id": str(clinician_id),
                "p_note": note.strip(),
            },
        ).execute()
        return cast(dict[str, Any], result.data or {})

    def retry_failed_generation(self, clinician_id: UUID, patient_id: UUID) -> None:
        self._require_assignment(clinician_id, patient_id)
        latest = (
            self.db.table("care_plan_generation_requests")
            .select("*")
            .eq("patient_id", str(patient_id))
            .eq("status", "failed")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = cast(list[dict[str, Any]], latest.data or [])
        if not rows:
            raise ValidationError("There is no failed care-plan generation to retry")
        row = rows[0]
        self.db.table("care_plan_generation_requests").update(
            {
                "status": "pending",
                "attempts": 0,
                "failure_code": None,
                "requested_at": datetime.now(UTC).isoformat(),
            }
        ).eq("id", str(row["id"])).execute()

    def add_clinician_authored_obligation(
        self,
        clinician_id: UUID,
        patient_id: UUID,
        obligation_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Stage a clinician-authored activity in a draft; never publish it directly.

        This preserves the legacy clinician-obligation endpoint's input contract while
        removing its direct route into the patient Today feed.  The clinician entry is
        registered as explicit provenance, then it becomes a source-linked plan item
        that still requires whole-plan approval before any runtime projection exists.
        """
        self._require_assignment(clinician_id, patient_id)
        description = str(obligation_data["description"]).strip()
        frequency = str(obligation_data["frequency"]).strip()
        notes = str(obligation_data.get("notes") or "").strip()
        obligation_type = str(obligation_data["obligation_type"])
        instructions = notes or description
        excerpt = f"{description}\nFrequency: {frequency}"
        if notes:
            excerpt = f"{excerpt}\nNotes: {notes}"

        fact = ClinicalFactService(self.db).create_candidate(
            ClinicalFactCreate(
                patient_id=patient_id,
                fact_type="obligation",
                subject_type="patient",
                value={
                    "description": description,
                    "frequency": frequency,
                    "obligation_type": obligation_type,
                    "instructions": instructions,
                },
                confidence_score=1.0,
                confidence_band=ConfidenceBand.HIGH,
                provenance=SourceProvenanceCreate(
                    artifact_type=SourceArtifactType.CLINICIAN_ENTRY,
                    source_system="clinician_portal",
                    source_reference=f"clinician:{clinician_id}:care-plan-entry",
                    document_location={"kind": "clinician_authored_care_plan_entry"},
                ),
                citations=[
                    EvidenceCitationCreate(
                        excerpt=excerpt,
                        location={"kind": "clinician_authored_care_plan_entry"},
                    )
                ],
            ),
            actor_id=clinician_id,
        )
        draft = self._open_draft(patient_id, datetime.now(UTC).isoformat())
        category = {
            "diet": CarePlanCategory.NUTRITION.value,
            "exercise": CarePlanCategory.MOVEMENT.value,
            "custom": CarePlanCategory.OTHER.value,
        }[obligation_type]
        self.db.table("care_plan_items").insert(
            {
                "plan_version_id": str(draft["id"]),
                "source_fact_id": str(fact["id"]),
                "category": category,
                "title": description,
                "instructions": instructions,
                "frequency": frequency,
                "confidence_score": 1.0,
                "uncertainty": [],
                "conflict": {},
                "blocker_reason": None,
            }
        ).execute()
        self._audit(
            UUID(str(draft["id"])),
            clinician_id,
            "clinician_authored_item_added",
            {"source_fact_id": str(fact["id"]), "category": category},
        )
        return self._hydrate_plan(draft)

    async def _generate(self, claim: dict[str, Any]) -> None:
        patient_id = UUID(str(claim["patient_id"]))
        facts = self._plan_facts(patient_id)
        if not facts:
            self._finish_request(claim, status="completed", plan_id=None)
            return
        categories = await self._select_categories(facts)
        conflicts = self._medication_conflicts(facts)
        draft = self._open_draft(patient_id, str(claim["source_watermark"]))
        plan_id = UUID(str(draft["id"]))
        existing_fact_ids = {
            str(item["source_fact_id"])
            for item in self._items(plan_id)
            if item.get("source_fact_id") is not None
        }
        for fact in facts:
            if str(fact["id"]) in existing_fact_ids:
                continue
            item = self._item_from_fact(
                fact,
                category=categories[str(fact["id"])],
                conflict=conflicts.get(str(fact["id"]), {}),
            )
            self.db.table("care_plan_items").insert(
                {"plan_version_id": str(draft["id"]), **item}
            ).execute()
        self.db.table("care_plan_versions").update(
            {"source_watermark": str(claim["source_watermark"])}
        ).eq("id", str(plan_id)).execute()
        self._audit(plan_id, None, "generated", {"fact_count": len(facts)})
        self._finish_request(claim, status="completed", plan_id=plan_id)

    def _plan_facts(self, patient_id: UUID) -> list[dict[str, Any]]:
        result = (
            self.db.table("clinical_facts")
            .select("*")
            .eq("patient_id", str(patient_id))
            .in_("fact_type", ["medication", "obligation"])
            .in_("review_state", ["pending_review", "approved"])
            .order("created_at", desc=True)
            .execute()
        )
        return cast(list[dict[str, Any]], result.data or [])

    async def _select_categories(self, facts: list[dict[str, Any]]) -> dict[str, str]:
        """Let the model classify fixed evidence; it cannot author an instruction."""
        prompt_facts = [
            {
                "source_fact_id": str(fact["id"]),
                "fact_type": fact["fact_type"],
                "value": fact.get("value") or {},
                "confidence_score": fact.get("confidence_score"),
                "uncertainty": fact.get("uncertainty") or [],
            }
            for fact in facts
        ]
        response, _telemetry = await get_router().generate_text_with_telemetry(
            TaskType.CARE_PLAN_DRAFT,
            prompt=CARE_PLAN_DRAFT_USER.format(facts_json=json.dumps(prompt_facts, sort_keys=True)),
            system_instruction=CARE_PLAN_DRAFT_SYSTEM,
            temperature=0,
            max_tokens=1024,
        )
        proposal = CarePlanDraftProposal.model_validate_json(str(response))
        expected_ids = {str(fact["id"]) for fact in facts}
        selected_ids = [str(item.source_fact_id) for item in proposal.items]
        if set(selected_ids) != expected_ids or len(selected_ids) != len(expected_ids):
            raise ValueError("Care-plan draft must select every grounded source fact exactly once")

        categories = {str(item.source_fact_id): item.category.value for item in proposal.items}
        for fact in facts:
            category = categories[str(fact["id"])]
            if fact["fact_type"] == "medication" and category != CarePlanCategory.MEDICATION.value:
                raise ValueError("Medication facts must remain medication plan items")
            if fact["fact_type"] == "obligation" and category == CarePlanCategory.MEDICATION.value:
                raise ValueError("Obligation facts cannot become medication plan items")
        return categories

    @staticmethod
    def _medication_conflicts(facts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Block publication when one medication has incompatible source instructions."""
        groups: dict[str, list[dict[str, Any]]] = {}
        for fact in facts:
            if fact.get("fact_type") != "medication":
                continue
            value = cast(dict[str, Any], fact.get("value") or {})
            name = str(value.get("name") or "").strip().casefold()
            if name:
                groups.setdefault(name, []).append(fact)

        conflicts: dict[str, dict[str, Any]] = {}
        for name, candidates in groups.items():
            instructions = {
                tuple(
                    str(value.get(field) or "").strip().casefold()
                    for field in ("dosage", "frequency", "route", "instructions")
                )
                for candidate in candidates
                for value in [cast(dict[str, Any], candidate.get("value") or {})]
            }
            if len(instructions) < 2:
                continue
            fact_ids = sorted(str(candidate["id"]) for candidate in candidates)
            for candidate in candidates:
                conflicts[str(candidate["id"])] = {
                    "kind": "medication_reconciliation_conflict",
                    "medication_name": name,
                    "conflicting_fact_ids": [
                        fact_id for fact_id in fact_ids if fact_id != str(candidate["id"])
                    ],
                }
        return conflicts

    def _item_from_fact(
        self, fact: dict[str, Any], *, category: str, conflict: dict[str, Any]
    ) -> dict[str, Any]:
        value = cast(dict[str, Any], fact.get("value") or {})
        fact_type = str(fact["fact_type"])
        if fact_type == "medication":
            name = str(value.get("name") or "Medication")
            medication = {
                key: value.get(key)
                for key in ("name", "dosage", "frequency", "route")
                if value.get(key)
            }
            title = " ".join(filter(None, [name, str(value.get("dosage") or "")])).strip()
            frequency = str(value.get("frequency") or "")
            # Missing source instructions are a clinician-review blocker.  Do not
            # manufacture a patient-facing instruction such as "take as directed".
            instructions = str(value.get("instructions") or "")
        else:
            title = str(value.get("description") or "Care activity")
            frequency = str(value.get("frequency") or "")
            instructions = title
            medication = {}
        return {
            "source_fact_id": str(fact["id"]),
            "category": category,
            "title": title,
            "instructions": instructions,
            "frequency": frequency,
            "medication": medication,
            "confidence_score": fact.get("confidence_score"),
            "uncertainty": fact.get("uncertainty") or [],
            "conflict": conflict,
            "blocker_reason": self._blocker(
                category=category,
                title=title,
                instructions=instructions,
                frequency=frequency,
                medication=medication,
                confidence=fact.get("confidence_score"),
                conflict=conflict,
                removed=False,
                confirmed=False,
            ),
        }

    def _open_draft(self, patient_id: UUID, source_watermark: str) -> dict[str, Any]:
        existing = (
            self.db.table("care_plan_versions")
            .select("*")
            .eq("patient_id", str(patient_id))
            .eq("status", "draft")
            .limit(1)
            .execute()
        )
        rows = cast(list[dict[str, Any]], existing.data or [])
        if rows:
            return rows[0]
        latest = self._plans(patient_id)
        version = int(latest[0]["version_number"]) + 1 if latest else 1
        created = (
            self.db.table("care_plan_versions")
            .insert(
                {
                    "patient_id": str(patient_id),
                    "version_number": version,
                    "status": "draft",
                    "source_watermark": source_watermark,
                    "generated_at": datetime.now(UTC).isoformat(),
                }
            )
            .execute()
        )
        draft = cast(list[dict[str, Any]], created.data or [])[0]
        approved = next((plan for plan in latest if plan.get("status") == "approved"), None)
        if approved:
            for item in self._items(UUID(str(approved["id"]))):
                if item.get("is_removed"):
                    continue
                payload = {
                    key: value
                    for key, value in item.items()
                    if key
                    in {
                        "source_fact_id",
                        "category",
                        "title",
                        "instructions",
                        "frequency",
                        "schedule",
                        "medication",
                        "confidence_score",
                        "uncertainty",
                        "conflict",
                        "blocker_reason",
                        "is_removed",
                    }
                }
                self.db.table("care_plan_items").insert(
                    {
                        **payload,
                        "plan_version_id": str(draft["id"]),
                        "projection_type": None,
                        "projection_id": None,
                    }
                ).execute()
        return draft

    def _record_generation_failure(self, claim: dict[str, Any], error: Exception) -> str:
        """Persist a safe outcome without retrying deterministic draft failures."""
        if isinstance(error, GenerationProviderError):
            failure = f"provider_{error.code.value}"
            if error.code in _TRANSIENT_PROVIDER_FAILURES:
                return (
                    "care_plans_failed"
                    if self._retry(claim, failure=failure)
                    else "care_plans_retry"
                )
        elif isinstance(error, PydanticValidationError | ValueError):
            failure = "invalid_model_response"
        else:
            failure = "generation_internal_error"
        self._finish_request(claim, status="failed", plan_id=None, failure=failure)
        return "care_plans_failed"

    def _retry(self, claim: dict[str, Any], *, failure: str) -> bool:
        attempt = int(claim.get("attempt") or 1)
        if attempt >= 3:
            self._finish_request(claim, status="failed", plan_id=None, failure=failure)
            return True
        self.db.table("care_plan_generation_requests").update(
            {
                "status": "retry",
                "next_attempt_at": (datetime.now(UTC) + _RETRY_DELAYS[attempt - 1]).isoformat(),
                "failure_code": failure,
                "claimed_at": None,
            }
        ).eq("id", str(claim["request_id"])).execute()
        return False

    def _finish_request(
        self,
        claim: dict[str, Any],
        *,
        status: str,
        plan_id: UUID | None,
        failure: str | None = None,
    ) -> None:
        self.db.table("care_plan_generation_requests").update(
            {
                "status": status,
                "plan_version_id": str(plan_id) if plan_id else None,
                "completed_at": datetime.now(UTC).isoformat(),
                "failure_code": failure,
            }
        ).eq("id", str(claim["request_id"])).execute()

    @staticmethod
    def _blocker(
        *,
        category: str,
        title: str,
        instructions: str,
        frequency: str,
        medication: dict[str, Any],
        confidence: Any,
        conflict: dict[str, Any] | None = None,
        removed: bool,
        confirmed: bool,
    ) -> str | None:
        if removed or confirmed:
            return None
        if conflict:
            return "Resolve conflicting medication instructions before approval."
        if (
            not title.strip()
            or not instructions.strip()
            or not frequency.strip()
            or frequency.strip().lower() == "as directed"
        ):
            return "Clarify the patient-facing instruction and frequency before approval."
        if confidence is None or float(confidence) < _LOW_CONFIDENCE:
            return "Confirm this low-confidence source extraction before approval."
        if category == "medication" and not all(
            str(medication.get(k) or "").strip() for k in ("name", "dosage", "frequency", "route")
        ):
            return "Medication name, dose, route, and frequency are required before approval."
        return None

    def _plans(self, patient_id: UUID) -> list[dict[str, Any]]:
        result = (
            self.db.table("care_plan_versions")
            .select("*")
            .eq("patient_id", str(patient_id))
            .order("version_number", desc=True)
            .execute()
        )
        return cast(list[dict[str, Any]], result.data or [])

    def _plan(self, plan_id: UUID, patient_id: UUID) -> dict[str, Any]:
        result = (
            self.db.table("care_plan_versions")
            .select("*")
            .eq("id", str(plan_id))
            .eq("patient_id", str(patient_id))
            .single()
            .execute()
        )
        plan = cast(dict[str, Any] | None, result.data)
        if not plan:
            raise NotFoundError("Care plan", str(plan_id))
        return plan

    def _draft(self, plan_id: UUID, patient_id: UUID) -> dict[str, Any]:
        plan = self._plan(plan_id, patient_id)
        if plan.get("status") != "draft":
            raise ValidationError("Only the current draft can be edited")
        return plan

    def _items(self, plan_id: UUID) -> list[dict[str, Any]]:
        result = (
            self.db.table("care_plan_items")
            .select("*")
            .eq("plan_version_id", str(plan_id))
            .order("created_at")
            .execute()
        )
        return cast(list[dict[str, Any]], result.data or [])

    def _hydrate_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        items = self._items(UUID(str(plan["id"])))
        fact_ids = [str(item["source_fact_id"]) for item in items if item.get("source_fact_id")]
        sources: dict[str, dict[str, Any]] = {}
        if fact_ids:
            citations = cast(
                list[dict[str, Any]],
                self.db.table("evidence_citations")
                .select("fact_id, excerpt, location, provenance_id")
                .in_("fact_id", fact_ids)
                .execute()
                .data
                or [],
            )
            provenance_ids = [
                str(row["provenance_id"]) for row in citations if row.get("provenance_id")
            ]
            provenance = (
                cast(
                    list[dict[str, Any]],
                    self.db.table("source_provenances")
                    .select("id, document_id, document_location")
                    .in_("id", provenance_ids)
                    .execute()
                    .data
                    or [],
                )
                if provenance_ids
                else []
            )
            by_provenance = {str(row["id"]): row for row in provenance}
            for citation in citations:
                source = by_provenance.get(str(citation.get("provenance_id")))
                if source:
                    sources[str(citation["fact_id"])] = {
                        "document_id": source.get("document_id"),
                        "excerpt": citation.get("excerpt"),
                        "location": citation.get("location")
                        or source.get("document_location")
                        or {},
                    }
        return {
            **plan,
            "items": [
                {**item, "source": sources.get(str(item.get("source_fact_id")))} for item in items
            ],
        }

    def _audit(
        self, plan_id: UUID, actor_id: UUID | None, event: str, data: dict[str, Any]
    ) -> None:
        self.db.table("care_plan_audit_events").insert(
            {
                "plan_version_id": str(plan_id),
                "actor_id": str(actor_id) if actor_id else None,
                "event_type": event,
                "event_data": data,
            }
        ).execute()

    def _require_assignment(self, clinician_id: UUID, patient_id: UUID) -> None:
        rows = cast(
            list[dict[str, Any]],
            self.db.table("care_teams")
            .select("id")
            .eq("clinician_id", str(clinician_id))
            .eq("patient_id", str(patient_id))
            .eq("status", "active")
            .limit(1)
            .execute()
            .data
            or [],
        )
        if not rows:
            raise AuthorizationError(
                "You are not assigned to this patient",
                reason_code=reasons.NO_CARE_TEAM_ASSIGNMENT,
                actor_id=str(clinician_id),
                actor_role="clinician",
                target_type="patient",
                target_id=str(patient_id),
            )
