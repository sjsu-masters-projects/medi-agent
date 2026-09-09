"""How much authority each clinical action requires.

The plan records that "clinical actions use tiered approval" so that clinicians retain
authority over clinical conclusions. Approval itself was already unavoidable — an action
envelope requires an approved recommendation, and approval requires an assigned clinician
who is not the proposer — but every action received identical scrutiny, and `action_type`
is free text, so no policy could distinguish surfacing a reminder from changing a
medication.

These tiers only ever tighten. Nothing here lets an action skip approval; the highest
tier adds a restriction on top of it. Loosening the existing gate would be a safety
change, and this is not the place to make one.

Adding an action type means deciding its tier here. That is the point: an action nobody
classified is treated as the most restricted kind rather than quietly inheriting the
default.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class ActionTier(StrEnum):
    """The authority a clinical action requires before it can be executed."""

    # Approval by an assigned clinician who is not the proposer.
    CLINICIAN_REVIEW = "clinician_review"

    # The same approval, and the recommendation must have originated with a clinician.
    # A model may not put this kind of action in front of a reviewer at all, because the
    # reviewer's judgment is meant to check a clinician's proposal, not launder a
    # model's.
    CLINICIAN_ORIGINATED = "clinician_originated"


# Actions whose tier has been decided. Unlisted actions are not permitted a lower tier by
# omission — see `tier_for`.
ACTION_TIERS: Final[dict[str, ActionTier]] = {
    "routine_message": ActionTier.CLINICIAN_REVIEW,
}


def tier_for(action_type: str) -> ActionTier:
    """Return the tier governing an action type.

    Unrecognized actions get the most restrictive tier rather than the default one. An
    action type reaches this function because someone introduced it without classifying
    it, and the safe reading of that is "nobody has decided yet", not "ordinary".
    """
    return ACTION_TIERS.get(action_type, ActionTier.CLINICIAN_ORIGINATED)


def requires_clinician_origin(action_type: str) -> bool:
    """Whether this action must be proposed by a clinician rather than a model."""
    return tier_for(action_type) is ActionTier.CLINICIAN_ORIGINATED
