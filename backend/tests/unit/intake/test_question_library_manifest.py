"""The real package, not a fixture: what ships must be loadable and must not rewrite history."""

import json
from pathlib import Path

import pytest

from app.intake.library import Bundle, load_library, select_question, version_label

ROOT = Path(__file__).parents[3] / "src/app/intake/question_library"
MANIFEST = json.loads((ROOT / "manifest.json").read_text())
# Existing intakes and confirmed reports reference this identity in the hosted database.
FIRST_RELEASE = ("candidate-1", "a7ee7f3c7bfd91fdbf3fccba56fb42af86176801895ca0d70ad3c99ffd0917ab")


def test_active_version_loads_through_the_runtime_loader():
    assert load_library().version == MANIFEST["active_version"]


def test_first_release_keeps_its_stored_identity_and_hash():
    version, sha256 = FIRST_RELEASE
    assert MANIFEST["bundles"][version]["sha256"] == sha256
    assert load_library(version).checksum == sha256


@pytest.mark.parametrize("version", list(MANIFEST["bundles"]))
def test_every_release_is_approved_reviewed_and_loadable(version):
    entry = MANIFEST["bundles"][version]
    assert entry["status"] == "approved"
    assert load_library(version).version == version
    assert (ROOT / f"{entry['label']}-review.md").is_file()


def test_people_see_release_labels_not_stored_identifiers():
    assert version_label("candidate-1") == "v1"
    assert version_label("v2") == "v2"
    assert version_label(None) is None
    assert version_label("unknown") == "unknown"


def test_active_version_asks_about_other_products_for_every_symptom():
    bundle = load_library()
    answers = {
        q.id: {"state": "answered", "value": "x"}
        for q in bundle.questions
        if q.id not in {"product", "concomitant"}
    }
    answers["product"] = {"state": "answered", "value": {"concern": False}}
    question = select_question(bundle, answers)
    assert question is not None and question.id == "concomitant"


def test_no_release_file_is_left_outside_the_manifest():
    listed = {entry["file"] for entry in MANIFEST["bundles"].values()}
    assert {path.name for path in ROOT.glob("*.json")} - {"manifest.json"} == listed
    assert isinstance(Bundle.model_validate_json((ROOT / "v2.json").read_text()), Bundle)
