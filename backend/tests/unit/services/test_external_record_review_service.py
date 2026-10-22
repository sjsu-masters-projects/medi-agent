"""External review workload: assignment scope, metadata-only reads and coverage."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from postgrest import SyncPostgrestClient

from app.core.exception_handlers import register_exception_handlers
from app.core.exceptions import ExternalServiceError
from app.core.security import get_current_user
from app.db.connection import get_db
from app.models.auth import CurrentUser
from app.routers import clinicians
from app.services.care_team_access import ClinicianAccess, PatientAccess
from app.services.clinic_link_scope import ClinicLinkScope
from app.services.external_record_review_service import (
    CANDIDATE_LIMIT,
    CITATION_LIMIT,
    PAGE_SIZE,
    ExternalRecordReviewService,
)


class Query:
    def __init__(self, db, table):
        self.db, self.table = db, table
        self.calls = []

    def __getattr__(self, name):
        def apply(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return self

        return apply

    def execute(self):
        if self.db.error:
            raise self.db.error
        if self.table == "patients":
            return SimpleNamespace(data=self.db.names)
        patient = next(
            args[1] for name, args, _ in self.calls if name == "eq" and args[0] == "patient_id"
        )
        value, count = self.db.facts.get(patient, ([], 0))
        return SimpleNamespace(data=value, count=count)


class Database:
    def __init__(self):
        self.facts, self.names, self.queries = {}, [], []
        self.error = None

    def table(self, name):
        query = Query(self, name)
        self.queries.append(query)
        return query


def candidate(time="2026-10-01T12:00:00Z"):
    return {
        "id": str(uuid4()),
        "evidence_citations": [
            {
                "source_provenances": {
                    "artifact_type": "fhir_resource",
                    "captured_at": time,
                    "withdrawn_at": None,
                },
            }
        ],
    }


def admit_everything(service, patients=()):
    """Every source is visible to the caller; ownership has its own tests."""
    service.access = MagicMock()
    service.access.for_clinician.return_value = ClinicianAccess(
        "clinician", {str(patient): frozenset({"team"}) for patient in patients}
    )
    service.access.visible_fact_ids.side_effect = lambda _access, ids: {str(i) for i in ids}
    return service


def service_with_scope(db, patients):
    service = ExternalRecordReviewService(db)
    service.memberships.link_scope = AsyncMock(return_value=ClinicLinkScope(patients))
    return admit_everything(service, patients)


@pytest.mark.asyncio
async def test_empty_or_unauthorized_scope_does_not_read_sources():
    db = Database()
    clinician, clinic = uuid4(), uuid4()
    service = service_with_scope(db, {})
    result = await service.list_reviews(clinician, clinic_id=clinic)
    service.memberships.link_scope.assert_awaited_once_with(clinician, clinic)
    assert result.items == [] and result.assigned_patients == 0
    assert not db.queries


@pytest.mark.asyncio
async def test_groups_current_scope_with_exact_counts_real_capture_time_and_no_private_payload():
    db = Database()
    patient, foreign, clinic, actor = (uuid4() for _ in range(4))
    db.names = [{"id": str(patient), "first_name": "Synthetic", "last_name": "Patient"}]
    db.facts[str(patient)] = ([candidate("2026-10-11T12:00:00Z"), candidate()], 2)
    db.facts[str(foreign)] = ([candidate()], 99)
    service = service_with_scope(db, {str(patient): (str(clinic), "Linked clinic")})
    result = await service.list_reviews(actor, clinic_id=clinic)
    item = result.items[0]
    assert item.pending_count == 2
    assert item.oldest_source_captured_at.isoformat() == "2026-10-01T12:00:00+00:00"
    assert item.source_times_complete
    assert item.patient_name == "Synthetic Patient" and item.clinic_id == str(clinic)
    assert item.patient_id == patient
    assert len(result.items) == 1 and result.retrieved_at > item.oldest_source_captured_at
    query = next(query for query in db.queries if query.table == "clinical_facts")
    assert ("eq", ("patient_id", str(patient)), {}) in query.calls
    assert ("eq", ("review_state", "pending_review"), {}) in query.calls
    assert ("in_", ("reconciliation_state", ["not_started", "deferred"]), {}) in query.calls
    assert (
        "in_",
        (
            "evidence_citations.source_provenances.artifact_type",
            ["document", "fhir_resource", "external_record"],
        ),
        {},
    ) in query.calls
    assert (
        "is_",
        ("evidence_citations.source_provenances.withdrawn_at", "null"),
        {},
    ) in query.calls
    selection = query.calls[0]
    assert selection[2] == {"count": "exact"}
    assert "!inner" in selection[1][0]
    assert all(
        field not in selection[1][0] for field in ("value", "excerpt", "review_note", "actor_id")
    )
    assert ("limit", (CANDIDATE_LIMIT,), {}) in query.calls
    assert ("limit", (CITATION_LIMIT,), {"foreign_table": "evidence_citations"}) in query.calls


@pytest.mark.asyncio
async def test_real_membership_link_scope_excludes_foreign_clinic_before_any_source_query():
    db = Database()
    actor, patient, own, foreign = (uuid4() for _ in range(4))
    service = admit_everything(ExternalRecordReviewService(db))
    links = [
        {
            "patient_id": str(patient),
            "clinic_id": str(own),
            "clinics": {"display_name": "Own clinic"},
        }
    ]
    with patch(
        "app.services.clinic_membership_service.CareTeamRepository.list_active_links",
        AsyncMock(return_value=links),
    ) as lookup:
        service.memberships.active_memberships = AsyncMock(
            return_value=[SimpleNamespace(clinic_id=own)]
        )
        result = await service.list_reviews(actor, clinic_id=foreign)
    lookup.assert_awaited_once_with(str(actor))
    assert result.items == []
    assert not db.queries


@pytest.mark.asyncio
async def test_assignment_pagination_and_zero_pending_patients_are_explicit():
    db = Database()
    ids = sorted(str(uuid4()) for _ in range(PAGE_SIZE + 2))
    service = service_with_scope(db, {key: (None, None) for key in ids})
    first = await service.list_reviews(uuid4())
    assert first.items == [] and first.has_more
    assert first.patients_examined == PAGE_SIZE and first.assigned_patients == PAGE_SIZE + 2
    second = await service.list_reviews(uuid4(), page=2)
    assert second.patients_examined == 2 and not second.has_more
    queries = [query for query in db.queries if query.table == "clinical_facts"]
    queried = [
        next(
            args[1] for method, args, _ in query.calls if method == "eq" and args[0] == "patient_id"
        )
        for query in queries
    ]
    assert queried == ids


@pytest.mark.asyncio
@pytest.mark.parametrize("problem", ["truncated", "missing", "invalid", "citations"])
async def test_incomplete_source_time_is_disclosed_not_invented(problem):
    db, patient = Database(), str(uuid4())
    row = candidate(
        None
        if problem == "missing"
        else "invalid"
        if problem == "invalid"
        else "2026-10-01T12:00:00Z"
    )
    if problem == "citations":
        row["evidence_citations"] *= CITATION_LIMIT
    db.facts[patient] = ([row], 300 if problem == "truncated" else 1)
    result = await service_with_scope(db, {patient: (None, None)}).list_reviews(uuid4())
    assert not result.items[0].source_times_complete
    if problem in {"missing", "invalid"}:
        assert result.items[0].oldest_source_captured_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["query", "count"])
async def test_errors_never_become_zero_work(failure):
    db, patient = Database(), str(uuid4())
    if failure == "query":
        db.error = RuntimeError("Database unavailable")
    else:
        db.facts[patient] = ([], None)
    with pytest.raises(ExternalServiceError):
        await service_with_scope(db, {patient: (None, None)}).list_reviews(uuid4())


def test_route_role_and_scope_validation():
    app = FastAPI()
    app.include_router(clinicians.router, prefix="/api/v1/clinicians")
    register_exception_handlers(app)
    actor = uuid4()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=actor, email="synthetic@example.invalid", role="patient"
    )
    app.dependency_overrides[get_db] = Database
    client = TestClient(app)
    endpoint = "/api/v1/clinicians/me/external-record-reviews"
    assert client.get(endpoint).status_code == 403
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=actor, email="synthetic@example.invalid", role="clinician", aal="aal2"
    )
    assert client.get(endpoint + "?page=0").status_code == 422
    assert client.get(endpoint + "?clinic_id=bad").status_code == 422
    with patch.object(
        ExternalRecordReviewService,
        "list_reviews",
        AsyncMock(
            return_value={
                "items": [],
                "retrieved_at": "2026-10-21T12:00:00Z",
                "page": 2,
                "page_size": PAGE_SIZE,
                "assigned_patients": 11,
                "patients_examined": 1,
                "has_more": False,
                "candidate_limit": CANDIDATE_LIMIT,
                "citation_limit": CITATION_LIMIT,
            }
        ),
    ) as read:
        clinic = uuid4()
        assert client.get(endpoint + f"?clinic_id={clinic}&page=2").status_code == 200
        read.assert_awaited_once_with(actor, clinic_id=clinic, page=2)


@pytest.mark.asyncio
async def test_installed_postgrest_client_emits_nested_filters_and_parses_exact_parent_count():
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            206, json=[candidate() for _ in range(39)], headers={"Content-Range": "0-38/39"}
        )

    with (
        httpx.Client(transport=httpx.MockTransport(respond)) as http,
        SyncPostgrestClient("https://synthetic.invalid/rest/v1", http_client=http) as db,
    ):
        service = admit_everything(ExternalRecordReviewService(db))
        result = await service._patient(str(uuid4()), PatientAccess("c", "p", frozenset({"t"})))
    assert result["pending_count"] == 39
    assert result["inspected_candidates"] == 39
    assert result["source_times_complete"]
    request = requests[0]
    assert request.method == "GET"
    assert request.url.path == "/rest/v1/clinical_facts"
    assert request.headers["prefer"] == "count=exact"
    params = request.url.params
    assert (
        params["select"]
        == "id,evidence_citations!inner(source_provenances!inner(artifact_type,captured_at,withdrawn_at))"
    )
    assert params["review_state"] == "eq.pending_review"
    assert params["reconciliation_state"] == "in.(not_started,deferred)"
    assert (
        params["evidence_citations.source_provenances.artifact_type"]
        == "in.(document,fhir_resource,external_record)"
    )
    assert params["evidence_citations.source_provenances.withdrawn_at"] == "is.null"
    assert params["limit"] == "200"
    assert params["evidence_citations.limit"] == "20"
    assert params["order"] == "created_at.asc,id.asc"
