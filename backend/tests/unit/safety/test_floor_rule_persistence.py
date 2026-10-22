"""Every rule the deterministic floor can emit must be persistable (SAFE-002).

`urgent_medication_error` was emitted by the floor and answered to the patient, but the
persistence RPC accepted only the two emergency rules, so the turn was never saved and no
clinician was alerted. These tests enumerate the floor's rules and check each one against
the migration that defines the RPC; the PostgreSQL contract test
(tests/integration/test_chat_safety_postgres.py) runs the same enumeration against a real
database.
"""

from __future__ import annotations

import ast
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from app.models.chat import ChatMessageCreate
from app.routers.chat import _safety_completion, _safety_turn_payload
from app.safety import triage_floor
from app.safety.intake_gate import _COPY_KEYS, evaluate_intake_safety
from app.safety.triage_copy import TRIAGE_COPY
from app.safety.triage_floor import FLOOR_RULE_URGENCY, deterministic_safety_floor

MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "src/app/db/migrations/097_medication_error_safety_persistence.sql"
)

# One synthetic phrase per (rule, locale) so the enumeration is driven by real floor output.
PHRASES = [
    ("emergency_symptom_keyword", "en-US", "I have crushing chest pain"),
    ("emergency_symptom_keyword", "es-MX", "Tengo dolor de pecho"),
    ("emergency_mental_health_keyword", "en-US", "I want to kill myself"),
    ("emergency_mental_health_keyword", "es-MX", "quiero morir"),
    ("urgent_medication_error", "en-US", "I took my metformin twice"),
    ("urgent_medication_error", "es-MX", "tomé dos veces mi metformina"),
]


def _rules_in_floor_source() -> set[str]:
    tree = ast.parse(Path(triage_floor.__file__).read_text())
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "safety_rule":
            assert isinstance(node.value, ast.Constant), "a floor rule must be a literal"
            found.add(str(node.value.value))
    return found


def test_the_rule_table_lists_exactly_the_rules_the_floor_constructs() -> None:
    assert _rules_in_floor_source() == set(FLOOR_RULE_URGENCY)


def test_the_phrases_cover_every_rule_and_match_the_table() -> None:
    assert {rule for rule, _, _ in PHRASES} == set(FLOOR_RULE_URGENCY)
    for rule, _locale, phrase in PHRASES:
        verdict = deterministic_safety_floor(phrase)
        assert verdict is not None
        assert verdict.safety_rule == rule
        assert verdict.urgency == FLOOR_RULE_URGENCY[rule]


@pytest.mark.parametrize(("rule", "locale", "phrase"), PHRASES)
def test_every_rule_has_reviewed_copy_and_a_persistable_payload(
    rule: str, locale: str, phrase: str
) -> None:
    assert rule in _COPY_KEYS
    decision = evaluate_intake_safety(phrase, locale)
    assert decision is not None
    assert decision.response_text == TRIAGE_COPY[locale][_COPY_KEYS[rule]]
    incoming = ChatMessageCreate(content=phrase, language=locale)
    payload = _safety_turn_payload({"incoming": incoming, "decision": decision})
    assert payload["safety_rule"] == rule
    assert payload["rule_version"] == "triage-floor/1"
    # The completion event reports the verdict's urgency, never a hard-coded one.
    record = {
        "assistant_message": {
            "id": str(uuid4()),
            "patient_id": str(uuid4()),
            "role": "assistant",
            "content": decision.response_text,
            "language": locale,
            "created_at": datetime.now(UTC).isoformat(),
        },
        "persistence_status": "saved",
    }
    assert _safety_completion(record, decision)["urgency"] == FLOOR_RULE_URGENCY[rule]


def test_the_persistence_migration_accepts_every_floor_rule_with_its_urgency() -> None:
    sql = MIGRATION.read_text()
    for rule, urgency in FLOOR_RULE_URGENCY.items():
        assert f"WHEN '{rule}' THEN '{urgency}'" in sql, f"RPC does not map {rule}"
        assert re.search(rf"'{rule}'[^;]*?urgency = '{urgency}'", sql, re.S), (
            f"alert constraint does not tie {rule} to {urgency}"
        )
