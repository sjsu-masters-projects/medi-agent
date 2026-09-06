"""Unit coverage for external-patient identity binding safeguards."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.core.exceptions import AuthorizationError, ValidationError
from app.services.external_patient_binding_service import ExternalPatientBindingService

PATIENT_ID = UUID("00000000-0000-0000-0000-000000000111")
OTHER_PATIENT_ID = UUID("00000000-0000-0000-0000-000000000222")
CLINICIAN_ID = UUID("00000000-0000-0000-0000-000000000333")
IMPORT_ID = UUID("00000000-0000-0000-0000-000000000444")


class _Query:
    def __init__(self, data: object) -> None:
        self._data = data

    def select(self, *_args: object) -> _Query:
        return self

    def eq(self, *_args: object) -> _Query:
        return self

    def single(self) -> _Query:
        return self

    def execute(self) -> SimpleNamespace:
        return SimpleNamespace(data=self._data)


class _Db:
    def __init__(self, binding_rows: list[dict[str, object]]) -> None:
        self.binding_rows = binding_rows

    def table(self, name: str) -> _Query:
        if name == "fhir_imports":
            return _Query(
                {
                    "id": str(IMPORT_ID),
                    "issuer": "https://sandbox.example/fhir",
                    "external_patient_id": "external-patient-1",
                    "external_identity": {
                        "name": "Different Person",
                        "birthDate": "1990-01-01",
                        "gender": "female",
                    },
                }
            )
        if name == "patients":
            return _Query(
                {
                    "first_name": "Local",
                    "last_name": "Patient",
                    "date_of_birth": "1991-01-01",
                    "gender": "female",
                }
            )
        if name == "external_patient_bindings":
            return _Query(self.binding_rows)
        raise AssertionError(f"Unexpected table: {name}")


def test_mismatched_identity_requires_a_clinician_reason() -> None:
    service = ExternalPatientBindingService(_Db([]))  # type: ignore[arg-type]

    with pytest.raises(ValidationError, match="confirmation note"):
        service.confirm(
            import_id=IMPORT_ID,
            patient_id=PATIENT_ID,
            clinician_id=CLINICIAN_ID,
            confirmation_note=None,
        )


def test_external_patient_already_bound_to_another_local_patient_is_blocked() -> None:
    service = ExternalPatientBindingService(
        _Db([{"id": "binding-1", "patient_id": str(OTHER_PATIENT_ID)}])  # type: ignore[arg-type]
    )

    with pytest.raises(AuthorizationError, match="already bound"):
        service.confirm(
            import_id=IMPORT_ID,
            patient_id=PATIENT_ID,
            clinician_id=CLINICIAN_ID,
            confirmation_note="Synthetic record has a deliberately different name.",
        )
