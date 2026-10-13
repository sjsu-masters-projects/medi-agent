"""The Form 3500 approval request and its attestation text (R17.5, R19.3, R19.6)."""

import pytest
from pydantic import ValidationError

from app.models.adr import (
    MEDWATCH_APPROVAL_ATTESTATION_VERSION,
    MEDWATCH_APPROVAL_ATTESTATIONS,
    MedWatchDraftApprovalRequest,
)
from app.models.medwatch_form_3500 import MedWatchNameWarning


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "approval_note": "  Reviewed source evidence.  ",
        "expected_revision": 2,
        "attested": True,
        "attestation_version": "medwatch-3500-approval-v1",
        "non_serious_attested": True,
        "acknowledged_warnings": [
            {"path": "section_b.narrative", "kind": "patient_name"},
            {"path": "section_b.narrative", "kind": "patient_name"},
            {"path": "section_f.others[0].name", "kind": "clinic_name"},
        ],
    }
    payload.update(overrides)
    return payload


def test_valid_payload() -> None:
    request = MedWatchDraftApprovalRequest.model_validate(_payload())
    assert request.approval_note == "Reviewed source evidence."
    assert request.attestation_version == MEDWATCH_APPROVAL_ATTESTATION_VERSION
    assert request.non_serious_attested is True
    assert request.acknowledged_warnings == [
        MedWatchNameWarning(path="section_b.narrative", kind="patient_name"),
        MedWatchNameWarning(path="section_f.others[0].name", kind="clinic_name"),
    ]


def test_optional_fields_default_to_no_attestation_and_no_warnings() -> None:
    payload = _payload()
    del payload["non_serious_attested"], payload["acknowledged_warnings"]
    request = MedWatchDraftApprovalRequest.model_validate(payload)
    assert request.non_serious_attested is False
    assert request.acknowledged_warnings == []


@pytest.mark.parametrize("version", ["medwatch-3500a-approval-v1", "medwatch-3500-approval-v2", ""])
def test_wrong_attestation_version_is_rejected(version) -> None:
    with pytest.raises(ValidationError) as caught:
        MedWatchDraftApprovalRequest.model_validate(_payload(attestation_version=version))
    assert caught.value.errors()[0]["loc"] == ("attestation_version",)


@pytest.mark.parametrize(
    "field", ["attestation_version", "attested", "approval_note", "expected_revision"]
)
def test_missing_required_field_is_rejected(field) -> None:
    payload = _payload()
    del payload[field]
    with pytest.raises(ValidationError) as caught:
        MedWatchDraftApprovalRequest.model_validate(payload)
    assert (field,) in {tuple(error["loc"]) for error in caught.value.errors()}


def test_unknown_warning_kind_is_rejected() -> None:
    with pytest.raises(ValidationError):
        MedWatchDraftApprovalRequest.model_validate(
            _payload(acknowledged_warnings=[{"path": "section_b.narrative", "kind": "email"}])
        )


def test_attestation_must_be_true() -> None:
    with pytest.raises(ValidationError, match="attestation"):
        MedWatchDraftApprovalRequest.model_validate(_payload(attested=False))


def test_one_attestation_text_per_version_states_who_submits() -> None:
    assert set(MEDWATCH_APPROVAL_ATTESTATIONS) == {MEDWATCH_APPROVAL_ATTESTATION_VERSION}
    text = MEDWATCH_APPROVAL_ATTESTATIONS[MEDWATCH_APPROVAL_ATTESTATION_VERSION]
    assert "Form FDA 3500" in text
    assert "I will submit it to FDA myself" in text
    assert "MediAgent does not submit it to FDA" in text
    assert "responsible for its content" in text
    assert "3500A" not in text
