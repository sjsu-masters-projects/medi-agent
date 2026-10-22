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


def _section_resource(section: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """One Composition section and the source references its lines were read from."""
    refs: list[dict[str, Any]] = []
    for item in section.items:
        if item.source.kind != "record" or not item.source.table:
            continue
        value = f"{item.source.table}/{item.source.id}" if item.source.id else item.source.table
        refs.append(
            {
                "identifier": {"system": _SOURCE_SYSTEM, "value": value},
                "display": item.source.label,
            }
        )
    lines = [item.text + (f" — {item.detail}" if item.detail else "") for item in section.items]
    entry: dict[str, Any] = {
        "title": section.title,
        "code": {"coding": [{"system": _SECTION_SYSTEM, "code": section.key}]},
        "text": _div(lines),
    }
    if section.status == "unavailable":
        entry["emptyReason"] = _empty_reason("unavailable")
    else:
        entry["entry"] = refs
        if section.status == "empty":
            entry["emptyReason"] = _empty_reason("nilknown")
    return entry, refs


def _empty_reason(code: str) -> dict[str, Any]:
    return {
        "coding": [
            {"system": "http://terminology.hl7.org/CodeSystem/list-empty-reason", "code": code}
        ]
    }


def _clinician_sections(detail: HandoffDetail) -> list[dict[str, Any]]:
    texts = (
        ("clinician_narrative", "Clinician narrative", detail.version.narrative),
        ("clinician_notes", "Clinician notes", detail.version.notes),
    )
    return [
        {
            "title": title,
            "code": {"coding": [{"system": _SECTION_SYSTEM, "code": key}]},
            "text": _div([text]),
        }
        for key, title, text in texts
        if text
    ]


def _composition(detail: HandoffDetail, sections: list[dict[str, Any]]) -> dict[str, Any]:
    assert detail.approved_at is not None  # noqa: S101 - checked by the caller
    return {
        "resourceType": "Composition",
        "id": str(detail.id),
        "extension": [
            {"url": _VERSION_EXTENSION, "valueInteger": detail.version.version},
            {"url": _PURPOSE_EXTENSION, "valueCode": detail.purpose},
        ],
        "identifier": {"system": _SUMMARY_SYSTEM, "value": str(detail.id)},
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
        "subject": {"reference": f"Patient/{detail.patient_id}"},
        "date": _instant(detail.approved_at),
        "author": [{"reference": f"Practitioner/{detail.author_id}"}],
        "title": detail.title,
        "attester": [
            {
                "mode": "professional",
                "time": _instant(detail.approved_at),
                "party": {"reference": f"Practitioner/{detail.approved_by}"},
            }
        ],
        "section": sections,
    }


def _entry(resource: dict[str, Any], full_url: str) -> dict[str, Any]:
    return {"fullUrl": full_url, "resource": resource}


def build_handoff_bundle(detail: HandoffDetail, *, patient: dict[str, Any]) -> dict[str, Any]:
    if detail.status != "approved" or detail.approved_at is None or detail.approved_by is None:
        raise ValueError("Only an approved summary can be exported")
    sections: list[dict[str, Any]] = []
    entities: dict[str, dict[str, Any]] = {}
    for section in detail.version.sections:
        entry, refs = _section_resource(section)
        sections.append(entry)
        for ref in refs:
            entities.setdefault(ref["identifier"]["value"], {"role": "source", "what": ref})
    sections += _clinician_sections(detail)
    composition_id = str(detail.id)
    author_ref = f"Practitioner/{detail.author_id}"
    approver_ref = f"Practitioner/{detail.approved_by}"
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
        "entity": list(entities.values()),
    }
    people = {str(detail.author_id), str(detail.approved_by)}
    bundle = {
        "resourceType": "Bundle",
        "type": "document",
        "timestamp": _instant(detail.approved_at),
        "identifier": {
            "system": _SUMMARY_SYSTEM,
            "value": f"{composition_id}/v{detail.version.version}",
        },
        "entry": [
            _entry(_composition(detail, sections), f"urn:uuid:{composition_id}"),
            _entry(patient_resource, f"urn:uuid:{detail.patient_id}"),
            *(
                _entry({"resourceType": "Practitioner", "id": pid}, f"urn:uuid:{pid}")
                for pid in sorted(people)
            ),
            _entry(provenance, f"urn:uuid:{composition_id}-provenance"),
        ],
    }
    return Bundle.model_validate(bundle).model_dump(mode="json", exclude_none=True)
