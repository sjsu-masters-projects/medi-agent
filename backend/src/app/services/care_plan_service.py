"""Automatic draft, clinician review, and deterministic care-plan publication."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from supabase import Client

from app.core import authorization_reasons as reasons
from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.models.care_plan import CarePlanCategory, CarePlanDraftUpdate
from app.models.clinical_fact import (
    ClinicalFactCreate,
    ConfidenceBand,
    EvidenceCitationCreate,
    SourceArtifactType,
    SourceProvenanceCreate,
)
from app.models.generation import GenerationErrorCode, GenerationProviderError
from app.services.care_plan_classification import (
    CarePlanClassificationError,
    classify_facts,
)
from app.services.care_plan_reconciliation import overlaps
from app.services.clinical_fact_service import ClinicalFactService

logger = logging.getLogger(__name__)

_LOW_CONFIDENCE = 0.7
_SOURCE_TITLE_REVIEW = (
    "Source title exceeds the draft limit; replace it after reviewing the full evidence."
)
_RETRY_DELAYS = (timedelta(minutes=5), timedelta(minutes=15), timedelta(hours=1))
_TRANSIENT_PROVIDER_FAILURES = frozenset(
    {
        GenerationErrorCode.RATE_LIMITED,
        GenerationErrorCode.TIMEOUT,
        GenerationErrorCode.UNAVAILABLE,
    }
)


class CarePlanSourceFieldsError(Exception):
    """Grounded wording cannot fit the current draft persistence contract."""


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
                self._log_generation_outcome(claim, outcome="ready")
            except Exception as error:  # noqa: BLE001 - classification owns the safe boundary
                outcome, failure = self._record_generation_failure(claim, error)
                counts[outcome] += 1
                diagnostics = (
                    error.diagnostics if isinstance(error, CarePlanClassificationError) else None
                )
                self._log_generation_outcome(
                    claim, outcome=outcome, failure_code=failure, diagnostics=diagnostics
                )
        return counts

    def get_for_clinician(self, clinician_id: UUID, patient_id: UUID) -> dict[str, Any] | None:
        self._require_assignment(clinician_id, patient_id)
        plans = self._plans(patient_id)
        return self._hydrate_plan(plans[0]) if plans else None

    def get_review_context_for_clinician(
        self, clinician_id: UUID, patient_id: UUID
    ) -> dict[str, Any]:
        """Return both review states without exposing another patient's plan."""
        self._require_assignment(clinician_id, patient_id)
        plans = self._plans(patient_id)
        active = next((plan for plan in plans if plan["status"] == "approved"), None)
        latest = plans[0] if plans else None
        return {
            "latest": self._hydrate_plan(latest) if latest else None,
            "active": self._hydrate_plan(active) if active and active != latest else None,
            "patient_locale": self._patient_locale(patient_id),
            "active_medications": self._active_medications(patient_id),
        }

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
        locale = self._patient_locale(patient_id)
        medications = self._active_medications(patient_id)
        validated: list[tuple[UUID, dict[str, Any]]] = []
        for item in update.items:
            original = known[str(item.id)]
            if item.language_verified and item.verified_locale != locale:
                raise ValidationError(
                    "Patient language changed; reload before verifying this draft"
                )
            if (
                original["category"] == "medication"
                and not item.is_removed
                and item.medication.get("decision")
            ):
                self._validate_medication_decision(item.medication, medications)
                if item.frequency.strip() != str(item.medication.get("frequency") or "").strip():
                    raise ValidationError("Medication frequency must match the patient-facing item")
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
                source_title_requires_edit=(
                    _SOURCE_TITLE_REVIEW in (original.get("uncertainty") or [])
                    and item.title.strip() == str(original["title"]).strip()
                ),
            )
            validated.append(
                (
                    item.id,
                    {
                        "title": item.title.strip(),
                        "instructions": item.instructions.strip(),
                        "frequency": item.frequency.strip(),
                        "schedule": item.schedule,
                        "medication": item.medication,
                        "is_removed": item.is_removed,
                        "blocker_reason": blocker,
                        "uncertainty": [
                            warning
                            for warning in (original.get("uncertainty") or [])
                            if warning != _SOURCE_TITLE_REVIEW
                            or item.title.strip() == str(original["title"]).strip()
                        ],
                        "reviewed_locale": locale
                        if item.language_verified and not item.is_removed
                        else None,
                    },
                )
            )
        for item_id, payload in validated:
            self.db.table("care_plan_items").update(payload).eq("id", str(item_id)).eq(
                "plan_version_id", str(plan_id)
            ).execute()
        self._audit(
            plan_id,
            clinician_id,
            "draft_edited",
            {
                "item_count": len(update.items),
                "removed_item_ids": [
                    str(item.id)
                    for item in update.items
                    if item.is_removed and not known[str(item.id)].get("is_removed")
                ],
                "restored_item_ids": [
                    str(item.id)
                    for item in update.items
                    if not item.is_removed and known[str(item.id)].get("is_removed")
                ],
            },
        )
        return self._hydrate_plan(self._plan(plan_id, patient_id))

    def approve(
        self, clinician_id: UUID, patient_id: UUID, plan_id: UUID, note: str
    ) -> dict[str, Any]:
        self._require_assignment(clinician_id, patient_id)
        self._draft(plan_id, patient_id)
        self._require_generation_complete(clinician_id, patient_id)
        locale = self._patient_locale(patient_id)
        medications = self._active_medications(patient_id)
        items = self._items(plan_id)
        for item in items:
            if item.get("is_removed"):
                continue
            if item.get("reviewed_locale") != locale:
                raise ValidationError("Verify every patient-facing item in the patient's language")
            if item["category"] == "medication":
                self._validate_medication_decision(item.get("medication") or {}, medications)
                if (
                    str(item.get("frequency") or "").strip()
                    != str((item.get("medication") or {}).get("frequency") or "").strip()
                ):
                    raise ValidationError("Medication frequency must match the patient-facing item")
        fact_ids = [str(item["source_fact_id"]) for item in items if item.get("source_fact_id")]
        facts: list[dict[str, Any]] = []
        if fact_ids:
            facts = cast(
                list[dict[str, Any]],
                self.db.table("clinical_facts")
                .select("id, fact_type, value")
                .in_("id", fact_ids)
                .execute()
                .data
                or [],
            )
        if overlaps(items, facts):
            raise ValidationError("Resolve overlapping plan items before publication")
        result = self.db.rpc(
            "approve_care_plan_version",
            {
                "p_plan_version_id": str(plan_id),
                "p_reviewer_id": str(clinician_id),
                "p_note": note.strip(),
            },
        ).execute()
        return cast(dict[str, Any], result.data or {})

    def _require_generation_complete(self, clinician_id: UUID, patient_id: UUID) -> None:
        generation = self.generation_for_clinician(clinician_id, patient_id)
        if generation and generation["status"] != "completed":
            raise ValidationError(
                "Automatic generation must complete before this draft can be published"
            )

    def _patient_locale(self, patient_id: UUID) -> str:
        result = (
            self.db.table("patients")
            .select("preferred_language")
            .eq("id", str(patient_id))
            .single()
            .execute()
        )
        patient = cast(dict[str, Any], result.data or {})
        return str(patient.get("preferred_language") or "en-US")

    def _active_medications(self, patient_id: UUID) -> list[dict[str, Any]]:
        result = (
            self.db.table("medications")
            .select("id, name, dosage, frequency, route, instructions, care_plan_item_id")
            .eq("patient_id", str(patient_id))
            .eq("is_active", True)
            .execute()
        )
        return cast(list[dict[str, Any]], result.data or [])

    @staticmethod
    def _validate_medication_decision(
        medication: dict[str, Any], active: list[dict[str, Any]]
    ) -> None:
        decision = medication.get("decision")
        name = str(medication.get("name") or "").strip().casefold()
        target_id = str(medication.get("target_id") or "")
        if decision == "create" and name and not target_id:
            if any(str(row.get("name") or "").strip().casefold() == name for row in active):
                raise ValidationError("An active medication with this name already exists")
            return
        if decision == "update" and target_id:
            target = next((row for row in active if str(row.get("id")) == target_id), None)
            if target and str(target.get("name") or "").strip().casefold() == name:
                return
        raise ValidationError("Choose an active matching medication to update or create a new one")

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
        proposed = [
            self._item_from_fact(
                fact,
                category=categories[str(fact["id"])],
                conflict=conflicts.get(str(fact["id"]), {}),
            )
            for fact in facts
        ]
        draft = self._open_draft(patient_id, str(claim["source_watermark"]))
        plan_id = UUID(str(draft["id"]))
        # All new evidence and the completion marker commit together. A retry
        # retains already-reviewed items and cannot acknowledge a partial write.
        self.db.rpc(
            "complete_care_plan_generation",
            {
                "p_plan_version_id": str(plan_id),
                "p_request_id": str(claim["request_id"]),
                "p_source_watermark": str(claim["source_watermark"]),
                "p_items": proposed,
            },
        ).execute()

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
        facts = cast(list[dict[str, Any]], result.data or [])
        if not facts:
            return []
        citations = cast(
            list[dict[str, Any]],
            self.db.table("evidence_citations")
            .select("fact_id, source_provenances!inner(artifact_type, document_id, withdrawn_at)")
            .in_("fact_id", [str(fact["id"]) for fact in facts])
            .execute()
            .data
            or [],
        )
        eligible = {
            str(row["fact_id"])
            for row in citations
            if (source := row.get("source_provenances"))
            and not source.get("withdrawn_at")
            and (
                source.get("artifact_type") == "clinician_entry"
                or (source.get("artifact_type") == "document" and source.get("document_id"))
            )
        }
        # SMART/FHIR candidates stay in External records. Importing a resource is
        # not an instruction to propose that historical therapy in today's plan.
        return [fact for fact in facts if str(fact["id"]) in eligible]

    async def _select_categories(self, facts: list[dict[str, Any]]) -> dict[str, str]:
        """Let the model classify fixed evidence; it cannot author an instruction."""
        return await classify_facts(facts)

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
        uncertainty = list(fact.get("uncertainty") or [])
        oversized_title = len(title) > 300
        if oversized_title:
            # Only the review heading is abbreviated. Full wording remains in the
            # linked fact/citations, and confirmation cannot publish this heading.
            title = title[:299] + "…"
            uncertainty.append(_SOURCE_TITLE_REVIEW)
        if len(instructions) > 2000:
            instructions = ""
            uncertainty.append(
                "Source instructions exceed the draft limit; review the full evidence."
            )
        if len(frequency) > 200:
            frequency = ""
            medication.pop("frequency", None)
            uncertainty.append(
                "Source frequency exceeds the draft limit; review the full evidence."
            )
        return {
            "source_fact_id": str(fact["id"]),
            "category": category,
            "title": title,
            "instructions": instructions,
            "frequency": frequency,
            "medication": medication,
            "confidence_score": fact.get("confidence_score"),
            "uncertainty": uncertainty,
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
                source_title_requires_edit=oversized_title,
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
                if item.get("projection_type") == "medication" and item.get("projection_id"):
                    payload["medication"] = {
                        **(item.get("medication") or {}),
                        "decision": "update",
                        "target_id": str(item["projection_id"]),
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

    def _record_generation_failure(
        self, claim: dict[str, Any], error: Exception
    ) -> tuple[str, str]:
        """Persist a safe outcome without retrying deterministic draft failures."""
        if isinstance(error, GenerationProviderError):
            failure = f"provider_{error.code.value}"
            if error.code in _TRANSIENT_PROVIDER_FAILURES:
                return (
                    ("care_plans_failed", failure)
                    if self._retry(claim, failure=failure)
                    else ("care_plans_retry", failure)
                )
        elif isinstance(error, CarePlanSourceFieldsError):
            failure = "source_fields_incomplete"
        elif isinstance(error, CarePlanClassificationError | ValueError):
            failure = "invalid_model_response"
        else:
            failure = "generation_internal_error"
        self._finish_request(claim, status="failed", plan_id=None, failure=failure)
        return "care_plans_failed", failure

    @staticmethod
    def _log_generation_outcome(
        claim: dict[str, Any],
        *,
        outcome: str,
        failure_code: str | None = None,
        diagnostics: dict[str, int | str] | None = None,
    ) -> None:
        """Emit a Cloud Run-correlatable outcome without source or patient content."""
        event: dict[str, int | str] = {
            "event": "care_plan_generation_outcome",
            "outcome": outcome,
            "request_id": str(claim["request_id"]),
            "attempt": int(claim.get("attempt") or 1),
        }
        if failure_code is not None:
            event["failure_code"] = failure_code
        if diagnostics is not None:
            event.update(diagnostics)
        log = logger.warning if failure_code is not None else logger.info
        log("%s", json.dumps(event, sort_keys=True, separators=(",", ":")))

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
        ).eq("id", str(claim["request_id"])).eq("status", "processing").eq(
            "source_watermark", str(claim["source_watermark"])
        ).execute()
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
        ).eq("id", str(claim["request_id"])).eq("status", "processing").eq(
            "source_watermark", str(claim["source_watermark"])
        ).execute()

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
        source_title_requires_edit: bool = False,
    ) -> str | None:
        if removed:
            return None
        if source_title_requires_edit:
            return _SOURCE_TITLE_REVIEW
        if (
            not title.strip()
            or not instructions.strip()
            or not frequency.strip()
            or frequency.strip().lower() == "as directed"
        ):
            return "Clarify the patient-facing instruction and frequency before approval."
        if category == "medication" and not all(
            str(medication.get(k) or "").strip() for k in ("name", "dosage", "frequency", "route")
        ):
            return "Medication name, dose, route, and frequency are required before approval."
        if category == "medication" and medication.get("route") not in {
            "oral",
            "topical",
            "inhaled",
            "iv",
            "im",
            "subcutaneous",
        }:
            return "Review and select a supported medication route before approval."
        if confirmed:
            return None
        if conflict:
            return "Resolve conflicting medication instructions before approval."
        if confidence is None or float(confidence) < _LOW_CONFIDENCE:
            return "Confirm this low-confidence source extraction before approval."
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
        sources: dict[str, list[dict[str, Any]]] = {}
        facts: list[dict[str, Any]] = []
        origins: dict[str, set[str]] = {}
        if fact_ids:
            facts = cast(
                list[dict[str, Any]],
                self.db.table("clinical_facts")
                .select("id, fact_type, value")
                .in_("id", fact_ids)
                .execute()
                .data
                or [],
            )
            citations = cast(
                list[dict[str, Any]],
                self.db.table("evidence_citations")
                .select("fact_id, excerpt, location, provenance_id")
                .in_("fact_id", fact_ids)
                .order("created_at")
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
                    .select("id, document_id, document_location, artifact_type")
                    .in_("id", provenance_ids)
                    .execute()
                    .data
                    or [],
                )
                if provenance_ids
                else []
            )
            by_provenance = {str(row["id"]): row for row in provenance}
            document_ids = list(
                {
                    str(row["document_id"])
                    for row in provenance
                    if row.get("document_id") is not None
                }
            )
            documents = (
                cast(
                    list[dict[str, Any]],
                    self.db.table("documents")
                    .select("id, file_name")
                    .in_("id", document_ids)
                    .execute()
                    .data
                    or [],
                )
                if document_ids
                else []
            )
            document_names = {str(row["id"]): row["file_name"] for row in documents}
            seen_citations: set[tuple[str, str, str, str]] = set()
            for citation in citations:
                source = by_provenance.get(str(citation.get("provenance_id")))
                if source:
                    origins.setdefault(str(citation["fact_id"]), set()).add(
                        str(source.get("artifact_type") or "unknown")
                    )
                    document_id = source.get("document_id")
                    location = citation.get("location") or source.get("document_location") or {}
                    excerpt = " ".join(str(citation.get("excerpt") or "").split())
                    key = (
                        str(citation["fact_id"]),
                        str(document_id),
                        json.dumps(location, sort_keys=True),
                        excerpt,
                    )
                    if key in seen_citations:
                        continue
                    seen_citations.add(key)
                    sources.setdefault(str(citation["fact_id"]), []).append(
                        {
                            "document_id": document_id,
                            "file_name": document_names.get(str(document_id)),
                            "excerpt": excerpt,
                            "location": location,
                        }
                    )
        peers = overlaps(items, facts) if plan.get("status") == "draft" else {}
        return {
            **plan,
            "items": [
                {
                    **item,
                    "overlapping_item_ids": peers.get(str(item["id"]), []),
                    "imported_evidence": bool(
                        origins.get(str(item.get("source_fact_id")))
                        and origins[str(item.get("source_fact_id"))]
                        <= {"fhir_resource", "external_record"}
                    ),
                    "source": next(iter(sources.get(str(item.get("source_fact_id")), [])), None),
                    "sources": sources.get(str(item.get("source_fact_id")), []),
                }
                for item in items
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
