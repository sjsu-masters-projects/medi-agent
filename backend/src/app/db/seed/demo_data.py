"""Typed loader for the canonical synthetic California portal fixture."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

DEMO_EMAIL_DOMAIN = "demo.mediagent.local"
CANONICAL_FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "synthetic_ca_portal_demo_2026_08.json"
)


@dataclass(frozen=True)
class DemoClinic:
    source_id: str
    display_name: str


@dataclass(frozen=True)
class DemoStaff:
    source_id: str
    display_label: str
    source_role: str
    clinic_source_id: str


@dataclass(frozen=True)
class DemoCondition:
    source_id: str
    label: str
    status: str


@dataclass(frozen=True)
class DemoAllergy:
    source_id: str
    substance: str
    reaction: str | None
    severity: str


@dataclass(frozen=True)
class DemoMedication:
    source_id: str
    label: str
    dose_text: str
    route: str
    start_date: str
    end_date: str | None
    status: str


@dataclass(frozen=True)
class DemoDocument:
    source_id: str
    title: str
    document_type: str
    created_at: str
    language: str
    mime_type: str


@dataclass(frozen=True)
class DemoTimelineEvent:
    source_id: str
    event_type: str
    timestamp: str
    summary: str
    channel: str | None


@dataclass(frozen=True)
class DemoPatientScenario:
    source_id: str
    display_label: str
    age_band: str
    preferred_language: str
    gender_identity: str
    clinic_source_id: str
    assigned_provider_source_id: str
    conditions: tuple[DemoCondition, ...]
    allergies: tuple[DemoAllergy, ...]
    medications: tuple[DemoMedication, ...]
    documents: tuple[DemoDocument, ...]
    timeline_events: tuple[DemoTimelineEvent, ...]
    declared_preferences: dict[str, Any]


@dataclass(frozen=True)
class DemoCareTeamAssignment:
    source_id: str
    patient_source_id: str
    staff_source_id: str
    role: str
    clinic_source_id: str
    effective_start: str
    grants_record_access: bool


@dataclass(frozen=True)
class CanonicalDemoFixture:
    dataset_id: str
    clinics: tuple[DemoClinic, ...]
    staff: tuple[DemoStaff, ...]
    patients: tuple[DemoPatientScenario, ...]
    care_team_assignments: tuple[DemoCareTeamAssignment, ...]


def _required(raw: dict[str, Any], field: str) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Canonical fixture is missing a non-empty {field}")
    return value


def _summary(raw: dict[str, Any]) -> str:
    return (
        _required(raw, "summary_en_us")
        if raw.get("summary_en_us")
        else _required(raw, "summary_es_mx")
    )


def _document_title(raw: dict[str, Any]) -> str:
    return (
        _required(raw, "title_en_us") if raw.get("title_en_us") else _required(raw, "title_es_mx")
    )


@lru_cache(maxsize=1)
def load_canonical_fixture() -> CanonicalDemoFixture:
    """Load the source-of-truth fixture without enriching its clinical content."""
    raw = json.loads(CANONICAL_FIXTURE_PATH.read_text(encoding="utf-8"))
    if raw.get("dataset_metadata", {}).get("is_synthetic") is not True:
        raise ValueError("Canonical demo fixture must be explicitly synthetic")

    clinics = tuple(
        DemoClinic(_required(item, "clinic_id"), _required(item, "display_name_en_us"))
        for item in raw["clinics"]
    )
    staff = tuple(
        DemoStaff(
            _required(item, "staff_id"),
            _required(item, "display_label"),
            _required(item, "role"),
            _required(item, "clinic_id"),
        )
        for item in raw["staff_accounts"]
    )
    patients = tuple(
        DemoPatientScenario(
            source_id=_required(item, "patient_id"),
            display_label=_required(item, "display_label"),
            age_band=_required(item, "age_band"),
            preferred_language=_required(item, "preferred_language"),
            gender_identity=_required(item, "gender_identity_declared"),
            clinic_source_id=_required(item, "clinic_id"),
            assigned_provider_source_id=_required(item, "assigned_provider_id"),
            conditions=tuple(
                DemoCondition(
                    _required(row, "condition_id"),
                    _required(row, "label_en_us"),
                    _required(row, "status"),
                )
                for row in item["conditions"]
            ),
            allergies=tuple(
                DemoAllergy(
                    _required(row, "allergy_id"),
                    _required(row, "substance_label"),
                    row.get("reaction_label"),
                    _required(row, "severity_label"),
                )
                for row in item["allergies"]
            ),
            medications=tuple(
                DemoMedication(
                    _required(row, "medication_id"),
                    _required(row, "label"),
                    _required(row, "dose_text_for_display_only"),
                    _required(row, "route"),
                    _required(row, "start_date"),
                    row.get("end_date"),
                    _required(row, "status"),
                )
                for row in item["medications"]
            ),
            documents=tuple(
                DemoDocument(
                    _required(row, "document_id"),
                    _document_title(row),
                    _required(row, "document_type"),
                    _required(row, "created_at"),
                    _required(row, "language"),
                    _required(row, "mime_type"),
                )
                for row in item["documents_metadata_only"]
            ),
            timeline_events=tuple(
                DemoTimelineEvent(
                    _required(row, "event_id"),
                    _required(row, "type"),
                    _required(row, "timestamp"),
                    _summary(row),
                    row.get("channel"),
                )
                for row in item["timeline_events"]
            ),
            declared_preferences=dict(item["declared_preferences"]),
        )
        for item in raw["patient_scenarios"]
    )
    assignments = tuple(
        DemoCareTeamAssignment(
            _required(item, "assignment_id"),
            _required(item, "patient_id"),
            _required(item, "staff_id"),
            _required(item, "role"),
            _required(item, "clinic_id"),
            _required(item, "effective_start"),
            bool(item.get("grants_record_access")),
        )
        for item in raw["care_team_assignments"]
    )
    fixture = CanonicalDemoFixture(
        _required(raw["dataset_metadata"], "dataset_id"), clinics, staff, patients, assignments
    )
    _validate_fixture(fixture)
    return fixture


def _validate_fixture(fixture: CanonicalDemoFixture) -> None:
    if len(fixture.patients) != 8:
        raise ValueError("Canonical demo fixture must contain exactly eight patient scenarios")
    language_counts = {
        language: sum(patient.preferred_language == language for patient in fixture.patients)
        for language in ("en-US", "es-MX")
    }
    if language_counts != {"en-US": 5, "es-MX": 3}:
        raise ValueError("Canonical demo fixture must preserve the 5 en-US / 3 es-MX split")
    if len({patient.source_id for patient in fixture.patients}) != len(fixture.patients):
        raise ValueError("Canonical demo fixture has duplicate patient IDs")
