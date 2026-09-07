"""Explicit binding of a SMART sandbox patient to a local synthetic patient."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from supabase import Client

from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError


class ExternalPatientBindingService:
    """Prevents one external patient being reconciled into the wrong local chart."""

    def __init__(self, db: Client) -> None:
        self.db = db

    def preview(self, *, import_id: UUID, patient_id: UUID) -> dict[str, Any]:
        imported = self._import(import_id=import_id, patient_id=patient_id)
        local = self._local_identity(patient_id)
        external = cast(dict[str, Any], imported.get("external_identity") or {})
        return {
            "import_id": str(import_id),
            "patient_id": str(patient_id),
            "issuer": str(imported["issuer"]),
            "external_patient_id": str(imported["external_patient_id"]),
            "external_identity": external,
            "local_identity": local,
            "identity_matches": self._matches(local, external),
            "binding_id": imported.get("external_patient_binding_id"),
            "confirmed_at": imported.get("identity_confirmed_at"),
        }

    def confirm(
        self,
        *,
        import_id: UUID,
        patient_id: UUID,
        clinician_id: UUID,
        confirmation_note: str | None,
    ) -> dict[str, Any]:
        imported = self._import(import_id=import_id, patient_id=patient_id)
        external_patient_id = imported.get("external_patient_id")
        if not isinstance(external_patient_id, str) or not external_patient_id:
            raise ValidationError("SMART import has no external patient context")
        local = self._local_identity(patient_id)
        external = cast(dict[str, Any], imported.get("external_identity") or {})
        if not self._matches(local, external) and not (
            confirmation_note and confirmation_note.strip()
        ):
            raise ValidationError(
                "A confirmation note is required when external and local identity differ"
            )

        existing = cast(
            list[dict[str, Any]],
            self.db.table("external_patient_bindings")
            .select("*")
            .eq("issuer", str(imported["issuer"]).rstrip("/"))
            .eq("external_patient_id", external_patient_id)
            .execute()
            .data
            or [],
        )
        if existing and str(existing[0].get("patient_id")) != str(patient_id):
            raise AuthorizationError(
                "This external patient is already bound to another local patient"
            )
        if existing:
            binding = existing[0]
        else:
            result = (
                self.db.table("external_patient_bindings")
                .insert(
                    {
                        "issuer": str(imported["issuer"]).rstrip("/"),
                        "external_patient_id": external_patient_id,
                        "patient_id": str(patient_id),
                        "confirmed_by": str(clinician_id),
                        "confirmation_note": confirmation_note.strip()
                        if confirmation_note
                        else None,
                        "external_identity": external,
                    }
                )
                .execute()
            )
            rows = cast(list[dict[str, Any]], result.data or [])
            if not rows:
                raise ValidationError("Could not create external patient binding")
            binding = rows[0]

        confirmed_at = datetime.now(UTC).isoformat()
        self.db.table("fhir_imports").update(
            {
                "external_patient_binding_id": str(binding["id"]),
                "identity_confirmed_at": confirmed_at,
                "identity_confirmation_note": confirmation_note.strip()
                if confirmation_note
                else None,
            }
        ).eq("id", str(import_id)).eq("patient_id", str(patient_id)).execute()
        return self.preview(import_id=import_id, patient_id=patient_id)

    def assert_import_bound(self, *, import_id: UUID, patient_id: UUID) -> None:
        imported = self._import(import_id=import_id, patient_id=patient_id)
        if not imported.get("external_patient_binding_id") or not imported.get(
            "identity_confirmed_at"
        ):
            raise ValidationError(
                "Confirm the external patient identity before applying imported data"
            )

    def _import(self, *, import_id: UUID, patient_id: UUID) -> dict[str, Any]:
        result = (
            self.db.table("fhir_imports")
            .select("*")
            .eq("id", str(import_id))
            .eq("patient_id", str(patient_id))
            .single()
            .execute()
        )
        imported = cast(dict[str, Any] | None, result.data)
        if not imported:
            raise NotFoundError("SMART import", str(import_id))
        return imported

    def _local_identity(self, patient_id: UUID) -> dict[str, Any]:
        result = (
            self.db.table("patients")
            .select("first_name, last_name, date_of_birth, gender")
            .eq("id", str(patient_id))
            .single()
            .execute()
        )
        patient = cast(dict[str, Any] | None, result.data)
        if not patient:
            raise NotFoundError("Patient", str(patient_id))
        return {
            "name": " ".join(
                part for part in (patient.get("first_name"), patient.get("last_name")) if part
            ),
            "birthDate": patient.get("date_of_birth"),
            "gender": patient.get("gender"),
        }

    @staticmethod
    def _matches(local: dict[str, Any], external: dict[str, Any]) -> bool:
        if not external:
            return False

        def normalized(value: Any) -> str:
            return " ".join(str(value or "").strip().lower().split())

        return (
            normalized(local.get("name")) == normalized(external.get("name"))
            and str(local.get("birthDate") or "") == str(external.get("birthDate") or "")
            and str(local.get("gender") or "") == str(external.get("gender") or "")
        )
