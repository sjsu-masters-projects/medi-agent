"""Tests for the safe FHIR candidate reprojection workflow."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from app.services.fhir_candidate_reprojection_service import (
    MAPPER_VERSION,
    FhirCandidateReprojectionService,
)

PATIENT_ID = "00000000-0000-0000-0000-000000000111"
FACT_ID = "00000000-0000-0000-0000-000000000222"
RESOURCE_ID = "00000000-0000-0000-0000-000000000333"
PROVENANCE_ID = "00000000-0000-0000-0000-000000000444"
CONTENT_HASH = "a" * 64


class Result:
    def __init__(self, data: Any) -> None:
        self.data = data


class Table:
    def __init__(self, name: str, store: dict[str, list[dict[str, Any]]]) -> None:
        self.name = name
        self.store = store
        self.filters: list[tuple[str, set[str]]] = []

    def select(self, *_fields: str) -> Table:
        return self

    def eq(self, column: str, value: Any) -> Table:
        self.filters.append((column, {str(value)}))
        return self

    def in_(self, column: str, values: list[str]) -> Table:
        self.filters.append((column, {str(value) for value in values}))
        return self

    def execute(self) -> Result:
        return Result(
            [
                row
                for row in self.store.get(self.name, [])
                if all(str(row.get(column)) in accepted for column, accepted in self.filters)
            ]
        )


class Rpc:
    def __init__(
        self, name: str, params: dict[str, Any], calls: list[tuple[str, dict[str, Any]]]
    ) -> None:
        self.name = name
        self.params = params
        self.calls = calls

    def execute(self) -> Result:
        self.calls.append((self.name, self.params))
        return Result({"fact_id": self.params["p_fact_id"], "revision_id": str(uuid4())})


class Database:
    def __init__(self, store: dict[str, list[dict[str, Any]]]) -> None:
        self.store = store
        self.rpc_calls: list[tuple[str, dict[str, Any]]] = []

    def table(self, name: str) -> Table:
        return Table(name, self.store)

    def rpc(self, name: str, params: dict[str, Any]) -> Rpc:
        return Rpc(name, params, self.rpc_calls)


def _care_plan() -> dict[str, Any]:
    return {
        "resourceType": "CarePlan",
        "status": "completed",
        "intent": "order",
        "category": [{"coding": [{"display": "Fracture care"}]}],
        "text": {"div": "<div>Care plan for fracture care.</div>"},
        "period": {"start": "2016-01-03", "end": "2016-02-02"},
        "activity": [
            {
                "detail": {
                    "code": {"coding": [{"display": "Recommendation to rest"}]},
                    "status": "completed",
                }
            }
        ],
    }


def _database(*, touched: bool = False, use_content_hash_version: bool = False) -> Database:
    source_version = None if use_content_hash_version else "4"
    candidate_version = CONTENT_HASH if use_content_hash_version else "4"
    return Database(
        {
            "clinical_facts": [
                {
                    "id": FACT_ID,
                    "patient_id": PATIENT_ID,
                    "fact_type": "care_plan",
                    "value": {"title": None, "status": "completed", "intent": "order"},
                    "external_source_version": candidate_version,
                    "review_state": "pending_review",
                    "reconciliation_state": "not_started",
                }
            ],
            "clinical_fact_audit_events": [
                {"fact_id": FACT_ID, "event_type": "created"},
                *([{"fact_id": FACT_ID, "event_type": "corrected"}] if touched else []),
            ],
            "evidence_citations": [{"fact_id": FACT_ID, "provenance_id": PROVENANCE_ID}],
            "source_provenances": [
                {
                    "id": PROVENANCE_ID,
                    "source_reference": f"fhir_import_resources/{RESOURCE_ID}",
                }
            ],
            "fhir_import_resources": [
                {
                    "id": RESOURCE_ID,
                    "resource_type": "CarePlan",
                    "version_id": source_version,
                    "content_hash": CONTENT_HASH,
                    "raw_resource": _care_plan(),
                }
            ],
        }
    )


def test_lists_only_untouched_pending_fhir_candidate_differences() -> None:
    proposals = FhirCandidateReprojectionService(_database()).list_proposals()  # type: ignore[arg-type]

    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.fact_id == FACT_ID
    assert proposal.mapper_version == MAPPER_VERSION
    assert proposal.projected_value["title"] == "Fracture care"
    assert proposal.projected_value["activities"] == ["Recommendation to rest (completed)"]
    assert {"title", "description", "period", "category", "activities", "addresses"}.issubset(
        proposal.changed_fields
    )


def test_skips_a_candidate_with_any_clinician_touch() -> None:
    proposals = FhirCandidateReprojectionService(_database(touched=True)).list_proposals()  # type: ignore[arg-type]

    assert proposals == []


def test_uses_stored_content_hash_when_the_resource_has_no_version_id() -> None:
    proposals = FhirCandidateReprojectionService(
        _database(use_content_hash_version=True)
    ).list_proposals()  # type: ignore[arg-type]

    assert len(proposals) == 1
    assert proposals[0].source_version == CONTENT_HASH


def test_apply_uses_guarded_database_rpc_with_exact_source_version() -> None:
    db = _database()
    service = FhirCandidateReprojectionService(db)  # type: ignore[arg-type]
    proposal = service.list_proposals()[0]

    result = service.apply(
        proposal,
        actor_id=UUID("00000000-0000-0000-0000-000000000555"),
        idempotency_key=UUID("00000000-0000-0000-0000-000000000666"),
    )

    assert result["fact_id"] == FACT_ID
    assert db.rpc_calls == [
        (
            "apply_pending_fhir_candidate_reprojection",
            {
                "p_fact_id": FACT_ID,
                "p_actor_id": "00000000-0000-0000-0000-000000000555",
                "p_mapper_version": MAPPER_VERSION,
                "p_source_version": "4",
                "p_projected_value": proposal.projected_value,
                "p_idempotency_key": "00000000-0000-0000-0000-000000000666",
            },
        )
    ]
