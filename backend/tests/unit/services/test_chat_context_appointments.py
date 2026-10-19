"""Nora's context carries this patient's visits (and only theirs), allergies and plan tasks."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.adk.agents.care_coordinator.prompts import (
    CARE_COORDINATOR_INSTRUCTION,
    CARE_RESPONDER_INSTRUCTION,
)
from app.adk.tools import patient_context as patient_context_module
from app.adk.tools.patient_context import get_patient_context
from app.services.chat_service import APPOINTMENT_CONTEXT_LIMIT, ChatService

PATIENT_A = str(uuid4())
PATIENT_B = str(uuid4())
VISIT_UTC = "2099-10-22T16:00:00+00:00"  # 9:00 AM Pacific daylight time


class FakeQuery:
    """Applies the filters the service sends, so a missing patient filter shows up as a leak."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.filters: list[tuple[str, str, Any]] = []
        self._limit: int | None = None

    def select(self, *_args: Any, **_kwargs: Any) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self.filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self.filters.append(("in", column, values))
        return self

    def gte(self, column: str, value: Any) -> FakeQuery:
        self.filters.append(("gte", column, value))
        return self

    def order(self, *_args: Any, **_kwargs: Any) -> FakeQuery:
        return self

    def limit(self, count: int) -> FakeQuery:
        self._limit = count
        return self

    def execute(self) -> Any:
        rows = self.rows
        for kind, column, value in self.filters:
            if kind == "eq":
                rows = [r for r in rows if r.get(column) == value or r.get("id") == value]
            elif kind == "in":
                rows = [r for r in rows if r.get(column) in value]
            elif kind == "gte":
                rows = [r for r in rows if str(r.get(column)) >= str(value)]
        rows = rows[: self._limit] if self._limit else rows
        return type("Response", (), {"data": rows})()


class FakeDB:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self.tables = tables
        self.reads: list[tuple[str, list[tuple[str, str, Any]]]] = []

    def table(self, name: str) -> FakeQuery:
        query = FakeQuery(self.tables.get(name, []))
        self.reads.append((name, query.filters))
        return query


def visit(patient: str, when: str = VISIT_UTC, **changes: Any) -> dict[str, Any]:
    return {
        "patient_id": patient,
        "scheduled_at": when,
        "duration_minutes": 30,
        "appointment_type": "follow_up",
        "location": None,
        "reason": "Blood pressure review",
        "status": "confirmed",
        "clinician_name": "Elena Park",
        "proposal_expires_at": None,
        "clinics": {"display_name": "Cedar Grove"},
        **changes,
    }


def service(tables: dict[str, list[dict[str, Any]]]) -> tuple[ChatService, FakeDB]:
    db = FakeDB({"patients": [{"id": PATIENT_A, "timezone": "America/Los_Angeles"}], **tables})
    chat = ChatService(db)  # type: ignore[arg-type]
    return chat, db


async def no_plan(self: ChatService, patient_id: str) -> list[dict[str, Any]]:
    return []


@pytest.mark.asyncio
async def test_context_includes_the_confirmed_visit_in_the_patients_time_zone() -> None:
    chat, _ = service({"appointments": [visit(PATIENT_A)]})
    with patch.object(ChatService, "_fetch_todays_plan_activities", no_plan):
        context = await chat.get_context(PATIENT_A, include_schedule=True)
    [appointment] = context["appointments"]
    assert appointment["status"] == "confirmed"
    assert appointment["time_local"] == "9:00 AM"
    assert appointment["date_local"] == "October 22, 2099"
    assert appointment["weekday"] == "Thursday"
    assert appointment["clinician"] == "Elena Park"
    assert appointment["clinic"] == "Cedar Grove"
    assert appointment["visit_type"] == "follow_up"
    assert appointment["time_zone"] == "America/Los_Angeles"
    assert context["timezone"] == "America/Los_Angeles"


@pytest.mark.asyncio
async def test_another_patients_visits_are_never_included_and_the_read_is_filtered() -> None:
    chat, db = service(
        {"appointments": [visit(PATIENT_A), visit(PATIENT_B, clinician_name="Other")]}
    )
    with patch.object(ChatService, "_fetch_todays_plan_activities", no_plan):
        context = await chat.get_context(PATIENT_A, include_schedule=True)
    assert [a["clinician"] for a in context["appointments"]] == ["Elena Park"]
    reads = [filters for name, filters in db.reads if name == "appointments"]
    assert reads and ("eq", "patient_id", PATIENT_A) in reads[0]
    assert "Other" not in json.dumps(context)


@pytest.mark.asyncio
async def test_offers_and_change_requests_are_labelled_and_expired_offers_are_dropped() -> None:
    expired = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    open_until = "2099-10-20T00:00:00+00:00"
    chat, _ = service(
        {
            "appointments": [
                visit(PATIENT_A, status="proposed", proposal_expires_at=open_until),
                visit(
                    PATIENT_A,
                    "2099-10-23T16:00:00+00:00",
                    status="proposed",
                    proposal_expires_at=expired,
                ),
                visit(PATIENT_A, "2099-10-24T16:00:00+00:00", status="alternative_requested"),
                visit(PATIENT_A, "2099-10-25T16:00:00+00:00", status="cancelled"),
            ]
        }
    )
    with patch.object(ChatService, "_fetch_todays_plan_activities", no_plan):
        context = await chat.get_context(PATIENT_A, include_schedule=True)
    assert [a["status"] for a in context["appointments"]] == [
        "offer_awaiting_your_answer",
        "change_requested_awaiting_care_team",
    ]
    assert context["appointments"][0]["answer_by"] == open_until


@pytest.mark.asyncio
async def test_the_count_is_capped() -> None:
    rows = [visit(PATIENT_A, f"2099-11-{day:02d}T16:00:00+00:00") for day in range(1, 20)]
    chat, _ = service({"appointments": rows})
    with patch.object(ChatService, "_fetch_todays_plan_activities", no_plan):
        context = await chat.get_context(PATIENT_A, include_schedule=True)
    assert len(context["appointments"]) == APPOINTMENT_CONTEXT_LIMIT


@pytest.mark.asyncio
async def test_no_visits_is_an_empty_list_and_allergies_are_patient_scoped() -> None:
    chat, _ = service(
        {
            "allergies": [
                {
                    "patient_id": PATIENT_A,
                    "allergen": "Penicillin",
                    "reaction": "rash",
                    "severity": "moderate",
                },
                {
                    "patient_id": PATIENT_B,
                    "allergen": "Latex",
                    "reaction": None,
                    "severity": "mild",
                },
            ]
        }
    )
    with patch.object(ChatService, "_fetch_todays_plan_activities", no_plan):
        context = await chat.get_context(PATIENT_A, include_schedule=True)
    assert context["appointments"] == []
    assert [a["allergen"] for a in context["allergies"]] == ["Penicillin"]


@pytest.mark.asyncio
async def test_the_context_tool_hands_the_model_the_visits_and_plan_state() -> None:
    chat, _ = service({"appointments": [visit(PATIENT_A)]})

    async def plan(self: ChatService, patient_id: str) -> None:
        return None  # unreadable: must stay distinguishable from "nothing today"

    class Tool:
        state = {"user:patient_id": PATIENT_A, "patient_id": PATIENT_A}

    with (
        patch.object(patient_context_module, "_service", return_value=chat),
        patch.object(ChatService, "_fetch_todays_plan_activities", plan),
        patch.object(patient_context_module, "require_patient_id", return_value=PATIENT_A),
    ):
        result = await get_patient_context(Tool())
    assert result["appointments"][0]["clinic"] == "Cedar Grove"
    assert result["todays_plan_activities"] is None


def test_the_prompts_answer_visits_from_the_data_and_say_none_only_when_empty() -> None:
    assert "Appointments:" in CARE_COORDINATOR_INSTRUCTION
    assert "ONLY when `appointments` is present and empty" in CARE_COORDINATOR_INSTRUCTION
    assert "Appointments:" in CARE_RESPONDER_INSTRUCTION
    assert "ONLY when the notes say no upcoming visits are on record" in CARE_RESPONDER_INSTRUCTION


@pytest.mark.asyncio
async def test_the_do_i_have_an_appointment_cases_are_satisfiable_from_the_context() -> None:
    path = Path(__file__).resolve().parents[2] / "fixtures/nora/grounded_answers.json"
    cases = {c["id"]: c for c in json.loads(path.read_text())["cases"]}
    asked = [cases["nora-023"], cases["nora-024"]]
    assert {c["locale"] for c in asked} == {"en-US", "es-MX"}
    assert asked[0]["message"] == "Do I have an appointment coming up?"
    chat, _ = service({"appointments": [visit(PATIENT_A)]})
    with patch.object(ChatService, "_fetch_todays_plan_activities", no_plan):
        context = await chat.get_context(PATIENT_A, include_schedule=True)
    rendered = json.dumps(context)
    for case in asked:
        # What the case demands in the answer is data the model is handed.
        assert any(token in rendered for token in case["must_include_any"][:2])
        assert case["must_not_include"], "a wrong 'no appointments' answer must fail the case"


@pytest.mark.asyncio
async def test_the_connection_handshake_context_does_not_read_the_schedule() -> None:
    chat, db = service({"appointments": [visit(PATIENT_A)]})
    context = await chat.get_context(PATIENT_A)
    assert "appointments" not in context
    assert not [name for name, _ in db.reads if name in {"appointments", "allergies"}]
