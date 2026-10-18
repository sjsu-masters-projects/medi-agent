"""LOC-003 shared translation guards: units, separators, negation and protected names."""

from __future__ import annotations

import pytest

from app.services import care_plan_translation as plans
from app.services import fact_display_translation as facts
from app.services import message_translation as messages
from app.services.translation_guards import (
    changed_protected_terms,
    guard_failure,
    negation_flipped,
    number_tokens,
)


@pytest.mark.parametrize(
    ("source", "target", "ok"),
    [
        ("Take 500 mg twice", "Toma 500 mg dos veces", True),
        ("Take 500 mg", "Toma 500 g", False),  # unit changed
        ("Take 5 mg", "Toma 5 mcg", False),
        ("Take 5 mcg", "Toma 5 µg", True),
        ("Inject 10 units", "Inyecta 10 unidades", True),
        ("Inject 10 units", "Inyecta 10 mL", False),
        ("Drink 2 L", "Bebe 2 litros", True),
        ("Take 2 tablets", "Toma 2 tabletas", True),
        ("Take 2 tablets", "Toma 2 mg", False),
        ("Reduce by 5%", "Reduce 5", False),
        ("Use 2,5 ml", "Use 2.5 ml", True),  # decimal comma folds
        ("Take 1,000 mg", "Toma 1.000 mg", False),  # thousands ambiguity is a failure
        ("Take 1.000 mg", "Toma 1,000 mg", False),
        ("Take 1,000 mg", "Toma 1,000 mg", True),
    ],
)
def test_number_guard_compares_units_and_separators(source: str, target: str, ok: bool) -> None:
    assert (number_tokens(source) == number_tokens(target)) is ok


@pytest.mark.parametrize(
    ("source", "target", "flipped"),
    [
        ("Do not take this with food", "Toma esto con comida", True),
        ("Don't skip a dose", "Salta una dosis", True),
        ("Never double the dose", "Duplica la dosis", True),
        ("Take it without food", "Tómalo con comida", True),
        ("Take it", "Nunca lo tomes", True),
        ("Do not take this", "No tomes esto", False),
        ("Take it without food", "Tómalo sin comida", False),
        ("Take it daily", "Tómalo a diario", False),
    ],
)
def test_negation_guard(source: str, target: str, flipped: bool) -> None:
    assert negation_flipped(source, target) is flipped


def test_protected_terms_must_survive_whole_word() -> None:
    assert changed_protected_terms(["Take Metformin"], ["Toma Metformin"], ["Metformin"]) == []
    assert changed_protected_terms(["Take Metformin"], ["Toma Metformina"], ["Metformin"]) == [
        "Metformin"
    ]
    # A name that was never in the source is not required in the target.
    assert changed_protected_terms(["Take it"], ["Tómalo"], ["Metformin"]) == []


def test_guard_failure_orders_codes() -> None:
    assert guard_failure("Take 5 mg", "Toma 6 mg") == "numbers_changed"
    assert guard_failure("Do not take it", "Tómalo") == "negation_changed"
    assert (
        guard_failure("Take Lisinopril", "Toma Lisinopril 10", protected=["Lisinopril"])
        == "numbers_changed"
    )
    assert (
        guard_failure("Take Lisinopril", "Toma Lisinoprilo", protected=["Lisinopril"])
        == "medication_name_changed"
    )
    assert guard_failure("Take Lisinopril", "Toma Lisinopril", protected=["Lisinopril"]) is None


def test_every_translation_path_uses_the_shared_unit_aware_guard() -> None:
    assert messages._numbers("Take 500 mg") != messages._numbers("Take 500 g")
    assert plans._numbers({"title": "5 mg"}) != plans._numbers({"title": "5 mcg"})
    assert facts._all_numbers({"a": "5 mg"}) != facts._all_numbers({"a": "5 g"})
    assert facts._all_numbers({"a": "1,000"}) != facts._all_numbers({"a": "1.000"})
