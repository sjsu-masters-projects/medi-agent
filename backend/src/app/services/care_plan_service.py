"""Automatic draft, clinician review, and deterministic care-plan publication."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from postgrest.exceptions import APIError
from supabase import Client

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.care_plan import (
    PATIENT_LOCALES,
    CarePlanCategory,
    CarePlanDraftUpdate,
    CarePlanItemUpdate,
    PatientLocale,
)
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
from app.services.care_plan_evidence_gate import eligible_fact_ids
from app.services.care_plan_lineage import CarePlanLineageService
from app.services.care_plan_reconciliation import overlaps
from app.services.care_plan_translation import draft_translations, validate_draft
from app.services.clinical_fact_service import ClinicalFactService
from app.services.document_intelligence.grounding import (
    INACTIVE_MEDICATION_ACTIONS,
    medication_action,
)
from app.services.fact_display_translation import detected_fact_locale

logger = logging.getLogger(__name__)

_LOW_CONFIDENCE = 0.7
_STOP_SOURCE_BLOCKER = (
    "This document says to stop or hold this medication, so it cannot become a Today "
    "activity. Update the medication list if needed, then remove this item."
)


def _medication_action(fact: dict[str, Any]) -> str | None:
    value = cast(dict[str, Any], fact.get("value") or {})
    stored = value.get("medication_action")
    return str(stored) if stored else medication_action(value.get("status"))


# A printed strength in a medication name ("20 mg", "0.5 mL", "100 units", "2.5%").
_STRENGTH = re.compile(r"\d+(?:[.,]\d+)?\s*(?:mg|mcg|µg|g|ml|units?|iu|meq|%)(?![a-z])", re.I)
_SOURCE_TITLE_REVIEW = (
    "Source title exceeds the draft limit; replace it after reviewing the full evidence."
)
_RETRY_DELAYS = (timedelta(minutes=5), timedelta(minutes=15), timedelta(hours=1))
_WORDING_FIELDS = ("title", "instructions", "frequency")
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
        self.lineage = CarePlanLineageService(db)

    def request_generation_for_plan(self, care_plan_id: UUID, source_watermark: datetime) -> None:
        """Ask for a fresh draft of ONE plan; only that plan's own sources are used."""
        self.db.rpc(
            "request_care_plan_generation_for_plan",
            {
                "p_care_plan_id": str(care_plan_id),
                "p_source_watermark": source_watermark.isoformat(),
            },
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

    def get_for_clinician(
        self,
        clinician_id: UUID,
        patient_id: UUID,
        *,
        care_team_id: UUID | None = None,
        care_plan_id: UUID | None = None,
    ) -> dict[str, Any] | None:
        """The latest version of the clinician's own plan; never another team's."""
        plan = self.lineage.select_owned_plan(
            clinician_id, patient_id, care_team_id=care_team_id, care_plan_id=care_plan_id
        )
        if plan is None:
            return None
        versions = self._versions(UUID(str(plan["id"])))
        return self._hydrate_plan(versions[0]) if versions else None

    def get_review_context_for_clinician(
        self,
        clinician_id: UUID,
        patient_id: UUID,
        *,
        care_team_id: UUID | None = None,
        care_plan_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Both review states of the clinician's own plan, without another team's plan."""
        plan = self.lineage.select_owned_plan(
            clinician_id, patient_id, care_team_id=care_team_id, care_plan_id=care_plan_id
        )
        versions = self._versions(UUID(str(plan["id"]))) if plan else []
        active = next((version for version in versions if version["status"] == "approved"), None)
        latest = versions[0] if versions else None
        return {
            "care_plan_id": plan["id"] if plan else None,
            "latest": self._hydrate_plan(latest) if latest else None,
            "active": self._hydrate_plan(active) if active and active != latest else None,
            "patient_locale": self._patient_locale(patient_id),
            "active_medications": self._active_medications(patient_id),
        }

    def generation_for_clinician(
        self,
        clinician_id: UUID,
        patient_id: UUID,
        *,
        care_team_id: UUID | None = None,
        care_plan_id: UUID | None = None,
    ) -> dict[str, Any] | None:
        """Durable draft state of the clinician's own plan."""
        plan = self.lineage.select_owned_plan(
            clinician_id, patient_id, care_team_id=care_team_id, care_plan_id=care_plan_id
        )
        if plan is None:
            return None
        return self._latest_generation(UUID(str(plan["id"])))

    def _latest_generation(self, care_plan_id: UUID) -> dict[str, Any] | None:
        result = (
            self.db.table("care_plan_generation_requests")
            .select("*")
            .eq("care_plan_id", str(care_plan_id))
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = cast(list[dict[str, Any]], result.data or [])
        return rows[0] if rows else None

    def plans_for_clinician(self, clinician_id: UUID, patient_id: UUID) -> list[dict[str, Any]]:
        """Every plan of the patient, as much of each as this clinician may know.

        Their own plans come with version ids and generation state. Another team's plan is
        only that it exists: specialty, clinician, clinic and approval date (its medications
        are on the shared summary). An unowned plan lists who may adopt it.
        """
        scopes = self.lineage.clinician_scopes(clinician_id, patient_id)
        mine = {str(scope.care_team_id) for scope in scopes}
        plans = self.lineage.plans_for_patient(patient_id)
        displays = self.lineage.team_displays(
            [str(plan["care_team_id"]) for plan in plans if plan.get("care_team_id")]
        )
        result: list[dict[str, Any]] = []
        for plan in plans:
            versions = self._versions(UUID(str(plan["id"])))
            approved = next((v for v in versions if v["status"] == "approved"), None)
            draft = next((v for v in versions if v["status"] == "draft"), None)
            entry: dict[str, Any] = {
                "care_plan_id": plan["id"],
                "care_team_id": plan.get("care_team_id"),
                "ownership_state": plan["ownership_state"],
                "origin": plan["origin"],
                "owner": self.lineage.owner_view(plan, displays),
                "approved_at": approved["approved_at"] if approved else None,
                "unowned_since": plan.get("unowned_since"),
                "is_mine": plan.get("ownership_state") == "owned"
                and str(plan.get("care_team_id")) in mine,
            }
            if entry["is_mine"]:
                entry["active_version_id"] = approved["id"] if approved else None
                entry["draft_version_id"] = draft["id"] if draft else None
                entry["latest_version_number"] = versions[0]["version_number"] if versions else None
                entry["generation"] = self._latest_generation(UUID(str(plan["id"])))
            elif plan.get("ownership_state") != "owned":
                entry["adoptable_by_care_team_ids"] = sorted(mine)
            result.append(entry)
        return result

    def unowned_activities(
        self, clinician_id: UUID, patient_id: UUID, care_plan_id: UUID
    ) -> dict[str, Any]:
        """The approved activities of an unowned plan, so a clinician can adopt or retire.

        Only plans nobody owns open here, and only to a clinician linked to the patient:
        those activities are already in the patient's Today and no team's detail is exposed.
        """
        self.lineage.clinician_scopes(clinician_id, patient_id)
        plan = self.lineage.plan(care_plan_id)
        if (
            plan is None
            or str(plan["patient_id"]) != str(patient_id)
            or plan.get("ownership_state") == "owned"
        ):
            raise NotFoundError("Care plan", str(care_plan_id))
        versions = self._versions(care_plan_id)
        approved = next((v for v in versions if v["status"] == "approved"), None)
        retired = {
            str(row["item_id"])
            for row in cast(
                list[dict[str, Any]],
                self.db.table("care_plan_item_retirements")
                .select("item_id")
                .eq("care_plan_id", str(care_plan_id))
                .execute()
                .data
                or [],
            )
        }
        items = (
            [
                {
                    key: item.get(key)
                    for key in (
                        "id",
                        "category",
                        "title",
                        "instructions",
                        "frequency",
                        "medication",
                        "wording",
                    )
                }
                for item in self._items(UUID(str(approved["id"])))
                if not item.get("is_removed") and str(item["id"]) not in retired
            ]
            if approved
            else []
        )
        displays = self.lineage.team_displays([])
        return {
            "care_plan_id": plan["id"],
            "ownership_state": plan["ownership_state"],
            "previous_owner": self.lineage.owner_view(plan, displays),
            "unowned_since": plan.get("unowned_since"),
            "approved_at": approved["approved_at"] if approved else None,
            "activities": items,
        }

    def get_for_patient(self, patient_id: UUID) -> dict[str, Any] | None:
        """Every approved plan of the patient, merged; each item names its plan's owner.

        ``id``/``version_number``/``approved_at`` describe the newest approved plan so the
        single-plan consumers keep working; ``plans`` lists each plan with its owner.
        """
        plans = self.lineage.plans_for_patient(patient_id)
        approved: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for plan in plans:
            version = next(
                (v for v in self._versions(UUID(str(plan["id"]))) if v["status"] == "approved"),
                None,
            )
            if version:
                approved.append((plan, version))
        if not approved:
            return None
        displays = self.lineage.team_displays(
            [str(plan["care_team_id"]) for plan, _ in approved if plan.get("care_team_id")]
        )
        retired = {
            str(row["item_id"])
            for row in cast(
                list[dict[str, Any]],
                self.db.table("care_plan_item_retirements")
                .select("item_id")
                .in_("care_plan_id", [str(plan["id"]) for plan, _ in approved])
                .execute()
                .data
                or [],
            )
        }
        items: list[dict[str, Any]] = []
        summaries: list[dict[str, Any]] = []
        for plan, version in approved:
            owner = {
                "care_plan_id": plan["id"],
                "care_team_id": plan.get("care_team_id"),
                "ownership_state": plan["ownership_state"],
                "unowned_notice": plan["ownership_state"] != "owned",
                **self.lineage.owner_view(plan, displays),
            }
            hydrated = self._hydrate_plan(version)
            for item in hydrated["items"]:
                if item.get("is_removed") or str(item["id"]) in retired:
                    continue
                items.append({**item, "plan_owner": owner})
            summaries.append(
                {
                    **owner,
                    "plan_version_id": version["id"],
                    "version_number": version["version_number"],
                    "approved_at": version["approved_at"],
                }
            )
        newest = max(approved, key=lambda pair: str(pair[1]["approved_at"]))[1]
        return {
            "id": newest["id"],
            "patient_id": str(patient_id),
            "version_number": newest["version_number"],
            "approved_at": newest["approved_at"],
            "status": "approved",
            "items": items,
            "plans": summaries,
        }

    def update_draft(
        self, clinician_id: UUID, patient_id: UUID, plan_id: UUID, update: CarePlanDraftUpdate
    ) -> dict[str, Any]:
        _, care_plan = self.lineage.require_owned_version(clinician_id, patient_id, plan_id)
        plan = self._draft(plan_id, patient_id)
        known = {str(row["id"]): row for row in self._items(UUID(str(plan["id"])))}
        if set(str(item.id) for item in update.items) != set(known):
            raise ValidationError("The draft changed; reload before saving your review")
        medications = self._active_medications(patient_id)
        own_items = self._own_plan_item_ids(UUID(str(care_plan["id"])))
        validated: list[tuple[UUID, dict[str, Any]]] = []
        for item in update.items:
            original = known[str(item.id)]
            medication_error = None
            wording_fields = self._reviewed_wording(original, item)
            if wording_fields["source_locale"]:
                # The source-language copy is what reconciliation and continuity compare.
                source = wording_fields["wording"].get(wording_fields["source_locale"])
                if source:
                    item = item.model_copy(
                        update={field: source[field] for field in _WORDING_FIELDS}
                    )
            if original["category"] == "medication" and not item.is_removed:
                try:
                    self._validate_medication_decision(
                        item.medication, medications, own_items=own_items
                    )
                    if (
                        item.frequency.strip()
                        != str(item.medication.get("frequency") or "").strip()
                    ):
                        raise ValidationError(
                            "Medication frequency must match the patient-facing item"
                        )
                except ValidationError as exc:
                    # Review must remain saveable before reconciliation is complete.
                    # Publication validates the decision independently and still rejects it.
                    medication_error = str(exc)
            verified = bool(
                item.wording_verified
                and not item.is_removed
                and self._wording_complete({**item.model_dump(), **wording_fields})
            )
            if verified:
                self._require_wording_guards({**item.model_dump(), **wording_fields})
            blocker = self._blocker(
                category=str(original["category"]),
                title=item.title,
                instructions=item.instructions,
                frequency=item.frequency,
                medication=item.medication,
                confidence=original.get("confidence_score"),
                conflict=cast(dict[str, Any], original.get("conflict") or {}),
                removed=item.is_removed,
                confirmed=item.clinician_confirmed or self._retains_confirmation(original, item),
                source_title_requires_edit=(
                    _SOURCE_TITLE_REVIEW in (original.get("uncertainty") or [])
                    and item.title.strip() == str(original["title"]).strip()
                ),
            )
            blocker = medication_error or blocker
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
                        **wording_fields,
                        "wording_verified": verified,
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
                "confirmed_item_ids": [
                    str(item.id)
                    for item in update.items
                    if item.clinician_confirmed and not item.is_removed
                ],
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

    @staticmethod
    def _reviewed_wording(original: dict[str, Any], item: CarePlanItemUpdate) -> dict[str, Any]:
        """Merge submitted wording; any changed language is marked as clinician edited."""
        before = cast(dict[str, dict[str, str]], original.get("wording") or {})
        origin = dict(cast(dict[str, str], original.get("wording_origin") or {}))
        source_locale = original.get("source_locale") or item.source_locale
        wording = dict(before)
        for locale, text in item.wording.items():
            stripped = {field: getattr(text, field).strip() for field in _WORDING_FIELDS}
            if before.get(locale) != stripped:
                unchanged_source = locale == source_locale and all(
                    stripped[field] == str(original.get(field) or "").strip()
                    for field in _WORDING_FIELDS
                )
                origin[locale] = "source" if unchanged_source else "clinician_edited"
            wording[locale] = stripped
        if source_locale and source_locale in wording:
            origin.setdefault(source_locale, "source")
        return {"source_locale": source_locale, "wording": wording, "wording_origin": origin}

    @staticmethod
    def _require_wording_guards(item: dict[str, Any]) -> None:
        """Reject verification of wording whose two languages disagree on a checked fact.

        The browser asks for the same checks, but the API must not be a way around them.
        The stored English and Spanish wording is compared directly (numbers with units,
        negation, medication name); a model is not called on a save or an approval.
        """
        wording = cast(dict[str, dict[str, str]], item.get("wording") or {})
        source_locale = item.get("source_locale")
        if source_locale not in PATIENT_LOCALES:
            return
        other = "es-MX" if source_locale == "en-US" else "en-US"
        reason = validate_draft(wording.get(source_locale) or {}, wording.get(other) or {}, item)
        if reason:
            labels = {
                "numbers_changed": "numbers or units differ between the languages",
                "negation_changed": "a negation (no, not, never, without) differs between the languages",
                "medication_name_changed": "a medication name differs between the languages",
                "field_missing": "a field is empty in one language",
            }
            raise ValidationError(
                f"The wording cannot be marked verified: {labels.get(reason, reason)}. "
                "Fix the wording and check it again."
            )

    @staticmethod
    def _wording_complete(item: dict[str, Any]) -> bool:
        """Mirror of private.care_plan_wording_is_complete for a clear preflight error."""
        wording = cast(dict[str, dict[str, str]], item.get("wording") or {})
        source_locale = item.get("source_locale")
        if source_locale not in PATIENT_LOCALES:
            return False
        if any(
            not str((wording.get(locale) or {}).get(field) or "").strip()
            for locale in PATIENT_LOCALES
            for field in _WORDING_FIELDS
        ):
            return False
        return all(
            str(wording[source_locale][field]).strip() == str(item.get(field) or "").strip()
            for field in _WORDING_FIELDS
        )

    async def retranslate_item(
        self,
        clinician_id: UUID,
        patient_id: UUID,
        plan_id: UUID,
        item_id: UUID,
        from_locale: PatientLocale,
    ) -> dict[str, Any]:
        """Redraft the other language from the reviewed source wording of one item."""
        self.lineage.require_owned_version(clinician_id, patient_id, plan_id)
        self._draft(plan_id, patient_id)
        item = next((row for row in self._items(plan_id) if str(row["id"]) == str(item_id)), None)
        if item is None or item.get("is_removed"):
            raise NotFoundError("Care plan item", str(item_id))
        source_locale = item.get("source_locale")
        if source_locale and source_locale != from_locale:
            raise ValidationError(
                "Translations are drafted from the source wording; edit the source language first"
            )
        try:
            drafts, diagnostics = await draft_translations([{**item, "source_locale": from_locale}])
        except GenerationProviderError:
            raise ValidationError(
                "Translation is unavailable right now. Try again, or write it yourself."
            ) from None
        draft = drafts.get(str(item_id))
        if draft is None:
            self._log_translation_outcome(plan_id, diagnostics)
            raise ValidationError(
                "The translation changed a number or medication name, so it was discarded. "
                "Try again, or write it yourself."
            )
        self._store_translation(
            item, draft.source_locale, draft.target_locale, draft.wording.model_dump()
        )
        self._audit(
            plan_id,
            clinician_id,
            "translation_drafted",
            {"item_id": str(item_id), "target_locale": draft.target_locale},
        )
        return self._hydrate_plan(self._plan(plan_id, patient_id))

    async def back_translate_item(
        self,
        clinician_id: UUID,
        patient_id: UUID,
        plan_id: UUID,
        item_id: UUID,
    ) -> dict[str, Any]:
        """LOC-003: Back-translate the Spanish wording of one item to English for verification."""
        from app.services.care_plan_translation import back_translate_spanish

        self.lineage.require_owned_version(clinician_id, patient_id, plan_id)
        self._plan(plan_id, patient_id)  # same 404 for an unknown or another patient's plan
        item = next((row for row in self._items(plan_id) if str(row["id"]) == str(item_id)), None)
        if item is None or item.get("is_removed"):
            raise NotFoundError("Care plan item", str(item_id))
        wording = cast(dict[str, dict[str, str]], item.get("wording") or {})
        spanish = wording.get("es-MX") or {}
        english = wording.get("en-US") or {}
        if not (spanish.get("title") or "").strip():
            raise ValidationError("No Spanish wording to back-translate")
        try:
            result = await back_translate_spanish(spanish, english, item)
        except (GenerationProviderError, ValueError):
            raise ValidationError(
                "The back-translation is unavailable right now. Try again in a moment."
            ) from None
        return {
            "back_translation": {
                "title": result.title,
                "instructions": result.instructions,
                "frequency": result.frequency,
            },
            "guards": {
                "numbers_match": result.numbers_match,
                "medication_names_match": result.medication_names_match,
            },
        }

    def _store_translation(
        self,
        item: dict[str, Any],
        source_locale: str,
        target_locale: str,
        translated: dict[str, str],
    ) -> None:
        wording = dict(cast(dict[str, dict[str, str]], item.get("wording") or {}))
        origin = dict(cast(dict[str, str], item.get("wording_origin") or {}))
        wording[source_locale] = {
            field: str(item.get(field) or "").strip() for field in _WORDING_FIELDS
        }
        wording[target_locale] = translated
        origin.setdefault(source_locale, "source")
        origin[target_locale] = "ai_draft"
        self.db.table("care_plan_items").update(
            {
                "source_locale": source_locale,
                "wording": wording,
                "wording_origin": origin,
                "wording_verified": False,
            }
        ).eq("id", str(item["id"])).eq("plan_version_id", str(item["plan_version_id"])).execute()

    async def _draft_missing_translations(self, plan_id: UUID) -> dict[str, int]:
        """Fill the second language for draft items that lack one; never fails generation."""
        pending = [
            item
            for item in self._items(plan_id)
            if not item.get("is_removed")
            and any(
                not (cast(dict[str, Any], item.get("wording") or {}).get(locale))
                for locale in PATIENT_LOCALES
            )
        ]
        if not pending:
            return {}
        drafts, diagnostics = await draft_translations(pending)
        for item in pending:
            draft = drafts.get(str(item["id"]))
            if draft is not None:
                self._store_translation(
                    item, draft.source_locale, draft.target_locale, draft.wording.model_dump()
                )
        return diagnostics

    @staticmethod
    def _log_translation_outcome(plan_id: UUID, diagnostics: Mapping[str, int | str]) -> None:
        event: dict[str, int | str] = {
            "event": "care_plan_translation_outcome",
            "plan_version_id": str(plan_id),
            **diagnostics,
        }
        logger.info("%s", json.dumps(event, sort_keys=True, separators=(",", ":")))

    @staticmethod
    def _retains_confirmation(original: dict[str, Any], item: CarePlanItemUpdate) -> bool:
        """A saved resolution applies only to exactly unchanged, active review content."""
        return (
            "blocker_reason" in original
            and original["blocker_reason"] is None
            and not original.get("is_removed")
            and not item.is_removed
            and all(
                str(original.get(field) or "").strip() == getattr(item, field).strip()
                for field in ("title", "instructions", "frequency")
            )
            and (original.get("schedule") or {}) == item.schedule
            and (original.get("medication") or {}) == item.medication
        )

    def approve(
        self,
        clinician_id: UUID,
        patient_id: UUID,
        plan_id: UUID,
        note: str,
        *,
        idempotency_key: UUID | None = None,
        excluded_item_ids: Sequence[UUID] = (),
    ) -> dict[str, Any]:
        """Publish the draft in one database transaction under the patient-wide lock.

        Cross-plan checks run in the database against current state. A blocker raises a
        ConflictError whose details list the conflicts to resolve; nothing is published.
        """
        self.publication_snapshot(clinician_id, patient_id, plan_id, excluded=excluded_item_ids)
        try:
            result = self.db.rpc(
                "publish_care_plan_version",
                {
                    "p_plan_version_id": str(plan_id),
                    "p_reviewer_id": str(clinician_id),
                    "p_note": note.strip(),
                    "p_idempotency_key": str(idempotency_key or uuid4()),
                    "p_excluded_item_ids": [str(item_id) for item_id in excluded_item_ids],
                },
            ).execute()
        except APIError as error:
            raise self._publication_error(error, clinician_id, patient_id, plan_id) from None
        return cast(dict[str, Any], result.data or {})

    def _publication_error(
        self, error: APIError, clinician_id: UUID, patient_id: UUID, plan_id: UUID
    ) -> Exception:
        code = str(error.code or "")
        message = str(error.message or "")
        if code == "CP001":
            # Re-read the comparison for the response: both instructions and plan metadata.
            review = self.cross_plan_review(clinician_id, patient_id, plan_id)
            return ConflictError(
                "Resolve each conflict with the patient's other plans before publishing",
                code="CROSS_PLAN_CONFLICT",
                details={
                    "conflicts": [c for c in review["conflicts"] if c["severity"] == "blocker"],
                    "interaction_coverage": review["interaction_coverage"],
                },
            )
        if code == "42501" and "care plan unavailable" in message:
            return NotFoundError("Care plan", str(plan_id))
        if code == "22023" and "different request" in message:
            return ConflictError(
                "This request key was already used for a different request",
                code="IDEMPOTENCY_KEY_REUSED",
            )
        if "not eligible for approval" in message:
            return ConflictError("This draft was already published or replaced; reload")
        return ValidationError(message[:300] or "The care plan could not be published")

    def cross_plan_review(
        self, clinician_id: UUID, patient_id: UUID, plan_id: UUID
    ) -> dict[str, Any]:
        """Conflicts with other plans and the shared list, from the database's own check."""
        self.lineage.require_owned_version(clinician_id, patient_id, plan_id)
        try:
            result = self.db.rpc(
                "care_plan_cross_plan_review",
                {"p_plan_version_id": str(plan_id), "p_reviewer_id": str(clinician_id)},
            ).execute()
        except APIError as error:
            raise self._publication_error(error, clinician_id, patient_id, plan_id) from None
        return cast(dict[str, Any], result.data or {"conflicts": []})

    def record_conflict_resolution(
        self,
        clinician_id: UUID,
        patient_id: UUID,
        plan_id: UUID,
        *,
        fingerprint: str,
        resolution: str,
        reason: str,
    ) -> dict[str, Any]:
        """Keep both (with a written reason) or ask the other care team. Both tell them."""
        self.lineage.require_owned_version(clinician_id, patient_id, plan_id)
        try:
            result = self.db.rpc(
                "record_cross_plan_resolution",
                {
                    "p_plan_version_id": str(plan_id),
                    "p_actor_id": str(clinician_id),
                    "p_fingerprint": fingerprint,
                    "p_resolution": resolution,
                    "p_reason": reason.strip(),
                },
            ).execute()
        except APIError as error:
            if str(error.code) == "40001":
                raise ConflictError(
                    "This conflict has changed; review it again", code="CONFLICT_CHANGED"
                ) from None
            raise self._publication_error(error, clinician_id, patient_id, plan_id) from None
        return cast(dict[str, Any], result.data or {})

    def publication_snapshot(
        self,
        clinician_id: UUID,
        patient_id: UUID,
        plan_id: UUID,
        *,
        excluded: Sequence[UUID] = (),
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Read-only publication preflight. The transaction rechecks these guards.

        Items published without are left out of the checks: they stay pending in the draft.
        """
        _, care_plan = self.lineage.require_owned_version(clinician_id, patient_id, plan_id)
        plan = self._draft(plan_id, patient_id)
        self._require_generation_complete(UUID(str(care_plan["id"])))
        medications = self._active_medications(patient_id)
        own_items = self._own_plan_item_ids(UUID(str(care_plan["id"])))
        skipped = {str(item_id) for item_id in excluded}
        items = [item for item in self._items(plan_id) if str(item.get("id")) not in skipped]
        for item in items:
            if item.get("is_removed"):
                continue
            if not self._wording_complete(item):
                raise ValidationError(
                    "Add English and Spanish wording for every patient-facing item"
                )
            if not item.get("wording_verified"):
                raise ValidationError(
                    "Check the English and Spanish wording of every patient-facing item"
                )
            self._require_wording_guards(item)
            if item["category"] == "medication":
                self._validate_medication_decision(
                    item.get("medication") or {}, medications, own_items=own_items
                )
                if (
                    str(item.get("frequency") or "").strip()
                    != str((item.get("medication") or {}).get("frequency") or "").strip()
                ):
                    raise ValidationError("Medication frequency must match the patient-facing item")
        fact_ids = [
            str(item["source_fact_id"])
            for item in items
            if not item.get("is_removed") and item.get("source_fact_id")
        ]
        if any(
            not item.get("source_fact_id") for item in items if not item.get("is_removed")
        ) or set(fact_ids) - eligible_fact_ids(self.db, patient_id, fact_ids):
            raise ValidationError(
                "Review and approve patient-uploaded source documents before preview or publication; "
                "rejected, missing or withdrawn sources must be removed from the draft"
            )
        facts: list[dict[str, Any]] = []
        if fact_ids:
            facts = cast(
                list[dict[str, Any]],
                self.db.table("clinical_facts")
                .select("id, fact_type, value")
                .eq("patient_id", str(patient_id))
                .in_("id", fact_ids)
                .in_("review_state", ["pending_review", "approved"])
                .execute()
                .data
                or [],
            )
            if set(fact_ids) - {str(fact["id"]) for fact in facts}:
                raise ValidationError(
                    "Remove missing or rejected source facts before preview or publication"
                )
        if overlaps(items, facts):
            raise ValidationError("Resolve overlapping plan items before publication")
        return plan, items

    def _require_generation_complete(self, care_plan_id: UUID) -> None:
        generation = self._latest_generation(care_plan_id)
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
        medication: dict[str, Any],
        active: list[dict[str, Any]],
        *,
        own_items: set[str] | None = None,
    ) -> None:
        """Per-plan shape of the decision. Duplicates of ANOTHER plan's or the shared list's
        medication are not rejected here: the database compares them at publication and the
        clinician resolves each one (change, keep both with a reason, ask, publish without).

        ``own_items`` are the care-plan item ids of this plan's lineage. A medication that
        this plan already projects cannot be created a second time, and a medication owned
        by another plan's activity cannot be updated from here.
        """
        decision = medication.get("decision")
        name = str(medication.get("name") or "").strip().casefold()
        target_id = str(medication.get("target_id") or "")
        own = own_items or set()
        if decision == "create" and name and not target_id:
            if any(
                str(row.get("name") or "").strip().casefold() == name
                and str(row.get("care_plan_item_id")) in own
                for row in active
            ):
                raise ValidationError("An active medication with this name already exists")
            return
        if decision == "update" and target_id:
            target = next((row for row in active if str(row.get("id")) == target_id), None)
            if target and str(target.get("name") or "").strip().casefold() == name:
                owner_item = target.get("care_plan_item_id")
                if owner_item and own_items is not None and str(owner_item) not in own:
                    raise ValidationError(
                        "This medication belongs to another care plan; "
                        "create your own entry or ask that care team"
                    )
                return
        raise ValidationError("Choose an active matching medication to update or create a new one")

    def _own_plan_item_ids(self, care_plan_id: UUID) -> set[str]:
        """Every care-plan item id in this plan's lineage (all versions)."""
        versions = [str(version["id"]) for version in self._versions(care_plan_id)]
        if not versions:
            return set()
        rows = cast(
            list[dict[str, Any]],
            self.db.table("care_plan_items")
            .select("id")
            .in_("plan_version_id", versions)
            .execute()
            .data
            or [],
        )
        return {str(row["id"]) for row in rows}

    def retry_failed_generation(
        self,
        clinician_id: UUID,
        patient_id: UUID,
        *,
        care_team_id: UUID | None = None,
        care_plan_id: UUID | None = None,
    ) -> None:
        plan = self.lineage.select_owned_plan(
            clinician_id, patient_id, care_team_id=care_team_id, care_plan_id=care_plan_id
        )
        if plan is None:
            raise ValidationError("There is no failed care-plan generation to retry")
        latest = (
            self.db.table("care_plan_generation_requests")
            .select("*")
            .eq("care_plan_id", str(plan["id"]))
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
        *,
        care_team_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Stage a clinician-authored activity in a draft; never publish it directly.

        This preserves the legacy clinician-obligation endpoint's input contract while
        removing its direct route into the patient Today feed.  The clinician entry is
        registered as explicit provenance, then it becomes a source-linked plan item
        that still requires whole-plan approval before any runtime projection exists.
        """
        scope = self.lineage.scope_for_team(clinician_id, patient_id, care_team_id)
        care_plan_id = self.lineage.ensure_plan_id(clinician_id, scope)
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
                    care_team_id=scope.care_team_id,
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
        draft = self._open_draft(patient_id, care_plan_id, datetime.now(UTC).isoformat())
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
        care_plan_id = UUID(str(claim["care_plan_id"]))
        facts = self._plan_facts(patient_id, care_plan_id)
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
        draft = self._open_draft(patient_id, care_plan_id, str(claim["source_watermark"]))
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
        # Outside the generation transaction: an unavailable translation leaves the item
        # untranslated for the clinician to retry, and never fails or rolls back the draft.
        try:
            diagnostics: dict[str, int | str] = dict(
                await self._draft_missing_translations(plan_id)
            )
        except GenerationProviderError as error:
            diagnostics = {"translation_provider_error": error.code.value}
        except Exception:  # noqa: BLE001 - the draft is already durable and reviewable
            logger.exception("Care-plan translation failed after generation")
            diagnostics = {"translation_internal_error": 1}
        if diagnostics:
            self._log_translation_outcome(plan_id, diagnostics)

    def _plan_facts(self, patient_id: UUID, care_plan_id: UUID) -> list[dict[str, Any]]:
        """Only the evidence routed to THIS plan's care team, never another team's.

        The database selects the eligible fact ids: sources routed to the plan's team, plus
        its clinician entries. SMART/FHIR candidates stay in External records; importing a
        resource is not an instruction to propose that historical therapy in today's plan.
        """
        ids = [
            str(value)
            for value in cast(
                list[Any],
                self.db.rpc("care_plan_source_fact_ids", {"p_care_plan_id": str(care_plan_id)})
                .execute()
                .data
                or [],
            )
        ]
        if not ids:
            return []
        result = (
            self.db.table("clinical_facts")
            .select("*")
            .eq("patient_id", str(patient_id))
            .in_("id", ids)
            .in_("fact_type", ["medication", "obligation"])
            .in_("review_state", ["pending_review", "approved"])
            .order("created_at", desc=True)
            .execute()
        )
        facts = cast(list[dict[str, Any]], result.data or [])
        eligible = eligible_fact_ids(self.db, patient_id, [str(fact["id"]) for fact in facts])
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
            stops = [
                candidate
                for candidate in candidates
                if _medication_action(candidate) in INACTIVE_MEDICATION_ACTIONS
            ]
            if stops:
                # A document that stops or holds a medicine outranks a matching instruction
                # to take it: the stop line itself can never be published as a Today task,
                # and every other line for the same medicine needs a clinician decision.
                stop_ids = sorted(str(candidate["id"]) for candidate in stops)
                for candidate in candidates:
                    fact_id = str(candidate["id"])
                    is_stop = fact_id in stop_ids
                    conflicts[fact_id] = {
                        "kind": "medication_stop_source" if is_stop else "medication_stopped",
                        "medication_name": name,
                        "action": _medication_action(candidate),
                        "stop_fact_ids": [item for item in stop_ids if item != fact_id],
                    }
                continue
            for candidate in candidates:
                if _medication_action(candidate) == "changed":
                    # "Increase to 20 mg daily" usually sits beside the old printed dose; the
                    # clinician sets the new dose and instructions before approval.
                    value = cast(dict[str, Any], candidate.get("value") or {})
                    conflicts[str(candidate["id"])] = {
                        "kind": "medication_changed",
                        "medication_name": name,
                        "action": "changed",
                        "printed_change": str(value.get("status") or "")[:200],
                    }
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
            dosage = str(value.get("dosage") or "")
            # "Atorvastatin 20 mg tablet" already carries its strength; appending the
            # per-dose count gave "Atorvastatin 20 mg tablet 1 tablet".
            title = name if _STRENGTH.search(name) else " ".join(filter(None, [name, dosage]))
            title = title.strip()
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

    def _open_draft(
        self, patient_id: UUID, care_plan_id: UUID, source_watermark: str
    ) -> dict[str, Any]:
        existing = (
            self.db.table("care_plan_versions")
            .select("*")
            .eq("care_plan_id", str(care_plan_id))
            .eq("status", "draft")
            .limit(1)
            .execute()
        )
        rows = cast(list[dict[str, Any]], existing.data or [])
        if rows:
            return rows[0]
        latest = self._versions(care_plan_id)
        version = int(latest[0]["version_number"]) + 1 if latest else 1
        created = (
            self.db.table("care_plan_versions")
            .insert(
                {
                    "patient_id": str(patient_id),
                    "care_plan_id": str(care_plan_id),
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
                # Preserve exclusions for these exact source facts. Otherwise a
                # new document makes generation resurrect already-rejected
                # proposals; genuinely new facts still need fresh review.
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
                        "source_locale",
                        "wording",
                        "wording_origin",
                    }
                }
                if (
                    not item.get("is_removed")
                    and item.get("projection_type") == "medication"
                    and item.get("projection_id")
                ):
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
        if (conflict or {}).get("kind") == "medication_stop_source":
            # Not confirmable: confirming would publish "stop this medicine" as a reminder
            # to take it. The clinician updates the medication list and removes the line.
            return _STOP_SOURCE_BLOCKER
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
        if (conflict or {}).get("kind") == "medication_stopped":
            return (
                "A source document says to stop or hold this medication. Confirm it should "
                "continue, or remove it, before approval."
            )
        if (conflict or {}).get("kind") == "medication_changed":
            return (
                "The document changes this medication. Enter the new dose and instructions, "
                "then confirm, before approval."
            )
        if conflict:
            return "Resolve conflicting medication instructions before approval."
        if confidence is None or float(confidence) < _LOW_CONFIDENCE:
            return "Confirm this low-confidence source extraction before approval."
        return None

    def _versions(self, care_plan_id: UUID) -> list[dict[str, Any]]:
        """Every version of ONE plan, newest first."""
        result = (
            self.db.table("care_plan_versions")
            .select("*")
            .eq("care_plan_id", str(care_plan_id))
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
                .select("id, fact_type, value, display_locale")
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
                    .select("id, file_name, display_title, uploaded_by_role, review_status")
                    .in_("id", document_ids)
                    .execute()
                    .data
                    or [],
                )
                if document_ids
                else []
            )
            document_names = {str(row["id"]): row["file_name"] for row in documents}
            document_reviews = {str(row["id"]): row for row in documents}
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
                            "display_title": document_reviews.get(str(document_id), {}).get(
                                "display_title"
                            ),
                            "upload_review_status": (
                                document_reviews.get(str(document_id), {}).get("review_status")
                                or "pending"
                                if document_reviews.get(str(document_id), {}).get(
                                    "uploaded_by_role"
                                )
                                == "patient"
                                else None
                            ),
                            "excerpt": excerpt,
                            "location": location,
                        }
                    )
        # DV-004: the strip and "Translated from Spanish" marker describe the SOURCE EVIDENCE
        # language, which is the fact's language, not the item's authored-wording source_locale.
        facts_by_id = {str(fact["id"]): fact for fact in facts}
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
                    "source_evidence_locale": self._source_evidence_locale(
                        facts_by_id.get(str(item.get("source_fact_id")))
                    ),
                }
                for item in items
            ],
        }

    @staticmethod
    def _source_evidence_locale(fact: dict[str, Any] | None) -> str | None:
        """Language of an item's source evidence (DV-004), or None when unknown."""
        if not fact:
            return None
        return detected_fact_locale(
            cast(dict[str, Any], fact.get("value") or {}),
            str(fact.get("fact_type") or ""),
            fact.get("display_locale"),
        )

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
