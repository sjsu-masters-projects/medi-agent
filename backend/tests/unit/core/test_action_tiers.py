"""Which authority each clinical action requires.

The property that carries the safety weight is what happens to an action nobody
classified. Defaulting it to the ordinary tier would mean a new action type silently
inherits the weakest policy, which is exactly the failure the registry exists to stop.
"""

import pytest

from app.core.action_tiers import (
    ACTION_TIERS,
    ActionTier,
    requires_clinician_origin,
    tier_for,
)


def test_a_registered_action_gets_its_declared_tier():
    assert tier_for("routine_message") is ActionTier.CLINICIAN_REVIEW


def test_an_unregistered_action_gets_the_most_restricted_tier():
    """Reaching this means nobody classified the action, which is not the same as ordinary."""
    assert tier_for("prescribe_controlled_substance") is ActionTier.CLINICIAN_ORIGINATED
    assert tier_for("") is ActionTier.CLINICIAN_ORIGINATED


@pytest.mark.parametrize("action_type", ["", "unknown", "   ", "routine_message_typo"])
def test_no_unregistered_spelling_slips_into_the_ordinary_tier(action_type: str):
    assert tier_for(action_type) is ActionTier.CLINICIAN_ORIGINATED


def test_every_registered_tier_is_a_real_tier():
    assert all(isinstance(tier, ActionTier) for tier in ACTION_TIERS.values())


def test_clinician_origin_is_required_only_at_the_top_tier():
    assert requires_clinician_origin("unlisted_action") is True
    assert requires_clinician_origin("routine_message") is False


def test_no_tier_permits_skipping_approval():
    """Tiers only tighten. A tier that waived review would be a safety regression."""
    assert set(ActionTier) == {ActionTier.CLINICIAN_REVIEW, ActionTier.CLINICIAN_ORIGINATED}
