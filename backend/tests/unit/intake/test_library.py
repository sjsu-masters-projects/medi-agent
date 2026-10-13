import json
from pathlib import Path

import pytest

from app.core.exceptions import ValidationError
from app.intake.library import Bundle, load_library, select_question, validate_value


def synthetic_bundle():
    path = Path(__file__).parents[3] / "src/app/intake/question_library/candidate-1.json"
    return Bundle.model_validate(json.loads(path.read_text()))


def test_pending_bundle_cannot_activate():
    with pytest.raises(ValidationError, match="unavailable"):
        load_library()


def test_selection_budget_and_unresolved_semantics():
    bundle = synthetic_bundle()
    answers = {}
    asked = []
    while question := select_question(bundle, answers):
        asked.append(question.id)
        answers[question.id] = {"state": "declined", "value": None}
    assert len(asked) == 11
    assert "concomitant" not in asked
    assert select_question(bundle, answers) is None
    answers["product"] = {
        "state": "answered",
        "value": {"concern": True, "name": "Synthetic unlisted product"},
    }
    assert select_question(bundle, answers).id == "concomitant"
    assert len(set(asked + ["concomitant"])) == 12


@pytest.mark.parametrize("value", [None, 0, 11, True, "severe", 3.5])
def test_severity_cannot_be_inferred(value):
    with pytest.raises(ValidationError):
        validate_value(synthetic_bundle().question("severity"), "answered", value)


def test_unknown_has_no_inferred_value():
    question = synthetic_bundle().question("severity")
    validate_value(question, "unknown", None)
    with pytest.raises(ValidationError):
        validate_value(question, "unknown", 0)


def test_requires_paired_coverage():
    payload = synthetic_bundle().model_dump()
    payload["questions"][0]["wording"].pop("es-MX")
    with pytest.raises(ValueError):
        Bundle.model_validate(payload)
