"""Uncertainty for evaluation samples too small for the usual normal approximation.

The routing evaluation runs 8 to 28 scenarios per workload. At that size a point
estimate is close to meaningless on its own: eight correct answers out of eight is
consistent with a true accuracy of 68%. Normal-approximation error bars understate
that badly and can collapse to zero width at a perfect score, so proportions use the
Wilson score interval instead, and partial-credit means use a percentile bootstrap.

Comparisons between two models run on the same scenarios are paired: the models see
identical inputs, so the question is which items they disagree on, not how their
aggregate scores differ. A paired test finds real differences that overlapping
per-model intervals hide, and it needs at least six one-sided disagreements before a
difference is significant at this sample size.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass

# Two-sided 95%.
_Z_95 = 1.959963984540054

BOOTSTRAP_RESAMPLES = 10_000
"""Resamples for a percentile interval. Fixed so a report is reproducible."""


@dataclass(frozen=True)
class Interval:
    """A point estimate and its confidence interval, all on the same scale."""

    point: float
    low: float
    high: float

    @property
    def width(self) -> float:
        return self.high - self.low

    def format(self, *, percent: bool = True) -> str:
        """Render as ``84% (62-95%)``, the form the evaluation report uses."""
        if percent:
            return f"{self.point:.0%} ({self.low * 100:.0f}-{self.high:.0%})"
        return f"{self.point:.2f} ({self.low:.2f}-{self.high:.2f})"


@dataclass(frozen=True)
class PairedComparison:
    """Two models on identical scenarios, compared item by item."""

    a_only: int
    """Scenarios where A succeeded and B failed."""
    b_only: int
    """Scenarios where B succeeded and A failed."""
    agreed: int
    p_value: float

    @property
    def discordant(self) -> int:
        return self.a_only + self.b_only

    @property
    def significant(self) -> bool:
        """Whether the difference clears the conventional 5% level."""
        return self.p_value < 0.05


def wilson_interval(successes: int, trials: int, *, z: float = _Z_95) -> Interval:
    """A confidence interval for a proportion that stays inside 0 to 1.

    Preferred over the normal approximation below a few hundred trials, where the
    approximation produces intervals that are too narrow and, at a perfect score,
    of zero width.
    """
    if trials <= 0:
        raise ValueError("trials must be positive")
    if not 0 <= successes <= trials:
        raise ValueError("successes must be between 0 and trials")

    proportion = successes / trials
    z_squared = z * z
    denominator = 1 + z_squared / trials
    center = (proportion + z_squared / (2 * trials)) / denominator
    spread = (
        z
        * math.sqrt(proportion * (1 - proportion) / trials + z_squared / (4 * trials * trials))
        / denominator
    )
    return Interval(point=proportion, low=max(0.0, center - spread), high=min(1.0, center + spread))


def bootstrap_mean_interval(
    values: Sequence[float],
    *,
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = 0,
    confidence: float = 0.95,
) -> Interval:
    """A percentile interval for the mean of partial-credit scores.

    Scores that are not simply right or wrong — required-field accuracy, F1 — cannot
    use Wilson. Resampling makes no distributional assumption, but it also cannot
    invent information: with eight scenarios the interval is wide, and that width is
    the honest answer rather than a defect to tune away.
    """
    if not values:
        raise ValueError("values must not be empty")
    if not 0 < confidence < 1:
        raise ValueError("confidence must be between 0 and 1")

    point = sum(values) / len(values)
    if len(values) == 1:
        return Interval(point=point, low=point, high=point)

    rng = random.Random(seed)
    size = len(values)
    means = sorted(sum(rng.choice(values) for _ in range(size)) / size for _ in range(resamples))
    tail = (1 - confidence) / 2
    low = means[max(0, math.floor(tail * resamples))]
    high = means[min(resamples - 1, math.ceil((1 - tail) * resamples) - 1)]
    return Interval(point=point, low=low, high=high)


def mcnemar_exact_p(a_only: int, b_only: int) -> float:
    """Two-sided exact p-value for paired binary outcomes.

    Only the scenarios the two models disagree on carry information, so this depends
    on the disagreement counts rather than on how many scenarios ran. Six one-sided
    disagreements reach p < 0.05; five do not.
    """
    if a_only < 0 or b_only < 0:
        raise ValueError("counts must not be negative")

    discordant = a_only + b_only
    if discordant == 0:
        return 1.0

    smaller = min(a_only, b_only)
    tail = sum(math.comb(discordant, i) for i in range(smaller + 1)) * (0.5**discordant)
    return min(1.0, 2 * tail)


def paired_comparison(a_outcomes: Sequence[bool], b_outcomes: Sequence[bool]) -> PairedComparison:
    """Compare two models scenario by scenario, in the order both ran them."""
    if len(a_outcomes) != len(b_outcomes):
        raise ValueError("paired comparison needs one outcome per model per scenario")
    if not a_outcomes:
        raise ValueError("outcomes must not be empty")

    a_only = sum(1 for a, b in zip(a_outcomes, b_outcomes, strict=True) if a and not b)
    b_only = sum(1 for a, b in zip(a_outcomes, b_outcomes, strict=True) if b and not a)
    agreed = len(a_outcomes) - a_only - b_only
    return PairedComparison(
        a_only=a_only,
        b_only=b_only,
        agreed=agreed,
        p_value=mcnemar_exact_p(a_only, b_only),
    )


def minimum_discordant_for_significance(*, alpha: float = 0.05) -> int:
    """How lopsided a disagreement must be before this sample size can show it.

    Reported next to a comparison so a reader can see what the evaluation was capable
    of detecting, rather than reading "no significant difference" as "no difference".
    """
    for discordant in range(1, 101):
        if mcnemar_exact_p(discordant, 0) < alpha:
            return discordant
    raise ValueError("no discordant count below 100 reaches the requested level")
