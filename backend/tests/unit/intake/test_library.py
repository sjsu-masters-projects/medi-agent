import json
from pathlib import Path

import pytest

from app.core.exceptions import ValidationError
from app.intake import library as library_module
from app.intake.library import Bundle, load_library, select_question, validate_value


def synthetic_bundle():
    path = Path(__file__).parents[3] / "src/app/intake/question_library/v1.json"
    return Bundle.model_validate(json.loads(path.read_text()))


@pytest.fixture
def isolated_library(tmp_path, monkeypatch):
    """Temporary test approvals never modify or authorize the runtime package."""
    root = tmp_path / "question_library"
    root.mkdir()
    bundle = synthetic_bundle()
    (root / "candidate-1.json").write_text(bundle.model_dump_json())
    monkeypatch.setattr(library_module, "__file__", str(tmp_path / "library.py"))
    entry = {
        "file": "candidate-1.json",
        "status": "approved",
        "sha256": bundle.checksum,
        "approval": {
            "reference": "test-only-fixture-not-for-publication",
            "reviewer_identity": "Synthetic test reviewer",
            "reviewer_role": "Test fixture",
            "date": "2000-01-01",
        },
    }

    def write():
        (root / "manifest.json").write_text(
            json.dumps(
                {
                    "active_version": "candidate-1",
                    "bundles": {"candidate-1": entry},
                }
            )
        )

    return entry, write, bundle


def test_pending_bundle_cannot_activate(isolated_library):
    entry, write, _ = isolated_library
    entry["status"] = "pending_review"
    entry["approval"] = None
    write()
    with pytest.raises(ValidationError, match="unavailable"):
        load_library()


def test_approved_pinned_bundle_loads_only_from_isolated_test_package(isolated_library):
    _, write, bundle = isolated_library
    write()
    assert load_library().checksum == bundle.checksum


@pytest.mark.parametrize("failure", ["revoked", "wrong_hash", "missing_reference"])
def test_ineligible_or_incomplete_manifest_cannot_activate(isolated_library, failure):
    entry, write, _ = isolated_library
    if failure == "revoked":
        entry["status"] = "revoked"
    elif failure == "wrong_hash":
        entry["sha256"] = "0" * 64
    else:
        entry["approval"]["reference"] = ""
    write()
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
