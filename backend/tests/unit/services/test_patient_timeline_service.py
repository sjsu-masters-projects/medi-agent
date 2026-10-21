"""Synthetic timeline access, source identity, dates, bounds and failure contracts."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.exception_handlers import register_exception_handlers
from app.core.exceptions import AuthorizationError
from app.core.security import get_current_user
from app.models.auth import CurrentUser
from app.models.dashboard import PatientTimelineResponse
from app.routers import clinicians
from app.services.clinician_service import ClinicianService
from app.services.patient_timeline_service import (
    CONVERSATION_LIMIT,
    SOURCE_LIMIT,
    SOURCES,
    PatientTimelineService,
)


class Query:
    def __init__(self, db, table):
        self.db, self.table = db, table
        self.calls = []

    def __getattr__(self, name):
        if name == "not_":
            return self

        def method(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return self

        return method

    def execute(self):
        value = self.db.rows.get(self.table, [])
        if isinstance(value, Exception):
            raise value
        if self.table == "documents" and any(
            call[0] == "order" and call[1][0] == "reviewed_at" for call in self.calls
        ):
            value = [row for row in value if row.get("reviewed_at")]
        return SimpleNamespace(data=value)


class Database:
    def __init__(self, rows=None, threads=None):
        self.rows = rows or {}
        self.threads = threads or {}
        self.queries = []
        self.rpc_calls = []

    def table(self, name):
        query = Query(self, name)
        self.queries.append(query)
        return query

    def rpc(self, name, arguments):
        self.rpc_calls.append((name, arguments))
        thread = arguments["p_payload"]["conversation_id"]
        result = self.threads[thread]
        if isinstance(result, Exception):
            raise result
        return SimpleNamespace(execute=lambda: SimpleNamespace(data={"items": result}))


def row(**values):
    return {"id": str(uuid4()), "created_at": "2026-10-01T10:00:00+00:00", **values}


@pytest.mark.asyncio
async def test_assignment_denial_precedes_all_source_queries():
    db = Database()
    authorize = AsyncMock(side_effect=AuthorizationError("Not assigned"))
    with pytest.raises(AuthorizationError):
        await PatientTimelineService(db, authorize).get_timeline(uuid4(), uuid4())
    assert db.queries == []
    assert db.rpc_calls == []


@pytest.mark.asyncio
async def test_cross_domain_events_use_real_dates_and_exact_source_links():
    patient, clinician, thread = uuid4(), uuid4(), uuid4()
    symptom = row(symptom="Synthetic cough", confirmation_state="patient_confirmed")
    message = row(
        sender_role="patient",
        sender_name="Private sender name",
        body="Must not leak",
        private_reasoning="secret",
    )
    doc = row(
        file_name="synthetic.pdf", reviewed_at="2026-10-03T09:00:00Z", review_status="approved"
    )
    medication = row(name="Synthetic medication", start_date="2026-09-01")
    log = row(logged_at="2026-10-05T08:00:00Z", target_id=str(uuid4()), status="taken")
    appointment = row(scheduled_at="2026-11-01T08:00:00Z")
    audit = row(
        event_type="approved", plan_version_id=str(uuid4()), event_data={"reasoning": "secret"}
    )
    db = Database(
        {
            "documents": [doc],
            "medications": [medication],
            "symptom_reports": [symptom],
            "adherence_logs": [log],
            "appointments": [appointment],
            "care_plan_audit_events": [audit],
            "care_conversations": [{"id": str(thread)}],
        },
        {str(thread): [message]},
    )
    authorize = AsyncMock()
    result = await PatientTimelineService(db, authorize).get_timeline(clinician, patient)
    authorize.assert_awaited_once_with(clinician, patient)
    assert {event.domain for event in result.events} == {
        "document",
        "medication",
        "symptom",
        "adherence",
        "message",
        "appointment",
        "approval",
    }
    assert result.events[0].occurred_at.isoformat() == "2026-10-05T08:00:00+00:00"
    by_id = {str(event.source_id): event for event in result.events}
    assert by_id[appointment["id"]].occurred_at.month == 10  # Recorded, not visit date.
    assert (
        by_id[appointment["id"]].destination_href
        == f"/appointments?appointmentId={appointment['id']}"
    )
    assert by_id[medication["id"]].occurred_at.month == 10  # Not inferred from start_date.
    assert (
        by_id[doc["id"]].destination_href
        == f"/patients/{patient}?tab=documents#document-{doc['id']}"
    )
    assert (
        by_id[symptom["id"]].destination_href
        == f"/patients/{patient}?tab=symptoms#symptom-{symptom['id']}"
    )
    assert by_id[message["id"]].destination_href == f"/messages?conversation={thread}"
    for event in result.events:
        assert event.source_href == f"/patients/{patient}?tab=timeline#source-{event.id}"
    assert "Must not leak" not in result.model_dump_json()
    assert "Private sender name" not in result.model_dump_json()
    assert "target_id" not in by_id[log["id"]].details
    assert "secret" not in result.model_dump_json()
    for query in db.queries:
        assert (
            "limit",
            (SOURCE_LIMIT + 1,),
            {},
        ) in query.calls or query.table == "care_conversations"
        if query.table != "care_conversations":
            selected = next(call[1][0] for call in query.calls if call[0] == "select")
            assert "event_data" not in selected and "body" not in selected


@pytest.mark.asyncio
async def test_private_message_discovery_is_actor_scoped_and_rpc_rechecks_each_thread():
    patient, actor, thread = uuid4(), uuid4(), uuid4()
    db = Database({"care_conversations": [{"id": str(thread)}]}, {str(thread): [row()]})
    await PatientTimelineService(db, AsyncMock()).get_timeline(actor, patient)
    discovery = next(query for query in db.queries if query.table == "care_conversations")
    assert ("eq", ("clinician_id", str(actor)), {}) in discovery.calls
    assert ("eq", ("patient_id", str(patient)), {}) in discovery.calls
    assert db.rpc_calls == [
        (
            "care_conversation_operation",
            {
                "p_actor_id": str(actor),
                "p_actor_role": "clinician",
                "p_action": "messages",
                "p_payload": {"conversation_id": str(thread), "limit": SOURCE_LIMIT + 1},
            },
        )
    ]
    assert not any(query.table == "care_conversation_messages" for query in db.queries)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    ["inactive clinic", "revoked membership", "changed assignment", "foreign conversation"],
)
async def test_thread_authorization_failure_is_unavailable_not_empty_or_partial(failure):
    thread = uuid4()
    db = Database(
        {"care_conversations": [{"id": str(thread)}]}, {str(thread): PermissionError(failure)}
    )
    result = await PatientTimelineService(db, AsyncMock()).get_timeline(uuid4(), uuid4())
    source = next(
        source
        for source in result.sources
        if source.source.startswith("care_conversation_messages")
    )
    assert source.status == "unavailable"
    assert source.has_more is None
    assert not any(event.domain == "message" for event in result.events)


@pytest.mark.asyncio
async def test_bounds_missing_dates_and_partial_failure_are_disclosed():
    db = Database(
        {
            "medications": [row() for _ in range(SOURCE_LIMIT + 1)],
            "symptom_reports": [
                row(created_at=None),
                row(created_at="invalid"),
                row(created_at="2026-01-01T00:00:00"),
            ],
            "documents": RuntimeError("sensitive upstream failure"),
        }
    )
    result = await PatientTimelineService(db, AsyncMock()).get_timeline(uuid4(), uuid4())
    coverage = {source.source: source for source in result.sources}
    assert coverage["medications.created_at"].returned == SOURCE_LIMIT
    assert coverage["medications.created_at"].has_more is True
    assert coverage["symptom_reports.created_at"].omitted_invalid == 3
    assert coverage["documents.created_at"].status == "unavailable"
    assert "sensitive" not in result.model_dump_json()
    assert len(result.events) == SOURCE_LIMIT


@pytest.mark.asyncio
async def test_conversation_cap_disclosed_and_never_queries_extra_threads():
    threads = [{"id": str(uuid4())} for _ in range(CONVERSATION_LIMIT + 1)]
    db = Database({"care_conversations": threads}, {thread["id"]: [] for thread in threads})
    result = await PatientTimelineService(db, AsyncMock()).get_timeline(uuid4(), uuid4())
    source = next(source for source in result.sources if source.conversation_limit)
    assert source.conversations_truncated is True
    assert source.has_more is True
    assert len(db.rpc_calls) == CONVERSATION_LIMIT


@pytest.mark.asyncio
async def test_joined_audit_queries_always_filter_patient_and_confirmed_symptoms():
    db = Database()
    patient = uuid4()
    await PatientTimelineService(db, AsyncMock()).get_timeline(uuid4(), patient)
    for source in SOURCES:
        if source.domain == "message":
            continue
        query = next(query for query in db.queries if query.table == source.table)
        scope = f"{source.parent}.patient_id" if source.parent else "patient_id"
        assert ("eq", (scope, str(patient)), {}) in query.calls
        if source.parent:
            assert f"{source.parent}!inner(patient_id)" in query.calls[0][1][0]
        if source.domain == "symptom":
            assert ("eq", ("confirmation_state", "patient_confirmed"), {}) in query.calls


@pytest.mark.asyncio
async def test_clinician_wrapper_checks_assignment_before_timeline_sources():
    db = MagicMock()
    service = ClinicianService(db)
    service._assert_patient_assignment = AsyncMock(side_effect=AuthorizationError("Denied"))
    with pytest.raises(AuthorizationError):
        await service.get_patient_timeline(uuid4(), uuid4())
    db.table.assert_not_called()


def test_timeline_route_delegates_actor_and_patient_with_response_schema():
    patient, actor = uuid4(), uuid4()
    app = FastAPI()
    app.include_router(clinicians.router)
    service = SimpleNamespace(
        get_patient_timeline=AsyncMock(
            return_value=PatientTimelineResponse(
                patient_id=patient, retrieved_at="2026-10-21T12:00:00Z", events=[], sources=[]
            )
        )
    )
    app.dependency_overrides[clinicians._clinician_dep] = lambda: SimpleNamespace(id=actor)
    app.dependency_overrides[clinicians._get_service] = lambda: service
    with TestClient(app) as client:
        response = client.get(f"/me/patients/{patient}/timeline")
        assert response.status_code == 200
        assert response.json()["patient_id"] == str(patient)
        assert client.get("/me/patients/not-a-uuid/timeline").status_code == 422
    service.get_patient_timeline.assert_awaited_once_with(actor, patient)


def test_timeline_api_rejects_patient_role_before_service_or_source_queries(monkeypatch):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(clinicians.router)
    monkeypatch.setattr("app.core.exception_handlers.record_denial", AsyncMock())
    service = SimpleNamespace(get_patient_timeline=AsyncMock())
    app.dependency_overrides[clinicians._get_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=uuid4(), email="synthetic@synthetic.invalid", role="patient"
    )
    with TestClient(app) as client:
        response = client.get(f"/me/patients/{uuid4()}/timeline")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AUTHORIZATION_ERROR"
    service.get_patient_timeline.assert_not_awaited()


def test_timeline_api_assignment_denial_precedes_source_queries(monkeypatch):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(clinicians.router)
    monkeypatch.setattr("app.core.exception_handlers.record_denial", AsyncMock())
    db = MagicMock()
    service = ClinicianService(db)
    service._assert_patient_assignment = AsyncMock(side_effect=AuthorizationError("Not assigned"))
    app.dependency_overrides[clinicians._get_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=uuid4(), email="synthetic@synthetic.invalid", role="clinician", aal="aal2"
    )
    with TestClient(app) as client:
        response = client.get(f"/me/patients/{uuid4()}/timeline")
    assert response.status_code == 403
    db.table.assert_not_called()
    db.rpc.assert_not_called()
