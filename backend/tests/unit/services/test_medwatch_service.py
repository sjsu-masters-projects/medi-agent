"""Tests for evidence-grounded MedWatch draft orchestration."""

from datetime import date
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.core.exceptions import ValidationError
from app.models.adr import (
    MedWatchDraftApprovalRequest,
    MedWatchDraftCreateRequest,
    MedWatchDraftUpdateRequest,
    MedWatchFormData,
)
from app.services.medwatch_3500.identifier import DEFAULT_CODE_PATTERN, identifier_violations
from app.services.medwatch_service import (
    Form3500Sources,
    MedWatchService,
    build_form_3500,
    patient_identity,
)


def _response(data=None):
    return SimpleNamespace(data=data)


@pytest.fixture
def service() -> MedWatchService:
    db = MagicMock()
    chain = MagicMock()
    for method in ("select", "eq", "in_", "limit", "order", "single"):
        getattr(chain, method).return_value = chain
    db.table.return_value = chain
    return MedWatchService(db)


def _form(*, patient_identifier: str = "Maya Patel") -> MedWatchFormData:
    return MedWatchFormData.model_validate(
        {
            "patient": {
                "patient_identifier": patient_identifier,
                "date_of_birth": "1988-04-03",
                "sex": "female",
            },
            "event": {
                "description": "Dizziness",
                "onset_date_or_time": "2026-10-01",
                "outcome": "",
                "seriousness": "",
            },
            "suspect_product": {
                "name": "Fluticasone/salmeterol",
                "dose": "1 puff",
                "frequency": "twice daily",
                "route": "inhaled",
                "therapy_start_date": "2026-09-28",
                "therapy_end_date": "",
            },
            "concomitant_products": {"products": "Albuterol"},
            "tests_and_history": {
                "relevant_tests": "",
                "other_relevant_history": "",
            },
            "reporter": {
                "name": "Elena Park",
                "email": "elena@example.com",
                "specialty": "Internal medicine",
                "clinic_name": "MediAgent Clinic",
            },
            "clinical_review": {
                "naranjo_score": 6,
                "causality": "Probable",
                "reportability_rationale": "Clinically significant new event.",
            },
        }
    )


@pytest.mark.asyncio
async def test_create_draft_uses_patient_facts_and_keeps_unknown_fields_empty(service) -> None:
    clinician_id = uuid4()
    patient_id = uuid4()
    assessment_id = uuid4()
    symptom_id = uuid4()
    medication_id = uuid4()
    document_id = uuid4()
    draft_id = uuid4()
    service.care_team_repo.find_active_assignment = AsyncMock(return_value=[{"id": "team"}])
    service._execute = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            _response(
                {
                    "id": str(assessment_id),
                    "patient_id": str(patient_id),
                    "symptom_report_id": str(symptom_id),
                    "suspect_medication_id": str(medication_id),
                    "suspect_medication_name": "Fluticasone/salmeterol",
                    "naranjo_score": 6,
                    "causality": "Probable",
                    "status": "draft",
                    "evidence": [
                        {
                            "question": "dose_response",
                            "answer": "yes",
                            "evidence": "Symptoms improved after the prior dose was reduced.",
                        }
                    ],
                }
            ),
            _response([]),
            _response(
                {
                    "id": str(patient_id),
                    "first_name": "Maya",
                    "last_name": "Patel",
                    "date_of_birth": "1988-04-03",
                    "gender": "female",
                }
            ),
            _response(
                {
                    "id": str(symptom_id),
                    "symptom": "dizziness",
                    "severity": 2,
                    "onset": "a few hours after starting",
                    "notes": None,
                }
            ),
            _response(
                {
                    "id": str(medication_id),
                    "name": "Fluticasone/salmeterol",
                    "dosage": "1 puff",
                    "frequency": "twice daily",
                    "route": "inhaled",
                    "start_date": "2026-09-28",
                    "end_date": None,
                    "instructions": "Use twice daily",
                    "source_document_id": str(document_id),
                }
            ),
            _response(
                {
                    "id": str(clinician_id),
                    "first_name": "Elena",
                    "last_name": "Park",
                    "email": "elena@example.com",
                    "specialty": "Internal medicine",
                    "clinic_name": "MediAgent Clinic",
                }
            ),
            _response(
                [
                    {"id": str(medication_id), "name": "Fluticasone/salmeterol"},
                    {"id": str(uuid4()), "name": "Albuterol"},
                ]
            ),
            _response([{"id": str(draft_id), "status": "draft"}]),
        ]
    )

    result = await service.create_draft(
        clinician_id,
        assessment_id,
        MedWatchDraftCreateRequest(
            decision="prepare_draft",
            reportability_rationale="Clinically significant new event.",
        ),
    )

    assert result["id"] == str(draft_id)
    rpc_name, payload = service.db.rpc.call_args.args
    assert rpc_name == "create_medwatch_draft"
    assert payload["p_form_data"]["event"]["outcome"] == ""
    assert payload["p_form_data"]["tests_and_history"]["relevant_tests"] == ""
    assert payload["p_form_data"]["concomitant_products"]["products"] == "Albuterol"
    assert any(
        item["source_type"] == "document_grounded_medication"
        and item["citation"] == f"documents/{document_id}"
        for item in payload["p_source_evidence"]
    )
    assert any(
        item["source_type"] == "patient_confirmed_adr_evidence"
        for item in payload["p_source_evidence"]
    )


@pytest.mark.asyncio
async def test_update_draft_audits_only_changed_leaf_fields(service) -> None:
    clinician_id = uuid4()
    patient_id = uuid4()
    draft_id = uuid4()
    current = _form()
    updated = current.model_copy(deep=True)
    updated.event.outcome = "Recovering"
    service.care_team_repo.find_active_assignment = AsyncMock(return_value=[{"id": "team"}])
    service._execute = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            _response(
                {
                    "id": str(draft_id),
                    "patient_id": str(patient_id),
                    "status": "draft",
                    "revision": 1,
                    "form_data": current.model_dump(mode="json"),
                }
            ),
            _response([{"id": str(draft_id), "revision": 2, "status": "draft"}]),
        ]
    )

    await service.update_draft(
        clinician_id,
        draft_id,
        MedWatchDraftUpdateRequest(form_data=updated, expected_revision=1),
    )

    rpc_name, payload = service.db.rpc.call_args.args
    assert rpc_name == "update_medwatch_draft"
    assert payload["p_changed_fields"] == ["event.outcome"]


@pytest.mark.asyncio
async def test_approval_rejects_incomplete_draft_before_rpc(service) -> None:
    clinician_id = uuid4()
    patient_id = uuid4()
    draft_id = uuid4()
    service.care_team_repo.find_active_assignment = AsyncMock(return_value=[{"id": "team"}])
    service._execute = AsyncMock(  # type: ignore[method-assign]
        return_value=_response(
            {
                "id": str(draft_id),
                "patient_id": str(patient_id),
                "status": "draft",
                "revision": 1,
                "form_data": _form(patient_identifier="").model_dump(mode="json"),
            }
        )
    )

    with pytest.raises(ValidationError, match="patient identifier"):
        await service.approve_draft(
            clinician_id,
            draft_id,
            MedWatchDraftApprovalRequest(
                approval_note="Reviewed source evidence.",
                expected_revision=1,
                attested=True,
                attestation_version="medwatch-3500-approval-v1",
            ),
        )

    service.db.rpc.assert_not_called()


@pytest.mark.asyncio
async def test_export_marks_artifact_as_not_submitted_to_fda(service) -> None:
    clinician_id = uuid4()
    patient_id = uuid4()
    draft_id = uuid4()
    assessment_id = uuid4()
    approved = {
        "id": str(draft_id),
        "patient_id": str(patient_id),
        "adr_assessment_id": str(assessment_id),
        "status": "reviewed",
        "approved_by": str(clinician_id),
        "approved_at": "2026-10-09T11:00:00Z",
        "approval_note": "Reviewed source evidence.",
        "revision": 2,
        "export_version": "medwatch-3500a-draft-v1",
        "form_data": _form().model_dump(mode="json"),
        "source_evidence": [],
        "clinician_edited_fields": [],
    }
    service.care_team_repo.find_active_assignment = AsyncMock(return_value=[{"id": "team"}])
    service._execute = AsyncMock(  # type: ignore[method-assign]
        side_effect=[_response(approved), _response([approved])]
    )

    result = await service.export_draft(clinician_id, draft_id)

    assert result["content"]["not_submitted_to_fda"] is True
    assert "submitted" not in result["content"]["approval"]
    service.db.rpc.assert_called_once_with(
        "record_medwatch_draft_export",
        {"p_draft_id": str(draft_id), "p_actor_id": str(clinician_id)},
    )


def test_approval_requires_explicit_attestation() -> None:
    with pytest.raises(ValueError, match="attestation"):
        MedWatchDraftApprovalRequest(
            approval_note="Reviewed source evidence.",
            expected_revision=1,
            attested=False,
            attestation_version="medwatch-3500-approval-v1",
        )


# Form 3500 prefill with provenance (R17.1, R17.6, R18.1 to R18.6, K-P8). Synthetic records.
PATIENT_ID = UUID("11111111-1111-4111-8111-111111111111")
SYMPTOM_ID = UUID("22222222-2222-4222-8222-222222222222")
MEDICATION_ID = UUID("33333333-3333-4333-8333-333333333333")
ASSESSMENT_ID = UUID("44444444-4444-4444-8444-444444444444")
CLINICIAN_ID = UUID("55555555-5555-4555-8555-555555555555")
DOCUMENT_ID = UUID("66666666-6666-4666-8666-666666666666")
REQUEST_ID = UUID("77777777-7777-4777-8777-777777777777")
DRAFT_ID = UUID("88888888-8888-4888-8888-888888888888")
PREFILL_TODAY = date(2026, 10, 13)


def _sources(**overrides: Any) -> Form3500Sources:
    values: dict[str, Any] = {
        "draft_id": DRAFT_ID,
        "assessment": {
            "id": str(ASSESSMENT_ID),
            "suspect_medication_name": "Lisinopril",
            "naranjo_score": 6,
            "causality": "Probable",
            "naranjo_answers": {
                "improved_on_dechallenge": "yes",
                "reappeared_on_rechallenge": "yes",
                "dose_response": "no",
            },
            "evidence": [
                {
                    "question": "improved_on_dechallenge",
                    "answer": "yes",
                    "evidence": "Cough eased after the dose was held.",
                },
                {
                    "question": "reappeared_on_rechallenge",
                    "answer": "yes",
                    "evidence": "It came back when I restarted it.",
                    "source": "patient_follow_up",
                    "information_request_id": str(REQUEST_ID),
                },
                {
                    "question": "dose_response",
                    "answer": "no",
                    "evidence": "Chart note reviewed.",
                    "source": "clinician_review",
                },
            ],
        },
        "patient": {
            "id": str(PATIENT_ID),
            "first_name": "Lucía",
            "last_name": "Ramírez",
            "email": "lucia.ramirez@example.test",
            "date_of_birth": "1961-07-14",
            "gender": "female",
        },
        "symptom": {
            "id": str(SYMPTOM_ID),
            "symptom": "Dry cough",
            "severity": 4,
            "onset": "2026-10-02",
            "notes": "Worse at night",
            "created_at": "2026-10-03T16:00:00+00:00",
        },
        "medication": {
            "id": str(MEDICATION_ID),
            "name": "Lisinopril",
            "dosage": "10 mg",
            "frequency": "daily",
            "route": "oral",
            "start_date": "2026-09-01",
            "end_date": None,
            "is_active": True,
            "instructions": "Take one tablet daily",
            "source_document_id": str(DOCUMENT_ID),
        },
        "clinician": {
            "id": str(CLINICIAN_ID),
            "first_name": "Elena",
            "last_name": "Park",
            "email": "elena.park@example.test",
            "specialty": "Internal medicine",
            "clinic_name": "Synthetic Valley Clinic",
        },
        "medications": [
            {"id": str(MEDICATION_ID), "name": "Lisinopril"},
            {"id": "m-2", "name": "Metformin", "start_date": "2024-01-10"},
            {"id": "m-3", "generic_name": "atorvastatin", "end_date": "2026-12-31"},
        ],
        "conditions": [
            {"name": "Hypertension", "status": "active"},
            {"name": "Old fracture", "status": "resolved"},
        ],
        "allergies": [{"allergen": "Penicillin", "reaction": "hives"}, {"allergen": "Latex"}],
        "rationale": "New cough on an ACE inhibitor; reporting for signal review.",
        "today": PREFILL_TODAY,
    }
    values.update(overrides)
    return Form3500Sources(**values)


def _by_path(evidence: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for entry in evidence:
        assert len(entry["field_paths"]) == 1, entry
        grouped.setdefault(entry["field_paths"][0], []).append(entry)
    return grouped


def _filled_paths(value: Any, prefix: str = "") -> list[str]:
    if isinstance(value, dict):
        paths: list[str] = []
        for key, item in value.items():
            paths.extend(_filled_paths(item, f"{prefix}.{key}" if prefix else key))
        return paths
    if isinstance(value, list) and value and isinstance(value[0], dict):
        paths = []
        for index, item in enumerate(value):
            paths.extend(_filled_paths(item, f"{prefix}[{index}]"))
        return paths
    if value in (None, "", [], False) or prefix == "form_version":
        return []
    return [prefix]


def test_prefill_maps_each_item_from_its_stored_source() -> None:
    form, evidence = build_form_3500(_sources())
    a, b, product = form.section_a, form.section_b, form.section_d.product_1
    assert DEFAULT_CODE_PATTERN.fullmatch(a.identifier) and a.identifier.startswith("LR-")
    assert (a.date_of_birth, a.sex) == ("1961-07-14", "F")
    assert b.report_types == ["adverse_event"]
    assert (b.event_date, b.event_date_confirmed) == ("2026-10-02", False)
    assert b.narrative == "Dry cough (patient-reported severity 4/10). Worse at night"
    assert b.other_history == "Conditions: Hypertension. Allergies: Penicillin (hives); Latex."
    assert (product.name, product.dose, product.dose_unit) == (
        "Lisinopril",
        "10",
        "MILLIGRAM(S) - MG",
    )
    assert (product.frequency, product.route) == ("Daily", "Oral")
    assert (product.therapy_start, product.therapy_stop, product.ongoing) == (
        "2026-09-01",
        None,
        "yes",
    )
    assert (product.abated, product.reappeared) == ("yes", "yes")
    assert [(row.name, row.start, row.end) for row in form.section_f.others] == [
        ("Metformin", "2024-01-10", None),
        ("atorvastatin", None, None),
    ]
    g = form.section_g
    assert (g.first_name, g.last_name, g.email) == ("Elena", "Park", "elena.park@example.test")
    review = form.mediagent_review
    assert (review.naranjo_score, review.causality) == (6, "Probable")
    assert review.reportability_rationale.startswith("New cough")
    assert form.legacy == {}


def test_every_filled_path_has_source_evidence() -> None:
    form, evidence = build_form_3500(_sources())
    grouped = _by_path(evidence)
    dumped = form.model_dump(mode="json")
    dumped.pop("legacy")
    for path in _filled_paths(dumped):
        if path == "section_b.event_date_confirmed":
            continue
        assert path in grouped, path
    assert grouped["section_d.product_1.name"][0]["source_type"] == "document_grounded_medication"
    assert grouped["section_d.product_1.name"][0]["citation"] == f"documents/{DOCUMENT_ID}"
    assert grouped["section_a.sex"][0]["citation"] == f"patients/{PATIENT_ID}"
    assert grouped["section_g.email"][0]["source_type"] == "authenticated_clinician"
    assert grouped["section_f.others[0].start"][0]["citation"] == "medications/m-2"
    assert {e["source_type"] for e in grouped["section_b.other_history"]} == {
        "patient_condition_record",
        "patient_allergy_record",
    }


def test_items_without_a_stored_source_stay_blank() -> None:
    form, _evidence = build_form_3500(_sources())
    a, b, g = form.section_a, form.section_b, form.section_g
    assert (a.race, a.hispanic_latino, a.weight_value, a.weight_unit, a.age_value) == (
        [],
        False,
        "",
        None,
        "",
    )
    assert (b.outcomes, b.death_date, b.report_date, b.tests, b.tests_comments) == (
        [],
        None,
        None,
        [],
        "",
    )
    product = form.section_d.product_1
    assert (product.ndc_or_unique_id, product.lot, product.manufacturer_compounder) == ("", "", "")
    assert (product.diagnosis_for_use, product.product_types, product.expiration_date) == (
        "",
        [],
        None,
    )
    assert form.section_d.product_2 is None
    assert (g.phone, g.address, g.city, g.country) == ("", "", "", "")
    assert (g.health_professional, g.occupation, g.also_reported_to) == (None, None, [])


@pytest.mark.parametrize("gender", ["other", "prefer_not_to_say", None, "FEMALE "])
def test_sex_is_only_prefilled_for_female_or_male(gender) -> None:
    patient = {**_sources().patient, "gender": gender}
    form, evidence = build_form_3500(_sources(patient=patient))
    assert form.section_a.sex is None
    assert "section_a.sex" not in _by_path(evidence)


def test_b3_falls_back_to_the_report_date_as_a_best_estimate() -> None:
    symptom = {**_sources().symptom, "onset": "a few hours after the new dose"}
    form, evidence = build_form_3500(_sources(symptom=symptom))
    assert (form.section_b.event_date, form.section_b.event_date_confirmed) == ("2026-10-03", False)
    entry = _by_path(evidence)["section_b.event_date"][0]
    assert entry["attribution"] == "Best estimate, confirm: date the symptom was reported"
    assert entry["citation"] == f"symptom_reports/{SYMPTOM_ID}"
    onset_entry = _by_path(build_form_3500(_sources())[1])["section_b.event_date"][0]
    assert onset_entry["attribution"] == "Best estimate, confirm: patient-reported onset"


def test_b3_uses_the_los_angeles_date_of_created_at() -> None:
    symptom = {**_sources().symptom, "onset": None, "created_at": "2026-10-03T05:30:00Z"}
    form, _evidence = build_form_3500(_sources(symptom=symptom))
    assert form.section_b.event_date == "2026-10-02"


def test_assessment_evidence_keeps_its_own_source() -> None:
    _form, evidence = build_form_3500(_sources())
    entries = _by_path(evidence)["mediagent_review.causality"]
    by_excerpt = {entry["excerpt"]: entry for entry in entries}
    ai = by_excerpt["Cough eased after the dose was held."]
    patient = by_excerpt["It came back when I restarted it."]
    other = by_excerpt["Chart note reviewed."]
    assert ai["source_type"] == "ai_extracted_adr_evidence"
    assert patient["source_type"] == "patient_confirmed_adr_evidence"
    assert patient["source_id"] == str(REQUEST_ID)
    assert other["source_type"] == "adr_assessment_evidence"
    confirmed = [e for e in evidence if e["source_type"] == "patient_confirmed_adr_evidence"]
    assert all(e["excerpt"] == "It came back when I restarted it." for e in confirmed)


def test_dechallenge_items_are_labelled_by_their_evidence_source() -> None:
    _form, evidence = build_form_3500(_sources())
    grouped = _by_path(evidence)
    assert grouped["section_d.product_1.abated"][0]["source_type"] == "ai_extracted_adr_evidence"
    assert grouped["section_d.product_1.reappeared"][0]["source_type"] == (
        "patient_confirmed_adr_evidence"
    )


@pytest.mark.parametrize("answer", ["do_not_know", None, "maybe"])
def test_unknown_naranjo_answers_leave_d7_and_d8_blank(answer) -> None:
    assessment = {
        **_sources().assessment,
        "naranjo_answers": {"improved_on_dechallenge": answer, "reappeared_on_rechallenge": answer},
    }
    form, evidence = build_form_3500(_sources(assessment=assessment))
    assert (form.section_d.product_1.abated, form.section_d.product_1.reappeared) == (None, None)
    assert "section_d.product_1.abated" not in _by_path(evidence)


def test_no_answers_map_no_to_no() -> None:
    assessment = {
        **_sources().assessment,
        "naranjo_answers": {"improved_on_dechallenge": "no", "reappeared_on_rechallenge": "no"},
        "evidence": [],
    }
    form, evidence = build_form_3500(_sources(assessment=assessment))
    assert (form.section_d.product_1.abated, form.section_d.product_1.reappeared) == ("no", "no")
    entry = _by_path(evidence)["section_d.product_1.abated"][0]
    assert entry["source_type"] == "deterministic_adr_assessment"


def test_b6_is_never_prefilled_from_observation_facts() -> None:
    facts = [
        {
            "fact_type": "observation",
            "code": "2160-0",
            "value": "1.4 mg/dL",
            "effective": "2026-10-01",
        },
        {
            "fact_type": "observation",
            "code": "8480-6",
            "value": "142 mmHg",
            "effective": "2026-10-01",
        },
    ]
    form, evidence = build_form_3500(_sources(clinical_facts=facts))
    assert form.section_b.tests == []
    assert not any(path.startswith("section_b.tests") for path in _by_path(evidence))


def test_reporter_identity_appears_only_in_section_g() -> None:
    form, _evidence = build_form_3500(_sources())
    outside_g = str(
        form.model_dump(mode="json", include={"section_a", "section_b", "section_d", "section_f"})
    ).casefold()
    for value in ("elena", "park", "synthetic valley clinic", "internal medicine"):
        assert value not in outside_g
    assert "lucía" not in outside_g and "ramírez" not in outside_g
    identity = patient_identity(_sources().patient)
    assert identifier_violations(form.section_a.identifier, identity) == []


def test_unsplittable_text_and_overflow_go_to_legacy() -> None:
    medication = {
        **_sources().medication,
        "dosage": "1 puff",
        "route": "inhaled",
        "frequency": "twice daily",
    }
    many = [{"id": f"m-{n}", "name": f"Synthetic {n}"} for n in range(12)]
    form, evidence = build_form_3500(_sources(medication=medication, medications=many))
    product = form.section_d.product_1
    assert (product.dose, product.dose_unit) == ("", None)
    assert (product.route, product.route_other) == ("Respiratory (inhalation)", "")
    assert (product.frequency, product.frequency_other) == ("Other", "twice daily")
    assert len(form.section_f.others) == 10
    assert form.legacy == {
        "medication.dosage": "1 puff",
        "medications.additional": "Synthetic 10; Synthetic 11",
    }
    assert "legacy.medication.dosage" in _by_path(evidence)


def test_future_and_reversed_medication_dates_are_not_used() -> None:
    medication = {
        **_sources().medication,
        "start_date": "2026-09-01",
        "end_date": "2026-08-01",
        "is_active": False,
    }
    form, _evidence = build_form_3500(_sources(medication=medication))
    product = form.section_d.product_1
    assert (product.therapy_start, product.therapy_stop, product.ongoing) == (
        "2026-09-01",
        None,
        None,
    )
