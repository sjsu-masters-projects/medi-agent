"""Explicit clinician lookup of public references; never reconciles clinical records."""

import asyncio
import re
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from postgrest.exceptions import APIError
from supabase import Client

from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.models.medication_reference import MedicationReferenceRead, MedicationReferenceSource
from app.services.clinic_membership_service import ClinicMembershipService
from app.services.clinical_fact_service import ClinicalFactService
from app.services.health_knowledge_service import HealthKnowledgeService, Reference


class MedicationReferenceService:
    def __init__(self, db: Client) -> None:
        self.db = db
        self.memberships = ClinicMembershipService(self)
        self.facts = ClinicalFactService(db)
        self.knowledge = HealthKnowledgeService(db)

    async def get_reference(
        self, clinician_id: UUID, *, patient_id: UUID, fact_id: UUID
    ) -> MedicationReferenceRead:
        scope = await self.memberships.link_scope(clinician_id)
        if str(patient_id) not in scope:
            raise AuthorizationError("You are not assigned to this patient")
        try:
            fact = await asyncio.to_thread(self.facts.get_fact, fact_id, patient_id)
        except APIError as exc:
            if exc.code == "PGRST116":
                raise NotFoundError("Clinical fact", str(fact_id)) from None
            raise
        if str(fact.get("patient_id")) != str(patient_id) or str(fact.get("id")) != str(fact_id):
            raise NotFoundError("Clinical fact", str(fact_id))
        if fact.get("fact_type") != "medication" or fact.get("review_state") == "deleted":
            raise ValidationError("Medication reference requires an available medication candidate")
        value = fact.get("value")
        name = value.get("name") if isinstance(value, dict) else None
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            raise ValidationError(
                "Medication candidate needs a recorded name of at most 200 characters"
            )
        result = MedicationReferenceRead(
            fact_id=fact_id, status="unavailable", retrieved_at=datetime.now(UTC)
        )
        try:
            knowledge = await self.knowledge.medication(name.strip())
        except Exception:
            # Provider/cache errors are an explicit unavailable result, never a safety verdict.
            result.retrieved_at = datetime.now(UTC)
            return result
        result.retrieved_at = datetime.now(UTC)
        result.status = knowledge.status
        result.subject = knowledge.subject[:200] if knowledge.subject else None
        result.rxcui = (
            knowledge.rxcui
            if knowledge.rxcui and re.fullmatch(r"[0-9]{1,20}", knowledge.rxcui)
            else None
        )
        result.references = [item for ref in knowledge.references[:3] if (item := _reference(ref))]
        if result.status == "found" and not result.references:
            result.status = "unavailable"
        return result


def _reference(ref: Reference) -> MedicationReferenceSource | None:
    url = _official_url(ref.source, ref.url)
    if not url or ref.locale not in {"en-US", "es-MX"} or ref.checked_at.tzinfo is None:
        return None
    return MedicationReferenceSource(
        source=ref.source,  # type: ignore[arg-type]
        locale=ref.locale,  # type: ignore[arg-type]
        title=ref.title[:240],
        url=url,
        summary=ref.summary[:1200],
        source_version=ref.source_version[:80] if ref.source_version else None,
        source_updated=ref.source_updated_on,
        checked_at=ref.checked_at,
        stale=ref.stale,
    )


def _official_url(source: str, url: str | None) -> str | None:
    if not url or len(url) > 2048 or re.search(r"[\s\\\x00-\x1f\x7f]", url):
        return None
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.username
            or parsed.password
            or parsed.port is not None
        ):
            return None
        if source == "medlineplus" and parsed.netloc == "medlineplus.gov":
            if (
                parsed.query
                or parsed.fragment
                or not re.fullmatch(
                    r"/(?:spanish/)?druginfo/(?:meds|natural)/[a-zA-Z0-9-]+\.html", parsed.path
                )
            ):
                return None
            return url
        if (
            source == "dailymed"
            and parsed.netloc == "dailymed.nlm.nih.gov"
            and parsed.path == "/dailymed/drugInfo.cfm"
            and not parsed.fragment
        ):
            query = parse_qs(parsed.query)
            if set(query) == {"setid"} and len(query["setid"]) == 1:
                return f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={UUID(query['setid'][0])}"
    except ValueError:
        return None
    return None
