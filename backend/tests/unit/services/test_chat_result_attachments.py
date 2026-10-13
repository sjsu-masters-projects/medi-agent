"""A reply's results card comes from the patient's own document facts, never its text."""

from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from postgrest.exceptions import APIError

from app.core.exceptions import NotFoundError
from app.services.chat_service import ChatService

PATIENT = "22222222-2222-2222-2222-222222222222"
DOC = "11111111-1111-1111-1111-111111111111"
OTHER = "33333333-3333-3333-3333-333333333333"
RESULT = {"kind": "lab_result", "name": "Potassium", "value": "6.9", "flag_meaning": "critical"}


def _documents(results_by_doc: dict[str, object]) -> MagicMock:
    service = MagicMock()

    def results(document_id: UUID, patient_id: UUID):
        outcome = results_by_doc[str(document_id)]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    service.list_document_results.side_effect = results
    service._get_document_row.return_value = {
        "file_name": "panel.pdf",
        "display_title": {"en-US": "Basic metabolic panel", "es-MX": "Panel metabólico"},
    }
    return service


def test_cited_documents_with_results_become_cards() -> None:
    documents = _documents({DOC: [RESULT], OTHER: []})
    with patch("app.services.document_service.DocumentService", return_value=documents):
        cards = ChatService(MagicMock()).result_attachments(PATIENT, [DOC, OTHER, DOC])
    assert cards == [
        {
            "type": "document_results",
            "document_id": DOC,
            "file_name": "panel.pdf",
            "title": {"en-US": "Basic metabolic panel", "es-MX": "Panel metabólico"},
            "results": [RESULT],
        }
    ]
    documents.list_document_results.assert_any_call(UUID(DOC), UUID(PATIENT))


def test_a_document_the_patient_cannot_see_never_becomes_a_card() -> None:
    documents = _documents({DOC: NotFoundError("Document", DOC)})
    with patch("app.services.document_service.DocumentService", return_value=documents):
        assert ChatService(MagicMock()).result_attachments(PATIENT, [DOC]) == []


@pytest.mark.asyncio
async def test_reply_is_saved_as_text_before_the_attachments_column_exists() -> None:
    db = MagicMock()
    table = db.table.return_value
    missing = APIError({"code": "PGRST204", "message": "Could not find the 'attachments' column"})
    saved = MagicMock(data=[{"id": "m1", "content": "Hi"}])
    table.insert.return_value.execute.side_effect = [missing, saved]
    sent: list[dict] = []
    original = table.insert.side_effect

    def record(payload):
        sent.append(dict(payload))
        return table.insert.return_value

    table.insert.side_effect = record
    row = await ChatService(db).save_message(
        PATIENT,
        {"content": "Hi", "role": "assistant", "attachments": [{"type": "document_results"}]},
    )
    assert original is None
    assert row == {"id": "m1", "content": "Hi"}
    assert "attachments" in sent[0] and "attachments" not in sent[1]
