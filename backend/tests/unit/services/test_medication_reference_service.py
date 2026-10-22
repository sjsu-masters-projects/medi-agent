"""Public references are bounded, authorized and separate from clinical truth."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import urlunsplit
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

from app.core.exception_handlers import register_exception_handlers
from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.core.security import get_current_user
from app.models.auth import CurrentUser
from app.routers import smart
from app.services.health_knowledge_service import Knowledge, Reference
from app.services.medication_reference_service import MedicationReferenceService, _official_url


def reference(**values):
    return Reference(
        **{
            "source": "medlineplus",
            "locale": "en-US",
            "title": "Metformin",
            "url": "https://medlineplus.gov/druginfo/meds/a696005.html",
            "summary": "Public text",
            "sections": {"private": "Excluded"},
            "source_version": "version-1",
            "source_updated_on": date(2026, 10, 1),
            "checked_at": datetime(2026, 10, 2, tzinfo=UTC),
            "stale": True,
            **values,
        }
    )


@pytest.fixture
def setup():
    actor, patient, fact = uuid4(), uuid4(), uuid4()
    service = MedicationReferenceService(MagicMock())
    service.memberships.link_scope = AsyncMock(return_value={str(patient)})
    service.facts.get_fact = MagicMock(
        return_value={
            "id": str(fact),
            "patient_id": str(patient),
            "fact_type": "medication",
            "review_state": "pending_review",
            "value": {"name": "Metformin", "rxcui": "original"},
        }
    )
    service.knowledge.medication = AsyncMock(
        return_value=Knowledge(
            status="found",
            subject="metformin",
            rxcui="6809",
            references=[reference()],
        )
    )
    return service, actor, patient, fact


@pytest.mark.asyncio
async def test_authorized_name_only_lookup_preserves_source_dates_and_never_writes(setup):
    service, actor, patient, fact = setup
    result = await service.get_reference(actor, patient_id=patient, fact_id=fact)
    service.facts.get_fact.assert_called_once_with(fact, patient)
    service.knowledge.medication.assert_awaited_once_with("Metformin")
    assert result.status == "found" and result.rxcui == "6809"
    assert result.references[0].source_updated.isoformat() == "2026-10-01"
    assert result.references[0].checked_at == datetime(2026, 10, 2, tzinfo=UTC)
    assert result.references[0].stale is True
    assert "Excluded" not in result.model_dump_json()
    assert service.facts.get_fact.return_value["value"]["rxcui"] == "original"
    service.db.table.assert_not_called()


@pytest.mark.asyncio
async def test_english_clinician_references_first_without_dropping_spanish(setup):
    service, actor, patient, fact = setup
    spanish = reference(
        locale="es-MX",
        title="Referencia",
        url="https://medlineplus.gov/spanish/druginfo/meds/a696005.html",
    )
    english = reference()
    service.knowledge.medication.return_value = Knowledge(
        status="found", references=[spanish, english]
    )
    result = await service.get_reference(actor, patient_id=patient, fact_id=fact)
    assert [item.locale for item in result.references] == ["en-US", "es-MX"]
    assert result.references[1].title == spanish.title
    assert result.references[1].checked_at == spanish.checked_at
    service.db.table.assert_not_called()


@pytest.mark.asyncio
async def test_assignment_denial_precedes_fact_and_external_lookup(setup):
    service, actor, patient, fact = setup
    service.memberships.link_scope.return_value = set()
    with pytest.raises(AuthorizationError):
        await service.get_reference(actor, patient_id=patient, fact_id=fact)
    service.facts.get_fact.assert_not_called()
    service.knowledge.medication.assert_not_awaited()


@pytest.mark.asyncio
async def test_foreign_fact_single_row_transport_error_is_not_found(setup):
    service, actor, patient, fact = setup
    service.facts.get_fact.side_effect = APIError({"code": "PGRST116", "message": "No row"})
    with pytest.raises(NotFoundError):
        await service.get_reference(actor, patient_id=patient, fact_id=fact)
    service.knowledge.medication.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", ["patient_id", "id", "fact_type", "review_state", "name", "missing", "long"]
)
async def test_foreign_or_invalid_candidate_never_calls_public_service(setup, change):
    service, actor, patient, fact = setup
    row = service.facts.get_fact.return_value
    if change in {"patient_id", "id"}:
        row[change] = str(uuid4())
    elif change == "fact_type":
        row[change] = "condition"
    elif change == "review_state":
        row[change] = "deleted"
    else:
        row["value"] = (
            {"name": {"unsafe": True}}
            if change == "name"
            else {}
            if change == "missing"
            else {"name": "x" * 201}
        )
    with pytest.raises((NotFoundError, ValidationError)):
        await service.get_reference(actor, patient_id=patient, fact_id=fact)
    service.knowledge.medication.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_patient_fact_query_is_filtered_by_both_identifiers(setup):
    service, actor, patient, fact = setup
    from app.services.clinical_fact_service import ClinicalFactService

    service.facts = ClinicalFactService(service.db)
    query = MagicMock()
    service.db.table.return_value = query
    query.select.return_value = query
    query.eq.return_value = query
    query.single.return_value = query
    query.execute.return_value = SimpleNamespace(data=None)
    with pytest.raises(NotFoundError):
        await service.get_reference(actor, patient_id=patient, fact_id=fact)
    query.eq.assert_any_call("id", str(fact))
    query.eq.assert_any_call("patient_id", str(patient))
    service.knowledge.medication.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["not_found", "unavailable"])
async def test_missing_and_unavailable_results_are_explicit(setup, status):
    service, actor, patient, fact = setup
    service.knowledge.medication.return_value = Knowledge(status=status)
    result = await service.get_reference(actor, patient_id=patient, fact_id=fact)
    assert result.status == status and not result.references
    assert result.rxcui is None and result.subject is None


@pytest.mark.asyncio
async def test_provider_error_is_unavailable_and_does_not_echo_private_error(setup):
    service, actor, patient, fact = setup
    service.knowledge.medication.side_effect = RuntimeError("private upstream detail")
    result = await service.get_reference(actor, patient_id=patient, fact_id=fact)
    assert result.status == "unavailable"
    assert "private" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_returned_references_and_text_are_bounded(setup):
    service, actor, patient, fact = setup
    service.knowledge.medication.return_value = Knowledge(
        status="found",
        subject="s" * 500,
        rxcui="javascript:unsafe",
        references=[reference(title="t" * 500, summary="x" * 5000, source_version="v" * 500)] * 20,
    )
    result = await service.get_reference(actor, patient_id=patient, fact_id=fact)
    assert len(result.references) == 3
    assert len(result.subject) == 200 and result.rxcui is None
    assert len(result.references[0].title) == 240
    assert len(result.references[0].summary) == 1200
    assert len(result.references[0].source_version) == 80


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "http://medlineplus.gov/druginfo/meds/a1.html",
        "https://medlineplus.gov.evil.test/druginfo/meds/a1.html",
        "https://evil.test/",
        # Build synthetic userinfo at runtime so a deliberately invalid fixture
        # is not mistaken for a committed live credential by history scanning.
        urlunsplit(
            (
                "https",
                "fixture-user:fixture-password@medlineplus.gov",
                "/druginfo/meds/a1.html",
                "",
                "",
            )
        ),
        "https://medlineplus.gov:443/druginfo/meds/a1.html",
        "https://medlineplus.gov/druginfo/meds/a1.html?redirect=https://evil.test",
        "https://medlineplus.gov/druginfo/meds/a1.html\n",
        "https://medlineplus.gov\\evil.test/",
    ],
)
def test_only_official_https_reference_links_are_exposed(url):
    assert _official_url("medlineplus", url) is None


@pytest.mark.asyncio
async def test_unsafe_reference_or_undated_source_cannot_be_reported_as_found(setup):
    service, actor, patient, fact = setup
    service.knowledge.medication.return_value = Knowledge(
        status="found",
        references=[
            reference(url="https://evil.test/"),
            reference(checked_at=datetime(2026, 10, 1)),
        ],
    )
    result = await service.get_reference(actor, patient_id=patient, fact_id=fact)
    assert result.status == "unavailable" and result.references == []


def test_official_daily_med_and_spanish_medlineplus_urls():
    label = f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={uuid4()}"
    assert _official_url("dailymed", label) == label
    spanish = "https://medlineplus.gov/spanish/druginfo/meds/a696005.html"
    assert _official_url("medlineplus", spanish) == spanish
    assert _official_url("dailymed", spanish) is None


@pytest.mark.parametrize(
    "role,assigned,expected",
    [("patient", True, 403), ("clinician", False, 403), ("clinician", True, 200)],
)
def test_reference_route_uses_real_role_and_assignment_gate(
    setup, monkeypatch, role, assigned, expected
):
    service, actor, patient, fact = setup
    if not assigned:
        service.memberships.link_scope.return_value = set()
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(smart.router, prefix="/smart")
    monkeypatch.setattr("app.core.exception_handlers.record_denial", AsyncMock())
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=actor, email="synthetic@synthetic.invalid", role=role, aal="aal2"
    )
    app.dependency_overrides[smart._medication_reference_service] = lambda: service
    with TestClient(app) as client:
        response = client.get(f"/smart/patients/{patient}/facts/{fact}/medication-reference")
    assert response.status_code == expected
    if expected == 403:
        service.knowledge.medication.assert_not_awaited()
        service.facts.get_fact.assert_not_called()
    else:
        assert response.json()["fact_id"] == str(fact)
