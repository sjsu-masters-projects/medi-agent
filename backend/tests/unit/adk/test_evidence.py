"""AI-003: the structured evidence stored per reply. Synthetic values only."""

from types import SimpleNamespace
from uuid import uuid4

from app.adk.evidence import (
    MAX_SOURCES,
    build_evidence,
    care_plan_ids_of,
    tool_names_of,
)

DOC = str(uuid4())
PLAN = str(uuid4())


def test_tools_and_plan_ids_come_from_events() -> None:
    event = SimpleNamespace(
        get_function_calls=lambda: [
            SimpleNamespace(name="get_patient_context"),
            SimpleNamespace(name="Bad Name!"),
        ],
        get_function_responses=lambda: [
            SimpleNamespace(
                name="get_patient_context",
                response={
                    "medications": [{"plan": {"care_plan_id": PLAN}}],
                    "x": [{"care_plan_id": "nope"}],
                },
            ),
            SimpleNamespace(name="search_my_documents", response={"care_plan_id": str(uuid4())}),
        ],
    )
    assert tool_names_of(event) == ["get_patient_context"]
    assert care_plan_ids_of(event) == [PLAN]


def test_evidence_is_rebuilt_field_by_field_and_bounded() -> None:
    cited = [
        {
            "source": "document",
            "document_id": DOC,
            "file_name": "labs.pdf",
            "title": {"en-US": "Labs", "fr": "x"},
            "pages": [2, 1, True, 0],
            "selected": False,
            "details": "SECRET extracted value",
        },
        {"source": "document", "document_id": "not-a-uuid", "file_name": "x.pdf"},
        {
            "source": "MedlinePlus",
            "title": "Metformin",
            "url": "javascript:alert(1)",
            "language": "en-US",
            "checked_on": "2026-10-01",
            "text": "SECRET reference body",
        },
    ] + [{"source": f"S{i}", "title": "t"} for i in range(30)]
    evidence = build_evidence(tools=["a", "a", "b"], cited=cited, care_plan_ids=[PLAN, PLAN])
    assert evidence["tools"] == ["a", "b"] and evidence["care_plan_ids"] == [PLAN]
    document, reference = evidence["sources"][0], evidence["sources"][1]
    assert document["pages"] == [1, 2] and document["title"] == {"en-US": "Labs"}
    assert reference["url"] == ""
    assert "SECRET" not in str(evidence) and len(evidence["sources"]) == MAX_SOURCES
    assert build_evidence(tools=[], cited=[], care_plan_ids=[])["sources"] == []
