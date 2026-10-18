"""CLN-003: an audit export tags an actor with the clinic of an ACTIVE link only."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.services.fhir_audit_export_service import FhirAuditExportService


def _service(rows: list[dict]) -> tuple[FhirAuditExportService, MagicMock]:
    db = MagicMock()
    chain = MagicMock()
    for method in ("select", "eq", "in_"):
        getattr(chain, method).return_value = chain
    chain.execute.return_value = SimpleNamespace(data=rows)
    db.table.return_value = chain
    return FhirAuditExportService(db), chain


def test_only_active_links_are_read() -> None:
    service, chain = _service([{"clinician_id": "c-1", "clinic_id": "clinic-A"}])
    assert service._actor_clinics(uuid4(), {"c-1"}) == {"c-1": "clinic-A"}
    chain.eq.assert_any_call("status", "active")
