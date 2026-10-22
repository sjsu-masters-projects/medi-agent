"""Cross-plan source comparisons preserve clinical content and stale-decision guards."""

from dataclasses import replace
from uuid import UUID

import pytest

from app.core.exceptions import ValidationError
from app.services.care_plan_conflicts import (
    INTERACTION_COVERAGE,
    PlanMedication,
    conflict_fingerprint,
    detect_cross_plan_conflicts,
    require_current_acknowledgements,
)


def medication(**changes):
    values = dict(
        patient_id=UUID(int=1),
        plan_id=UUID(int=2),
        care_team_id=UUID(int=3),
        item_id=UUID(int=4),
        version_id=UUID(int=5),
        name="Metformin",
        dosage="500 mg",
        frequency="daily",
        route="oral",
        instructions="Source instruction",
        action="continue",
    )
    return PlanMedication(**(values | changes))


def other(**changes):
    return medication(
        **({"plan_id": UUID(int=6), "care_team_id": UUID(int=7), "item_id": UUID(int=8)} | changes)
    )


def test_exact_name_duplicate_is_a_review_blocker_not_interaction_advice():
    left, right = medication(), other(name="  METFORMIN  ")
    found = detect_cross_plan_conflicts([left], [right])
    assert len(found) == 1
    assert found[0].kind == "duplicate_medication"
    assert found[0].identity_basis == "recorded_name"
    assert found[0].requires_resolution
    assert left.name == "Metformin" and right.name == "  METFORMIN  "
    assert INTERACTION_COVERAGE == "not_checked"


@pytest.mark.parametrize(
    "field,value",
    [
        ("dosage", "1000 mg"),
        ("frequency", "twice daily"),
        ("route", "topical"),
        ("instructions", "Different source instruction"),
        ("schedule", '{"days":["Monday"]}'),
    ],
)
def test_source_regimen_differences_block_without_choosing_a_regimen(field, value):
    assert (
        detect_cross_plan_conflicts([medication()], [other(**{field: value})])[0].kind
        == "regimen_difference"
    )


@pytest.mark.parametrize("left_action,right_action", [("stop", "continue"), ("continue", "stop")])
def test_stop_and_continue_is_bidirectional(left_action, right_action):
    found = detect_cross_plan_conflicts(
        [medication(action=left_action)], [other(action=right_action)]
    )
    assert found[0].kind == "stop_continue"


def test_unknown_action_does_not_invent_stop_or_continue():
    assert (
        detect_cross_plan_conflicts([medication(action="unknown")], [other(action="stop")])[0].kind
        != "stop_continue"
    )


def test_recorded_ingredient_or_canonical_target_can_establish_overlap():
    found = detect_cross_plan_conflicts(
        [medication(ingredient_rxcui="6809")],
        [other(name="Recorded different name", ingredient_rxcui="6809")],
    )
    assert found[0].identity_basis == "recorded_ingredient"
    found = detect_cross_plan_conflicts(
        [medication(canonical_target_id=UUID(int=20))],
        [other(name="Recorded different name", canonical_target_id=UUID(int=20))],
    )
    assert found[0].identity_basis == "canonical_target"


@pytest.mark.parametrize(
    "name", ["Metformin ER", "Metformin hydrochloride", "Metformin/sitagliptin", "Brand name"]
)
def test_no_unrecorded_release_salt_brand_or_combination_equivalence(name):
    assert detect_cross_plan_conflicts([medication()], [other(name=name)]) == []


def test_other_patient_is_rejected_and_same_lineage_is_not_cross_plan():
    with pytest.raises(ValidationError, match="one patient"):
        detect_cross_plan_conflicts([medication()], [other(patient_id=UUID(int=30))])
    assert (
        detect_cross_plan_conflicts([medication()], [replace(other(), plan_id=UUID(int=2))]) == []
    )


def test_different_plan_owned_by_same_team_still_requires_review():
    assert len(detect_cross_plan_conflicts([medication()], [other(care_team_id=UUID(int=3))])) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("dosage", "1000 mg"),
        ("version_id", UUID(int=99)),
        ("care_team_id", UUID(int=99)),
        ("instructions", "New instructions"),
        ("wording", '{"es-MX":{"title":"Otro"}}'),
        ("canonical_target_id", UUID(int=99)),
        ("action", "stop"),
    ],
)
def test_acknowledgement_does_not_survive_changed_either_side(field, value):
    left, right = medication(), other()
    original = conflict_fingerprint(left, right)
    assert conflict_fingerprint(replace(left, **{field: value}), right) != original
    assert conflict_fingerprint(left, replace(right, **{field: value})) != original


def test_json_key_order_does_not_invalidate_the_same_snapshot():
    left = medication(schedule='{"a":1,"b":2}')
    assert conflict_fingerprint(left, other()) == conflict_fingerprint(
        replace(left, schedule='{"b":2,"a":1}'), other()
    )


@pytest.mark.parametrize("reason", [None, "", "   ", "x" * 2001])
def test_every_blocker_needs_its_current_nonempty_bounded_reason(reason):
    found = detect_cross_plan_conflicts([medication()], [other()])
    with pytest.raises(ValidationError, match="written reason"):
        require_current_acknowledgements(found, {found[0].fingerprint: reason})
    require_current_acknowledgements(
        found, {found[0].fingerprint: "Reviewed source overlap; intentional."}
    )


def test_old_reply_or_acknowledgement_never_unlocks_a_new_version():
    left, right = medication(), other()
    original = conflict_fingerprint(left, right)
    current = detect_cross_plan_conflicts([left], [replace(right, version_id=UUID(int=90))])
    with pytest.raises(ValidationError):
        require_current_acknowledgements(current, {original: "Old written reason", "reply": "OK"})


def test_duplicate_inputs_are_stable_and_no_conflict_is_not_a_safety_verdict():
    assert detect_cross_plan_conflicts(
        [medication(), medication()], [other(), other()]
    ) == detect_cross_plan_conflicts([medication()], [other()])
    require_current_acknowledgements([], {})
    assert INTERACTION_COVERAGE == "not_checked"
