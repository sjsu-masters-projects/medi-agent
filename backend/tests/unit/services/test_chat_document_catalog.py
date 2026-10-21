import pytest

from app.models.enums import Language
from app.services.chat_document_catalog import (
    build_document_catalog_reply,
    is_document_catalog_question,
)


def test_recognizes_clear_document_catalog_questions_in_both_supported_locales():
    assert is_document_catalog_question("What documents do you have on me?")
    assert is_document_catalog_question("¿Qué documentos tengo disponibles?")
    assert not is_document_catalog_question("Can you explain this document?")
    assert not is_document_catalog_question("I have a document with my lab result.")


def test_builds_a_bounded_portal_catalog_reply_without_claiming_full_clinic_records():
    reply = build_document_catalog_reply(
        [{"file_name": "follow-up.pdf", "document_type": "discharge_summary"}],
        Language.EN,
    )

    assert "follow-up.pdf (Discharge summary)" in reply
    assert "Documents tab" in reply
    assert "clinic may have other records outside the portal" in reply


def test_builds_an_honest_empty_catalog_reply_in_spanish():
    reply = build_document_catalog_reply([], Language.ES)

    assert "No veo documentos" in reply
    assert "Documentos" in reply


@pytest.mark.parametrize(
    "locale,title", [(Language.EN, "Lipid panel"), (Language.ES, "Perfil de lípidos")]
)
def test_catalog_reuses_grounded_title_and_preserves_original_filename(locale, title):
    document = {
        "file_name": "original.pdf",
        "document_type": "lab_report",
        "display_title": {"en-US": "Lipid panel", "es-MX": "Perfil de lípidos"},
    }
    reply = build_document_catalog_reply([document], locale)
    assert f"{title} (original.pdf)" in reply
    assert document["file_name"] == "original.pdf"


@pytest.mark.parametrize("titles", [{"en-US": "English only"}, None, "bad", {"es-MX": 42}])
def test_catalog_never_invents_or_cross_translates_a_missing_title(titles):
    reply = build_document_catalog_reply(
        [{"file_name": "original.pdf", "display_title": titles}], Language.ES
    )
    assert "original.pdf" in reply
    assert "English only" not in reply
