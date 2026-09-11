"""Statistical primitives.

Each estimator is checked against a closed-form or textbook value rather than a golden
snapshot, so the tests document the intended semantics.
"""

from __future__ import annotations

import math

import pytest

from netlab.core import metrics


class TestConcentration:
    def test_gini_perfect_equality_is_zero(self):
        assert metrics.gini([5, 5, 5, 5]) == 0.0

    def test_gini_rises_with_inequality(self):
        assert metrics.gini([1, 1, 1, 97]) > metrics.gini([20, 25, 25, 30])

    def test_gini_handles_empty_and_zero(self):
        assert metrics.gini([]) == 0.0
        assert metrics.gini([0, 0]) == 0.0

    def test_hhi_single_entity_is_one(self):
        assert metrics.hhi([10]) == 1.0

    def test_hhi_uniform_is_zero_after_normalization(self):
        assert metrics.hhi([4, 4, 4, 4]) == 0.0

    def test_top_k_share_bounds(self):
        assert metrics.top_k_share([1] * 20, 10) == 0.5
        assert metrics.top_k_share([1, 2, 3], 10) == 1.0


class TestDiversity:
    def test_entropy_of_uniform_equals_log_n(self):
        assert metrics.shannon_entropy([1, 1, 1, 1]) == pytest.approx(math.log(4), abs=1e-3)

    def test_entropy_of_singleton_is_zero(self):
        assert metrics.shannon_entropy([7]) == 0.0

    def test_evenness_is_bounded(self):
        assert metrics.pielou_evenness([1, 1, 1, 1]) == pytest.approx(1.0, abs=1e-3)
        assert 0 <= metrics.pielou_evenness([90, 5, 3, 2]) <= 1

    def test_effective_count_matches_category_count_when_uniform(self):
        assert metrics.effective_count([3, 3, 3]) == pytest.approx(3.0, abs=0.01)

    def test_effective_count_below_raw_count_when_skewed(self):
        assert metrics.effective_count([100, 1, 1, 1]) < 4


class TestTailFitting:
    def test_alpha_none_for_thin_samples(self):
        assert metrics.powerlaw_alpha([1, 2, 3]) is None

    def test_alpha_positive_for_heavy_tail(self):
        sizes = [1] * 50 + [2] * 20 + [5] * 6 + [30]
        alpha = metrics.powerlaw_alpha(sizes)
        assert alpha is not None and alpha > 1


class TestDispersionAndFit:
    def test_median_even_and_odd(self):
        assert metrics.median([1, 3]) == 2
        assert metrics.median([1, 2, 3]) == 2

    def test_modified_z_flags_the_spike(self):
        zs = metrics.modified_zscores([2, 2, 3, 2, 40, 2, 3])
        assert max(zs) > 3.5
        assert zs.index(max(zs)) == 4

    def test_modified_z_handles_zero_dispersion(self):
        assert metrics.modified_zscores([5, 5, 5]) == [0.0, 0.0, 0.0]

    def test_ols_recovers_a_known_line(self):
        slope, intercept, r2 = metrics.ols_slope([1, 2, 3, 4], [3, 5, 7, 9])
        assert slope == pytest.approx(2.0, abs=1e-6)
        assert intercept == pytest.approx(1.0, abs=1e-6)
        assert r2 == pytest.approx(1.0, abs=1e-6)

    def test_ols_degenerate_input(self):
        assert metrics.ols_slope([1], [1]) == (0.0, 0.0, 0.0)

    def test_percentile_interpolates(self):
        assert metrics.percentile([1, 2, 3, 4], 50) == pytest.approx(2.5)
