from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from tests.unit.intake.test_library import synthetic_bundle
from tests.unit.intake.test_service import resolved_row, service

from app.core.exceptions import ValidationError
from app.intake.conversation import interpret, reports_no_other_products, source_suggestions
from app.models.symptom_intake import IntakeReply


@pytest.mark.parametrize(
    ("text", "state", "value"),
    [
        ("not sure", "unknown", None),
        ("No sé", "unknown", None),
        ("skip", "declined", None),
        ("Prefiero no responder", "declined", None),
        ("five", "answered", 5),
        ("cinco", "answered", 5),
        ("8 out of 10", "answered", 8),
        ("10/10", "answered", 10),
    ],
)
def test_rating_interpretation_never_guesses(text, state, value):
    assert interpret(synthetic_bundle().question("severity"), text) == (state, value)


@pytest.mark.parametrize("text", ["mild", "very bad", "5 or 6", "0", "11", "yes", "confirm"])
def test_ambiguous_rating_is_not_an_answer(text):
    with pytest.raises(ValidationError):
        interpret(synthetic_bundle().question("severity"), text)


def test_product_name_is_testimony_not_a_medication_match():
    assert interpret(synthetic_bundle().question("product"), "Unlisted supplement") == (
        "answered",
        {"concern": True, "name": "Unlisted supplement"},
    )
    assert interpret(synthetic_bundle().question("product"), "No") == (
        "answered",
        {"concern": False},
    )
    with pytest.raises(ValidationError):
        interpret(synthetic_bundle().question("product"), "Yes")


@pytest.mark.parametrize(
    "text",
    [
        "no",
        "No.",
        "nope",
        "No, I'm not",
        "No, I’m not",
        "not really",
        "nothing",
        "no thanks",
        "Nada",
        "no gracias",
        "No me preocupa",
        "no, ninguno",
    ],
)
def test_a_plain_no_never_becomes_a_product_name(text):
    assert interpret(synthetic_bundle().question("product"), text) == (
        "answered",
        {"concern": False},
    )


@pytest.mark.parametrize(
    "text", ["no, but maybe ibuprofen", "I don't think so", "creo que no", "not sure if it's that"]
)
def test_a_hedged_negative_asks_again_rather_than_recording_a_product(text):
    with pytest.raises(ValidationError):
        interpret(synthetic_bundle().question("product"), text)


@pytest.mark.parametrize(
    ("text", "name"),
    [
        ("yes, ibuprofen", "ibuprofen"),
        ("Sí, ibuprofeno", "ibuprofeno"),
        ("ibuprofen", "ibuprofen"),
        ("Norvasc", "Norvasc"),
        ("No-Doz", "No-Doz"),
        ("Nobel vitamin", "Nobel vitamin"),
    ],
)
def test_a_named_product_is_kept_without_a_leading_yes(text, name):
    assert interpret(synthetic_bundle().question("product"), text) == (
        "answered",
        {"concern": True, "name": name},
    )


@pytest.mark.parametrize("text", ["none", "Nada", "no, ninguno", "ningún otro"])
def test_no_other_products_is_recognized(text):
    assert reports_no_other_products(text)


@pytest.mark.parametrize("text", ["ibuprofen", "", None, 3])
def test_named_other_products_are_not_treated_as_none(text):
    assert not reports_no_other_products(text)


def test_source_candidates_quote_explicit_values_only():
    candidates = source_suggestions("I have a mild headache since yesterday, rated 5/10.")
    assert candidates["description"].startswith("I have")
    assert candidates["onset"] == "since yesterday, rated 5/10"
    assert candidates["severity"] == 5
    assert "severity" not in source_suggestions("A mild headache")


@pytest.mark.asyncio
async def test_voice_reply_uses_private_answer_boundary():
    svc = service()
    row = resolved_row()
    row["answers"].pop("severity")
    svc._read_row = AsyncMock(return_value=row)
    svc.library = MagicMock(return_value=synthetic_bundle())
    svc.answer = AsyncMock(return_value={"status": "collecting"})
    await svc.reply(
        uuid4(),
        IntakeReply(
            expected_revision=11,
            mutation_id=uuid4(),
            question_id="severity",
            text="cinco",
            locale="es-MX",
            input_mode="voice",
        ),
    )
    answer = svc.answer.call_args.args[1]
    assert answer.value == 5 and answer.wording == "cinco" and answer.input_mode == "voice"
    svc.db.table.assert_not_called()


@pytest.mark.asyncio
async def test_voice_emergency_precedes_parser_and_unavailable_library():
    svc = service()
    svc._read_row = AsyncMock(return_value=resolved_row())
    svc.library = MagicMock(side_effect=AssertionError("must not load"))
    svc.interrupt = AsyncMock(return_value={"status": "interrupted_safety"})
    result = await svc.reply(
        uuid4(),
        IntakeReply(
            expected_revision=11,
            mutation_id=uuid4(),
            question_id="severity",
            text="I cannot breathe",
            locale="en-US",
            input_mode="voice",
        ),
    )
    assert result["status"] == "interrupted_safety"
    svc.library.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "declared", "actual"),
    [
        ("Me duele la cabeza desde ayer.", "en-US", "es-MX"),
        ("The headache is in my forehead.", "es-MX", "en-US"),
    ],
)
async def test_reply_preserves_answer_language_without_changing_draft(text, declared, actual):
    svc = service()
    row = resolved_row()
    svc._read_row = AsyncMock(return_value=row)
    svc.library = MagicMock(return_value=synthetic_bundle())
    svc.answer = AsyncMock(return_value={"status": "collecting"})
    await svc.reply(
        uuid4(),
        IntakeReply(
            expected_revision=11,
            mutation_id=uuid4(),
            question_id="description",
            text=text,
            locale=declared,
            input_mode="voice",
        ),
    )
    answer = svc.answer.call_args.args[1]
    assert answer.wording == text and answer.locale == actual
    assert row["locale"] == "es-MX"
