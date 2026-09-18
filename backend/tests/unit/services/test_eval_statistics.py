"""Uncertainty reporting for the small evaluation samples the routing spike runs."""

from __future__ import annotations

import pytest

from app.services.eval_statistics import (
    Interval,
    bootstrap_mean_interval,
    mcnemar_exact_p,
    minimum_discordant_for_significance,
    paired_comparison,
    wilson_interval,
)


class TestWilsonInterval:
    def test_a_perfect_small_sample_is_not_certainty(self) -> None:
        """Eight of eight is consistent with a true accuracy near two thirds."""
        interval = wilson_interval(8, 8)

        assert interval.point == 1.0
        assert interval.low == pytest.approx(0.676, abs=0.002)
        assert interval.high == 1.0

    def test_more_scenarios_narrow_the_interval(self) -> None:
        assert wilson_interval(28, 28).width < wilson_interval(8, 8).width

    def test_stays_inside_zero_to_one(self) -> None:
        for successes, trials in ((0, 8), (8, 8), (1, 30), (29, 30)):
            interval = wilson_interval(successes, trials)
            assert 0.0 <= interval.low <= interval.high <= 1.0

    def test_never_collapses_to_zero_width_at_the_boundary(self) -> None:
        """The normal approximation reports no uncertainty here, which is wrong."""
        assert wilson_interval(10, 10).width > 0.2
        assert wilson_interval(0, 10).width > 0.2

    def test_rejects_impossible_counts(self) -> None:
        with pytest.raises(ValueError):
            wilson_interval(9, 8)
        with pytest.raises(ValueError):
            wilson_interval(0, 0)


class TestBootstrapMeanInterval:
    def test_covers_the_mean_of_partial_credit_scores(self) -> None:
        scores = [1.0, 0.8, 0.6, 1.0, 0.4, 0.9, 1.0, 0.7]

        interval = bootstrap_mean_interval(scores)

        assert interval.low < interval.point < interval.high
        assert interval.point == pytest.approx(sum(scores) / len(scores))

    def test_is_reproducible_across_runs(self) -> None:
        scores = [0.5, 0.9, 0.3, 1.0, 0.75]

        assert bootstrap_mean_interval(scores) == bootstrap_mean_interval(scores)

    def test_identical_scores_give_no_spread(self) -> None:
        interval = bootstrap_mean_interval([0.5] * 6)

        assert interval.low == interval.high == pytest.approx(0.5)

    def test_rejects_an_empty_sample(self) -> None:
        with pytest.raises(ValueError):
            bootstrap_mean_interval([])


class TestPairedComparison:
    def test_six_one_sided_disagreements_are_significant(self) -> None:
        """The smallest difference this sample size can actually demonstrate."""
        assert mcnemar_exact_p(6, 0) == pytest.approx(0.03125)
        assert mcnemar_exact_p(6, 0) < 0.05

    def test_five_are_not(self) -> None:
        assert mcnemar_exact_p(5, 0) == pytest.approx(0.0625)
        assert mcnemar_exact_p(5, 0) > 0.05

    def test_agreement_carries_no_evidence(self) -> None:
        assert mcnemar_exact_p(0, 0) == 1.0

    def test_balanced_disagreement_is_not_a_difference(self) -> None:
        assert mcnemar_exact_p(7, 7) == 1.0

    def test_counts_disagreements_scenario_by_scenario(self) -> None:
        better = [True, True, True, False, True]
        worse = [False, False, True, False, False]

        result = paired_comparison(better, worse)

        assert (result.a_only, result.b_only, result.agreed) == (3, 0, 2)
        assert result.discordant == 3
        assert not result.significant

    def test_finds_a_difference_that_aggregate_scores_would_hide(self) -> None:
        """Both models answer 22 of 28, but they fail on different scenarios."""
        a_outcomes = [True] * 22 + [False] * 6
        b_outcomes = [True] * 16 + [False] * 6 + [True] * 6

        result = paired_comparison(a_outcomes, b_outcomes)

        assert sum(a_outcomes) == sum(b_outcomes)
        assert (result.a_only, result.b_only) == (6, 6)
        assert not result.significant

    def test_rejects_unpaired_input(self) -> None:
        with pytest.raises(ValueError):
            paired_comparison([True, False], [True])

    def test_reports_what_the_sample_size_could_detect(self) -> None:
        assert minimum_discordant_for_significance() == 6


class TestIntervalFormatting:
    def test_renders_as_a_percentage_range(self) -> None:
        assert Interval(0.84, 0.62, 0.95).format() == "84% (62-95%)"

    def test_renders_partial_credit_on_its_own_scale(self) -> None:
        assert Interval(0.84, 0.62, 0.95).format(percent=False) == "0.84 (0.62-0.95)"
