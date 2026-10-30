"""Immutable paired-locale questions. Repository review is required for activation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic import ValidationError as SchemaError

from app.core.exceptions import ValidationError

LOCALES = {"en-US", "es-MX"}
FIELDS = {
    "description",
    "location",
    "onset",
    "duration",
    "course",
    "severity",
    "associated",
    "red_flags",
    "product",
    "concomitant",
    "history",
    "outcome",
}


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(pattern=r"^[a-z_]{1,40}$")
    wording: dict[str, str]
    answer_type: Literal["text", "rating", "boolean", "product"] = "text"
    required: bool = True
    applies_if: str | None = None
    positive_safety_rule: (
        Literal["emergency_symptom_keyword", "emergency_mental_health_keyword"] | None
    ) = None

    @model_validator(mode="after")
    def validate_contract(self) -> Question:
        if set(self.wording) != LOCALES or not all(self.wording.values()):
            raise ValueError("Every question requires both supported locales")
        if self.id not in FIELDS or self.applies_if not in {None, "product"}:
            raise ValueError("Unsupported question or applicability")
        if self.positive_safety_rule and self.answer_type != "boolean":
            raise ValueError("Reviewed positive mapping requires a boolean question")
        return self


class Bundle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["symptom-questions/1"]
    version: str = Field(min_length=1, max_length=80)
    questions: tuple[Question, ...] = Field(min_length=1, max_length=12)
    budget: int = Field(ge=1, le=12)

    @model_validator(mode="after")
    def validate_coverage(self) -> Bundle:
        ids = [q.id for q in self.questions]
        if len(set(ids)) != len(ids) or set(ids) != FIELDS or self.budget != 12:
            raise ValueError("Bundle must cover all twelve bounded fields exactly once")
        return self

    @property
    def checksum(self) -> str:
        encoded = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()

    def question(self, question_id: str) -> Question:
        for question in self.questions:
            if question.id == question_id:
                return question
        raise ValidationError("Unknown question", code="INTAKE_ANSWER_INVALID")


def load_library(version: str | None = None) -> Bundle:
    try:
        return _load_library(version)
    except (OSError, ValueError, KeyError, TypeError, SchemaError):
        raise ValidationError(
            "Question library unavailable", code="INTAKE_LIBRARY_UNAVAILABLE"
        ) from None


def _load_library(version: str | None = None) -> Bundle:
    """No test approval or browser flag is ever considered by the runtime loader."""
    root = Path(__file__).parent / "question_library"
    manifest = json.loads((root / "manifest.json").read_text())
    selected = version or manifest.get("active_version")
    entry = manifest.get("bundles", {}).get(selected)
    if not entry or entry.get("status") != "approved":
        raise ValidationError("Question library unavailable", code="INTAKE_LIBRARY_UNAVAILABLE")
    approval = entry.get("approval", {})
    if not all(
        approval.get(k) for k in ("reference", "reviewer_identity", "reviewer_role", "date")
    ):
        raise ValidationError("Question library unavailable", code="INTAKE_LIBRARY_UNAVAILABLE")
    path = root / entry["file"]
    if path.resolve().parent != root.resolve():
        raise ValidationError("Question library unavailable", code="INTAKE_LIBRARY_UNAVAILABLE")
    bundle = Bundle.model_validate_json(path.read_text())
    if bundle.checksum != entry.get("sha256") or bundle.version != selected:
        raise ValidationError("Question library unavailable", code="INTAKE_LIBRARY_UNAVAILABLE")
    return bundle


def version_label(version: str | None) -> str | None:
    """The name people see. The first release keeps its stored identifier, `candidate-1`,
    because existing intakes and reports reference it, but it is displayed as `v1`."""
    if not version:
        return version
    try:
        manifest = json.loads(
            (Path(__file__).parent / "question_library/manifest.json").read_text()
        )
        return str(manifest["bundles"][version]["label"])
    except (OSError, ValueError, KeyError, TypeError):
        return version


def select_question(bundle: Bundle, answers: dict[str, Any]) -> Question | None:
    for question in bundle.questions[: bundle.budget]:
        if question.id in answers:
            continue
        if question.applies_if == "product":
            product = answers.get("product", {})
            if (
                product.get("state") != "answered"
                or product.get("value", {}).get("concern") is not True
            ):
                continue
        return question
    return None


def validate_value(question: Question, state: str, value: Any) -> None:
    if state != "answered":
        if value is not None:
            raise ValidationError(
                "Unresolved answers cannot have a value", code="INTAKE_ANSWER_INVALID"
            )
        return
    valid = _valid_value(question.answer_type, value)
    if not valid:
        raise ValidationError("Invalid answer", code="INTAKE_ANSWER_INVALID")


def _valid_value(kind: str, value: Any) -> bool:
    if kind == "rating":
        return type(value) is int and 1 <= value <= 10
    if kind == "boolean":
        return type(value) is bool
    if kind == "product":
        allowed = {
            "concern",
            "name",
            "strength",
            "dose",
            "route",
            "indication",
            "start",
            "stop",
            "change",
        }
        return (
            isinstance(value, dict)
            and set(value) <= allowed
            and type(value.get("concern")) is bool
            and all(
                isinstance(v, str) and len(v) <= 300 for k, v in value.items() if k != "concern"
            )
            and (value["concern"] is False or bool(str(value.get("name", "")).strip()))
        )
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 1000
