"""FHIR R4 document Bundle for an approved care-handoff summary (CON-001).

Choice: a Composition-led document Bundle rather than a DocumentReference. The summary is a
clinician-authored, sectioned document with per-line sources, which is what a Composition
carries; a DocumentReference would only point at an opaque file. The Bundle holds the
Composition, a minimal Patient and Practitioner, and one Provenance whose entities are the
source records each line was read from. It is generated on demand from the approved version,
never written to an external server, and carries no private reasoning or other teams' data
(the sections it renders already exclude those).
"""

from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any

from fhir.resources.R4B.bundle import Bundle

from app.models.handoff import HandoffDetail

_SOURCE_SYSTEM = "urn:mediagent:source-record"
_SUMMARY_SYSTEM = "urn:mediagent:handoff-summary"
_SECTION_SYSTEM = "urn:mediagent:handoff-section"
_VERSION_EXTENSION = "urn:mediagent:handoff-version"
_PURPOSE_EXTENSION = "urn:mediagent:handoff-purpose"


def _instant(value: datetime) -> str:
    return value.isoformat()


def _div(lines: list[str]) -> dict[str, str]:
    body = "".join(f"<li>{escape(line)}</li>" for line in lines) or "<li>No entries.</li>"
    return {
        "status": "generated",
        "div": f'<div xmlns="http://www.w3.org/1999/xhtml"><ul>{body}</ul></div>',
    }


def build_handoff_bundle(detail: HandoffDetail, *, patient: dict[str, Any]) -> dict[str, Any]:
    if detail.status != "approved" or detail.approved_at is None or detail.approved_by is None:
        raise ValueError("Only an approved summary can be exported")
    composition_id = str(detail.id)
    patient_ref = f"Patient/{detail.patient_id}"
    author_ref = f"Practitioner/{detail.author_id}"
    approver_ref = f"Practitioner/{detail.approved_by}"
    sections: list[dict[str, Any]] = []
    entities: list[dict[str, Any]] = []
    seen: set[str] = set()
    for section in detail.version.sections:
        refs: list[dict[str, Any]] = []
        for item in section.items:
            if item.source.kind != "record" or not item.source.table:
                continue
            value = f"{item.source.table}/{item.source.id}" if item.source.id else item.source.table
            ref = {
                "identifier": {"system": _SOURCE_SYSTEM, "value": value},
                "display": item.source.label,
            }
            refs.append(ref)
            if value not in seen:
                seen.add(value)
                entities.append({"role": "source", "what": ref})
        lines = [item.text + (f" — {item.detail}" if item.detail else "") for item in section.items]
        entry: dict[str, Any] = {
            "title": section.title,
            "code": {"coding": [{"system": _SECTION_SYSTEM, "code": section.key}]},
            "text": _div(lines),
            "entry": refs,
        }
        if section.status != "available":
            entry["emptyReason"] = {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/list-empty-reason",
                        "code": "unavailable" if section.status == "unavailable" else "nilknown",
                    }
                ]
            }
            if section.status == "unavailable":
                entry.pop("entry")
        sections.append(entry)
    for key, title, text in (
        ("clinician_narrative", "Clinician narrative", detail.version.narrative),
        ("clinician_notes", "Clinician notes", detail.version.notes),
    ):
        if text:
            sections.append(
                {
                    "title": title,
                    "code": {"coding": [{"system": _SECTION_SYSTEM, "code": key}]},
                    "text": _div([text]),
                }
            )
    composition = {
        "resourceType": "Composition",
        "id": composition_id,
        "extension": [
            {"url": _VERSION_EXTENSION, "valueInteger": detail.version.version},
            {"url": _PURPOSE_EXTENSION, "valueCode": detail.purpose},
        ],
        "identifier": {"system": _SUMMARY_SYSTEM, "value": composition_id},
        "status": "final",
        "type": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": "34133-9",
                    "display": "Summarization of episode note",
                }
            ]
        },
        "subject": {"reference": patient_ref},
        "date": _instant(detail.approved_at),
        "author": [{"reference": author_ref}],
        "title": detail.title,
        "attester": [
            {
                "mode": "professional",
                "time": _instant(detail.approved_at),
                "party": {"reference": approver_ref},
            }
        ],
        "section": sections,
    }
    patient_resource = {
        "resourceType": "Patient",
        "id": str(detail.patient_id),
        "name": [{"family": patient.get("last_name"), "given": [patient.get("first_name")]}],
        "birthDate": patient.get("date_of_birth"),
    }
    provenance = {
        "resourceType": "Provenance",
        "target": [{"reference": f"Composition/{composition_id}"}],
        "recorded": _instant(detail.approved_at),
        "agent": [
            {"type": {"text": "author"}, "who": {"reference": author_ref}},
            {"type": {"text": "verifier"}, "who": {"reference": approver_ref}},
        ],
        "entity": entities,
    }
    bundle = {
        "resourceType": "Bundle",
        "type": "document",
        "timestamp": _instant(detail.approved_at),
        "identifier": {
            "system": _SUMMARY_SYSTEM,
            "value": f"{composition_id}/v{detail.version.version}",
        },
        "entry": [
            {"fullUrl": f"urn:uuid:{composition_id}", "resource": composition},
            {"fullUrl": f"urn:uuid:{detail.patient_id}", "resource": patient_resource},
            {
                "fullUrl": f"urn:uuid:{detail.author_id}",
                "resource": {"resourceType": "Practitioner", "id": str(detail.author_id)},
            },
            *(
                [
                    {
                        "fullUrl": f"urn:uuid:{detail.approved_by}",
                        "resource": {"resourceType": "Practitioner", "id": str(detail.approved_by)},
                    }
                ]
                if detail.approved_by != detail.author_id
                else []
            ),
            {"fullUrl": f"urn:uuid:{composition_id}-provenance", "resource": provenance},
        ],
    }
    return Bundle.model_validate(bundle).model_dump(mode="json", exclude_none=True)
