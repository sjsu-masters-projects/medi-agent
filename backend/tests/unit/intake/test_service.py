from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from tests.unit.intake.test_library import synthetic_bundle

from app.core.exceptions import AuthorizationError, ValidationError
from app.models.auth import CurrentUser
from app.models.symptom_intake import IntakeAnswer, IntakeConfirm, IntakeStart
from app.services.symptom_intake_service import SymptomIntakeService


def resolved_row():
    bundle = synthetic_bundle()
    return {
        "id": str(uuid4()),
        "patient_id": str(uuid4()),
        "revision": 11,
        "library_version": bundle.version,
        "library_hash": bundle.checksum,
        "locale": "es-MX",
        "timezone": "America/Los_Angeles",
        "session_id": "default",
        "source_message_id": str(uuid4()),
        "status": "collecting",
        "answers": {
            q.id: {"state": "unknown", "value": None, "wording": "", "locale": "es-MX"}
            for q in bundle.questions
            if not q.applies_if
        },
    }


def service():
    return SymptomIntakeService(
        MagicMock(), CurrentUser(id=uuid4(), email="synthetic@invalid.test", role="patient")
    )


@pytest.mark.asyncio
async def test_safety_runs_before_unavailable_library_or_value_selection():
    svc = service()
    row = {"id": str(uuid4()), "revision": 0, "library_version": "unavailable", "answers": {}}
    svc._read_row = AsyncMock(return_value=row)
    svc.interrupt = AsyncMock(return_value={"status": "interrupted_safety"})
    answer = IntakeAnswer(
        expected_revision=0,
        mutation_id=uuid4(),
        question_id="description",
        state="answered",
        value="I cannot breathe",
        locale="en-US",
    )
    assert (await svc.answer(uuid4(), answer))["status"] == "interrupted_safety"
    svc.interrupt.assert_awaited_once()


@pytest.mark.asyncio
async def test_wrong_actor_does_not_invoke_rpc():
    svc = service()
    svc.actor = CurrentUser(id=uuid4(), email="synthetic@invalid.test", role="clinician")
    with pytest.raises(AuthorizationError):
        await svc.active("default")
    svc.db.rpc.assert_not_called()


def test_identity_fields_are_rejected_and_timezone_is_not_browser_supplied():
    with pytest.raises(ValueError):
        IntakeStart(source_message_id=uuid4(), session_id="default", patient_id=str(uuid4()))
    assert service()._timezone("not/a/zone") == ("UTC", True)
    assert service()._timezone("America/Los_Angeles") == ("America/Los_Angeles", False)


@pytest.mark.asyncio
async def test_preview_uses_test_only_library_and_keeps_unknown_and_skips(monkeypatch):
    svc = service()
    row = resolved_row()
    svc.library = MagicMock(return_value=synthetic_bundle())
    svc._read_row = AsyncMock(return_value=row)
    svc._call = AsyncMock(return_value=row)
    context = {
        "version": "symptom-context/1",
        "purpose": "patient_symptom_preview",
        "medications": [],
        "facts": [],
        "excerpts": [],
    }
    monkeypatch.setattr(
        "app.services.symptom_intake_service.retrieve_context", AsyncMock(return_value=context)
    )
    await svc.preview(row["id"], row["revision"])
    action, payload = svc._call.call_args.args
    assert action == "preview"
    snapshot = payload["preview"]
    assert snapshot["answers"]["severity"]["value"] is None
    assert "No sé" in snapshot["summary"]
    assert snapshot["selection"]["concomitant"]["state"] == "not_applicable"
    assert snapshot["context"] == context
    assert snapshot["source_message_id"] == row["source_message_id"]


@pytest.mark.asyncio
async def test_incomplete_preview_never_retrieves_or_writes(monkeypatch):
    svc = service()
    row = resolved_row()
    row["answers"].pop("severity")
    svc.library = MagicMock(return_value=synthetic_bundle())
    svc._read_row = AsyncMock(return_value=row)
    svc._call = AsyncMock()
    retrieve = AsyncMock()
    monkeypatch.setattr("app.services.symptom_intake_service.retrieve_context", retrieve)
    with pytest.raises(ValidationError):
        await svc.preview(row["id"], row["revision"])
    retrieve.assert_not_awaited()
    svc._call.assert_not_awaited()


@pytest.mark.asyncio
async def test_context_withdrawal_masks_snapshot_and_blocks_confirmation(monkeypatch):
    svc = service()
    row = resolved_row()
    row.update(status="ready_for_confirmation", preview={"context": {}})
    svc.library = MagicMock(return_value=synthetic_bundle())
    monkeypatch.setattr(
        "app.services.symptom_intake_service.verify_context", AsyncMock(return_value=False)
    )
    visible = await svc._visible(row)
    assert visible["preview"] is None and not visible["can_confirm"]
    svc._read_row = AsyncMock(return_value=visible)
    svc._call = AsyncMock()
    with pytest.raises(ValidationError):
        await svc.confirm(
            row["id"],
            IntakeConfirm(
                expected_revision=11, confirmation_id=uuid4(), preview_hash="a" * 64, consent=True
            ),
        )
    svc._call.assert_not_awaited()


def test_database_revocation_disables_question_selection():
    svc = service()
    svc.library = MagicMock(return_value=synthetic_bundle())
    row = resolved_row()
    row["database_library_available"] = False
    assert not svc.describe(row)["library_available"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "locale,text", [("en-US", "I cannot breathe"), ("es-MX", "No puedo respirar")]
)
async def test_explicit_start_safety_preserves_direction_and_required_alert(
    monkeypatch, locale, text
):
    svc = service()
    svc._source = AsyncMock(
        return_value={
            "id": str(uuid4()),
            "content": text,
            "language": locale,
            "session_id": "default",
        }
    )
    svc.library = MagicMock(side_effect=AssertionError("ordinary intake must not run"))
    record = AsyncMock(return_value={"persistence_status": "saved"})
    monkeypatch.setattr("app.services.chat_safety_service.ChatSafetyService.record_safely", record)
    result = await svc.start(IntakeStart(source_message_id=uuid4(), session_id="default"))
    assert result["status"] == "interrupted_safety" and result["safety"]["response_text"]
    record.assert_awaited_once()
    svc.library.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["preview", "confirm"])
async def test_ledger_safety_precedes_revoked_library_and_context(monkeypatch, operation):
    svc = service()
    row = resolved_row()
    row["answers"]["description"] = {
        "state": "answered",
        "value": "I cannot breathe",
        "wording": "",
        "locale": "en-US",
    }
    svc._read_row = AsyncMock(return_value=row)
    svc.library = MagicMock(side_effect=AssertionError("Safety must run first"))
    svc.interrupt = AsyncMock(return_value={"status": "interrupted_safety"})
    retrieve = AsyncMock()
    monkeypatch.setattr("app.services.symptom_intake_service.retrieve_context", retrieve)
    if operation == "preview":
        result = await svc.preview(row["id"], row["revision"])
    else:
        result = await svc.confirm(
            row["id"],
            IntakeConfirm(
                expected_revision=row["revision"],
                confirmation_id=uuid4(),
                preview_hash="a" * 64,
                consent=True,
            ),
        )
    assert result["status"] == "interrupted_safety"
    svc.library.assert_not_called()
    retrieve.assert_not_awaited()


def test_clinical_consumers_never_receive_cached_source_context():
    from app.intake.preview import testimony_only

    report = {
        "severity": None,
        "confirmed_content": {
            "summary": "Synthetic testimony",
            "answers": {"severity": {"state": "unknown", "value": None}},
            "context": {"excerpts": ["withdrawn source"]},
        },
    }
    visible = testimony_only(report)
    assert "context" not in visible["confirmed_content"]
    assert visible["confirmed_content"]["answers"]["severity"]["value"] is None
    assert "context" in report["confirmed_content"]


@pytest.mark.asyncio
async def test_confirmed_product_concern_starts_report_scoped_adr_handoff(monkeypatch):
    svc = service()
    report_id = str(uuid4())
    medication_id = str(uuid4())
    report = {
        "id": report_id,
        "confirmed_content": {
            "answers": {
                "product": {
                    "state": "answered",
                    "value": {"concern": True, "name": "Metformin"},
                }
            },
            "context": {"medications": [{"source_id": medication_id, "name": "Metformin"}]},
        },
    }
    svc._call = AsyncMock(return_value=report)
    run = AsyncMock(return_value={"task_id": "task-1", "status": "completed"})
    monkeypatch.setattr(
        "app.services.symptom_intake_service.A2ATaskService.run_symptom_to_pharmacovigilance",
        run,
    )

    result = await svc._handoff_confirmed_product_concern(
        {"confirmed_report_id": report_id, "session_id": "session-1"}
    )

    assert result["adr_handoff"] == {"task_id": "task-1", "status": "completed"}
    run.assert_awaited_once_with(
        patient_id=str(svc.actor.id),
        payload={"session_id": "session-1", "symptom_report": report},
    )


@pytest.mark.asyncio
async def test_confirmed_report_without_product_concern_skips_adr_handoff(monkeypatch):
    svc = service()
    report_id = str(uuid4())
    svc._call = AsyncMock(
        return_value={
            "id": report_id,
            "confirmed_content": {
                "answers": {
                    "product": {
                        "state": "answered",
                        "value": {"concern": False},
                    }
                }
            },
        }
    )
    run = AsyncMock()
    monkeypatch.setattr(
        "app.services.symptom_intake_service.A2ATaskService.run_symptom_to_pharmacovigilance",
        run,
    )

    result = await svc._handoff_confirmed_product_concern(
        {"confirmed_report_id": report_id, "session_id": "session-1"}
    )

    assert "adr_handoff" not in result
    run.assert_not_awaited()


@pytest.mark.asyncio
async def test_confirmed_unlisted_product_is_preserved_without_fabricated_adr_link(monkeypatch):
    svc = service()
    report_id = str(uuid4())
    svc._call = AsyncMock(
        return_value={
            "id": report_id,
            "confirmed_content": {
                "answers": {
                    "product": {
                        "state": "answered",
                        "value": {"concern": True, "name": "Patient-reported product"},
                    }
                },
                "context": {"medications": []},
            },
        }
    )
    run = AsyncMock()
    monkeypatch.setattr(
        "app.services.symptom_intake_service.A2ATaskService.run_symptom_to_pharmacovigilance",
        run,
    )

    result = await svc._handoff_confirmed_product_concern(
        {"confirmed_report_id": report_id, "session_id": "session-1"}
    )

    assert result["adr_handoff"]["status"] == "requires_medication_reconciliation"
    run.assert_not_awaited()


@pytest.mark.asyncio
async def test_confirm_retry_uses_public_path_to_recover_report_handoff(monkeypatch):
    svc = service()
    row = resolved_row()
    report_id = str(uuid4())
    medication_id = str(uuid4())
    row.update(status="confirmed", confirmed_report_id=report_id)
    report = {
        "id": report_id,
        "confirmed_content": {
            "answers": {
                "product": {
                    "state": "answered",
                    "value": {"concern": True, "name": "Metformin"},
                }
            },
            "context": {"medications": [{"source_id": medication_id, "name": "Metformin"}]},
        },
    }
    svc.library = MagicMock(return_value=synthetic_bundle())
    svc._read_row = AsyncMock(return_value=row)
    svc._call = AsyncMock(side_effect=[row, report])
    run = AsyncMock(return_value={"task_id": "task-1", "status": "completed"})
    monkeypatch.setattr(
        "app.services.symptom_intake_service.A2ATaskService.run_symptom_to_pharmacovigilance",
        run,
    )

    result = await svc.confirm(
        row["id"],
        IntakeConfirm(
            expected_revision=row["revision"],
            confirmation_id=uuid4(),
            preview_hash="a" * 64,
            consent=True,
        ),
    )

    assert result["adr_handoff"] == {"task_id": "task-1", "status": "completed"}
    run.assert_awaited_once()


@pytest.mark.asyncio
async def test_first_confirm_uses_public_path_to_start_report_handoff(monkeypatch):
    svc = service()
    row = resolved_row()
    svc.library = MagicMock(return_value=synthetic_bundle())
    report_id = str(uuid4())
    medication_id = str(uuid4())
    row.update(status="ready_for_confirmation", preview={"context": {}})
    confirmed = {**row, "status": "confirmed", "confirmed_report_id": report_id}
    report = {
        "id": report_id,
        "confirmed_content": {
            "answers": {
                "product": {
                    "state": "answered",
                    "value": {"concern": True, "name": "Metformin"},
                }
            },
            "context": {"medications": [{"source_id": medication_id, "name": "Metformin"}]},
        },
    }
    svc._read_row = AsyncMock(return_value=row)
    svc._call = AsyncMock(side_effect=[confirmed, report])
    monkeypatch.setattr(
        "app.services.symptom_intake_service.verify_context", AsyncMock(return_value=True)
    )
    run = AsyncMock(return_value={"task_id": "task-1", "status": "completed"})
    monkeypatch.setattr(
        "app.services.symptom_intake_service.A2ATaskService.run_symptom_to_pharmacovigilance",
        run,
    )

    result = await svc.confirm(
        row["id"],
        IntakeConfirm(
            expected_revision=row["revision"],
            confirmation_id=uuid4(),
            preview_hash="a" * 64,
            consent=True,
        ),
    )

    assert result["adr_handoff"] == {"task_id": "task-1", "status": "completed"}
    assert svc._call.await_args_list[0].args[0] == "confirm"
    assert svc._call.await_args_list[1].args == (
        "report",
        {"report_id": report_id},
    )


@pytest.mark.asyncio
async def test_confirmed_report_remains_authoritative_when_handoff_is_temporarily_unavailable():
    svc = service()
    report_id = str(uuid4())
    svc._call = AsyncMock(side_effect=RuntimeError("temporary worker outage"))

    result = await svc._handoff_confirmed_product_concern(
        {"confirmed_report_id": report_id, "status": "confirmed"}
    )

    assert result["status"] == "confirmed"
    assert result["confirmed_report_id"] == report_id
    assert result["adr_handoff"] == {"task_id": None, "status": "pending"}
