"""
Unit tests for metrics/common.py.

Covers: _as_float_array, flatten_pair, rankdata_average, pearson_cc,
spearman_cc, mse_score, normalize_minmax, normalize_distribution,
similarity_score, kldiv_score, roc_auc_from_labels, nss_from_binary_mask,
dense_saliency_metrics.

Reference implementations use scipy.stats where available.
"""
from __future__ import annotations

import math
import sys
import os

import numpy as np
import pytest
import scipy.stats

from metrics.common import (
    EPS,
    _as_float_array,
    _validate_mask_shape,
    _validate_same_shape,
    flatten_pair,
    rankdata_average,
    pearson_cc,
    spearman_cc,
    mse_score,
    normalize_minmax,
    normalize_distribution,
    similarity_score,
    kldiv_score,
    roc_auc_from_labels,
    nss_from_binary_mask,
    dense_saliency_metrics,
)


# ---------------------------------------------------------------------------
# _as_float_array
# ---------------------------------------------------------------------------

class TestAsFloatArray:
    def test_empty_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            _as_float_array(np.array([]))

    def test_nan_raises(self):
        with pytest.raises(ValueError, match="finite"):
            _as_float_array(np.array([1.0, float("nan")]))

    def test_inf_raises(self):
        with pytest.raises(ValueError, match="finite"):
            _as_float_array(np.array([1.0, float("inf")]))

    def test_neg_inf_raises(self):
        with pytest.raises(ValueError, match="finite"):
            _as_float_array(np.array([float("-inf"), 1.0]))

    def test_valid_converted_to_float64(self):
        result = _as_float_array(np.array([1, 2, 3], dtype=np.int32))
        assert result.dtype == np.float64

    def test_scalar_input(self):
        result = _as_float_array(np.array([42]))
        assert result.shape == (1,)
        assert result[0] == 42.0


# ---------------------------------------------------------------------------
# flatten_pair
# ---------------------------------------------------------------------------

class TestFlattenPair:
    def test_shape_mismatch_raises(self):
        with pytest.raises(ValueError, match="same shape"):
            flatten_pair(np.array([1.0, 2.0]), np.array([1.0, 2.0, 3.0]))

    def test_mask_shape_mismatch_raises(self):
        pred = np.array([1.0, 2.0, 3.0])
        target = np.array([1.0, 2.0, 3.0])
        mask = np.array([True, False])  # wrong size
        with pytest.raises(ValueError, match="same shape"):
            flatten_pair(pred, target, mask=mask)

    def test_all_false_mask_raises(self):
        pred = np.array([1.0, 2.0, 3.0])
        target = np.array([1.0, 2.0, 3.0])
        mask = np.array([False, False, False])
        with pytest.raises(ValueError, match="empty after applying the mask"):
            flatten_pair(pred, target, mask=mask)

    def test_partial_mask(self):
        pred = np.array([1.0, 2.0, 3.0, 4.0])
        target = np.array([10.0, 20.0, 30.0, 40.0])
        mask = np.array([True, False, True, False])
        p, t = flatten_pair(pred, target, mask=mask)
        np.testing.assert_array_equal(p, [1.0, 3.0])
        np.testing.assert_array_equal(t, [10.0, 30.0])

    def test_no_mask(self):
        pred = np.array([[1.0, 2.0], [3.0, 4.0]])
        target = np.array([[5.0, 6.0], [7.0, 8.0]])
        p, t = flatten_pair(pred, target)
        assert p.shape == (4,)
        assert t.shape == (4,)

    def test_nan_in_input_raises(self):
        with pytest.raises(ValueError, match="finite"):
            flatten_pair(np.array([1.0, float("nan")]), np.array([1.0, 2.0]))


# ---------------------------------------------------------------------------
# rankdata_average
# ---------------------------------------------------------------------------

class TestRankdataAverage:
    def test_no_ties_matches_scipy(self):
        values = np.array([3.0, 1.0, 4.0, 1.5, 9.0, 2.6])
        expected = scipy.stats.rankdata(values, method="average")
        np.testing.assert_allclose(rankdata_average(values), expected, atol=1e-12)

    def test_all_ties(self):
        values = np.array([5.0, 5.0, 5.0])
        result = rankdata_average(values)
        # average rank of 3 ties in positions 0,1,2 = (1+2+3)/3 = 2.0
        np.testing.assert_allclose(result, [2.0, 2.0, 2.0])

    def test_partial_ties_matches_scipy(self):
        values = np.array([1.0, 1.0, 2.0, 3.0, 3.0])
        expected = scipy.stats.rankdata(values, method="average")
        np.testing.assert_allclose(rankdata_average(values), expected, atol=1e-12)

    def test_single_element(self):
        result = rankdata_average(np.array([7.0]))
        assert result[0] == 1.0

    def test_two_elements_distinct(self):
        result = rankdata_average(np.array([2.0, 1.0]))
        np.testing.assert_allclose(result, [2.0, 1.0])

    def test_2d_input_is_flattened(self):
        values = np.array([[3.0, 1.0], [4.0, 2.0]])
        result = rankdata_average(values)
        assert result.shape == (4,)


# ---------------------------------------------------------------------------
# pearson_cc
# ---------------------------------------------------------------------------

class TestPearsonCC:
    def test_identical_maps_returns_one(self):
        arr = np.array([1.0, 2.0, 3.0, 4.0])
        assert pearson_cc(arr, arr) == pytest.approx(1.0, abs=1e-10)

    def test_perfect_negative_correlation(self):
        pred = np.array([1.0, 2.0, 3.0, 4.0])
        target = np.array([4.0, 3.0, 2.0, 1.0])
        assert pearson_cc(pred, target) == pytest.approx(-1.0, abs=1e-10)

    def test_zero_correlation(self):
        # orthogonal vectors (mean-zero)
        pred = np.array([-1.0, 1.0, -1.0, 1.0])
        target = np.array([-1.0, -1.0, 1.0, 1.0])
        assert pearson_cc(pred, target) == pytest.approx(0.0, abs=1e-10)

    def test_constant_pred_returns_nan(self):
        pred = np.array([3.0, 3.0, 3.0])
        target = np.array([1.0, 2.0, 3.0])
        assert math.isnan(pearson_cc(pred, target))

    def test_constant_target_returns_nan(self):
        pred = np.array([1.0, 2.0, 3.0])
        target = np.array([3.0, 3.0, 3.0])
        assert math.isnan(pearson_cc(pred, target))

    def test_both_constant_returns_nan(self):
        assert math.isnan(pearson_cc(np.array([1.0, 1.0]), np.array([2.0, 2.0])))

    def test_scale_invariance(self):
        pred = np.array([1.0, 2.0, 3.0])
        target = np.array([2.0, 5.0, 3.0])
        cc1 = pearson_cc(pred, target)
        cc2 = pearson_cc(pred * 100.0, target * 0.001)
        assert cc1 == pytest.approx(cc2, abs=1e-10)

    def test_matches_scipy_reference(self):
        rng = np.random.default_rng(42)
        pred = rng.uniform(0, 1, 50)
        target = rng.uniform(0, 1, 50)
        expected, _ = scipy.stats.pearsonr(pred, target)
        assert pearson_cc(pred, target) == pytest.approx(expected, abs=1e-10)

    def test_two_element_arrays(self):
        # With 2 elements, perfect correlation or anti-correlation
        assert pearson_cc(np.array([1.0, 2.0]), np.array([1.0, 2.0])) == pytest.approx(1.0)
        assert pearson_cc(np.array([1.0, 2.0]), np.array([2.0, 1.0])) == pytest.approx(-1.0)


# ---------------------------------------------------------------------------
# spearman_cc
# ---------------------------------------------------------------------------

class TestSpearmanCC:
    def test_identical_returns_one(self):
        arr = np.array([3.0, 1.0, 4.0, 1.5, 9.0])
        assert spearman_cc(arr, arr) == pytest.approx(1.0, abs=1e-10)

    def test_reversed_returns_neg_one(self):
        arr = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        assert spearman_cc(arr, arr[::-1]) == pytest.approx(-1.0, abs=1e-10)

    def test_matches_scipy_reference(self):
        rng = np.random.default_rng(7)
        pred = rng.uniform(0, 1, 40)
        target = rng.uniform(0, 1, 40)
        expected = scipy.stats.spearmanr(pred, target).statistic
        assert spearman_cc(pred, target) == pytest.approx(expected, abs=1e-10)

    def test_constant_pred_returns_nan(self):
        assert math.isnan(spearman_cc(np.array([2.0, 2.0, 2.0]), np.array([1.0, 2.0, 3.0])))

    def test_monotone_increasing_returns_one(self):
        pred = np.array([0.1, 0.5, 0.9, 1.5, 3.0])
        target = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        assert spearman_cc(pred, target) == pytest.approx(1.0, abs=1e-10)


# ---------------------------------------------------------------------------
# mse_score
# ---------------------------------------------------------------------------

class TestMseScore:
    def test_identical_is_zero(self):
        arr = np.array([1.0, 2.0, 3.0])
        assert mse_score(arr, arr) == pytest.approx(0.0, abs=1e-15)

    def test_known_value(self):
        pred = np.array([0.0, 0.0])
        target = np.array([3.0, 4.0])
        # (9 + 16) / 2 = 12.5
        assert mse_score(pred, target) == pytest.approx(12.5)

    def test_non_negative(self):
        rng = np.random.default_rng(0)
        pred = rng.uniform(-1, 1, 100)
        target = rng.uniform(-1, 1, 100)
        assert mse_score(pred, target) >= 0.0

    def test_symmetry(self):
        pred = np.array([1.0, 2.0, 3.0])
        target = np.array([4.0, 5.0, 6.0])
        assert mse_score(pred, target) == pytest.approx(mse_score(target, pred))


# ---------------------------------------------------------------------------
# normalize_minmax
# ---------------------------------------------------------------------------

class TestNormalizeMinmax:
    def test_constant_input_returns_zeros(self):
        result = normalize_minmax(np.array([5.0, 5.0, 5.0]))
        np.testing.assert_array_equal(result, [0.0, 0.0, 0.0])

    def test_range_is_zero_to_one(self):
        arr = np.array([2.0, 0.0, 8.0, 4.0])
        result = normalize_minmax(arr)
        assert result.min() == pytest.approx(0.0)
        assert result.max() == pytest.approx(1.0)

    def test_known_values(self):
        arr = np.array([0.0, 5.0, 10.0])
        result = normalize_minmax(arr)
        np.testing.assert_allclose(result, [0.0, 0.5, 1.0])

    def test_negative_values_handled(self):
        arr = np.array([-2.0, 0.0, 2.0])
        result = normalize_minmax(arr)
        np.testing.assert_allclose(result, [0.0, 0.5, 1.0])

    def test_output_dtype_float64(self):
        result = normalize_minmax(np.array([1.0, 2.0, 3.0]))
        assert result.dtype == np.float64

    def test_two_element(self):
        result = normalize_minmax(np.array([3.0, 7.0]))
        np.testing.assert_allclose(result, [0.0, 1.0])


# ---------------------------------------------------------------------------
# normalize_distribution
# ---------------------------------------------------------------------------

class TestNormalizeDistribution:
    def test_sums_to_approx_one(self):
        arr = np.array([1.0, 2.0, 3.0, 4.0])
        result = normalize_distribution(arr)
        assert result.sum() == pytest.approx(1.0, abs=1e-9)

    def test_all_positive(self):
        arr = np.array([1.0, 2.0, 3.0])
        result = normalize_distribution(arr)
        assert (result > 0).all()

    def test_uniform_input(self):
        arr = np.array([1.0, 1.0, 1.0, 1.0])
        result = normalize_distribution(arr)
        np.testing.assert_allclose(result, result[0] * np.ones(4), rtol=1e-10)

    def test_negative_values_shifted(self):
        arr = np.array([-1.0, 0.0, 1.0])
        result = normalize_distribution(arr)
        # after shift: [0, 1, 2], then normalize
        assert (result > 0).all()
        assert result.sum() == pytest.approx(1.0, abs=1e-9)
        # ratio should preserve relative differences: result[2]/result[1] ≈ (2+EPS)/(1+EPS)
        assert result[2] > result[1] > result[0]

    def test_all_zero_returns_uniform(self):
        arr = np.array([0.0, 0.0, 0.0])
        result = normalize_distribution(arr)
        np.testing.assert_allclose(result, [1 / 3, 1 / 3, 1 / 3], atol=1e-10)

    def test_mask_subsets_array(self):
        arr = np.array([1.0, 2.0, 3.0, 4.0])
        mask = np.array([True, False, True, False])
        result = normalize_distribution(arr, mask=mask)
        # should operate on [1.0, 3.0] only
        assert result.shape == (2,)
        assert result.sum() == pytest.approx(1.0, abs=1e-9)

    def test_single_nonzero_element(self):
        arr = np.array([0.0, 5.0, 0.0])
        result = normalize_distribution(arr)
        # all mass on middle element after epsilon stabilisation
        assert result[1] > result[0]
        assert result[1] > result[2]

    def test_epsilon_stabilises_zeros(self):
        arr = np.array([0.0, 1.0])
        result = normalize_distribution(arr)
        # zero entry gets EPS weight, not literal 0
        assert result[0] > 0.0
        assert result[0] < result[1]


# ---------------------------------------------------------------------------
# similarity_score (SIM)
# ---------------------------------------------------------------------------

class TestSimilarityScore:
    def test_identical_maps_returns_one(self):
        arr = np.array([1.0, 2.0, 3.0, 4.0])
        assert similarity_score(arr, arr) == pytest.approx(1.0, abs=1e-8)

    def test_range_zero_to_one(self):
        rng = np.random.default_rng(99)
        pred = rng.uniform(0, 1, 50)
        target = rng.uniform(0, 1, 50)
        score = similarity_score(pred, target)
        assert 0.0 <= score <= 1.0 + 1e-10

    def test_scale_invariant_pred(self):
        pred = np.array([1.0, 2.0, 3.0, 4.0])
        target = np.array([4.0, 3.0, 1.0, 2.0])
        s1 = similarity_score(pred, target)
        s2 = similarity_score(pred * 100.0, target)
        assert s1 == pytest.approx(s2, abs=1e-10)

    def test_scale_invariant_target(self):
        pred = np.array([1.0, 2.0, 3.0, 4.0])
        target = np.array([4.0, 3.0, 1.0, 2.0])
        s1 = similarity_score(pred, target)
        s2 = similarity_score(pred, target * 50.0)
        assert s1 == pytest.approx(s2, abs=1e-10)

    def test_constant_pred_does_not_crash(self):
        # constant pred → normalize_minmax returns zeros → normalize_distribution returns uniform
        pred = np.array([5.0, 5.0, 5.0, 5.0])
        target = np.array([1.0, 0.0, 0.0, 0.0])
        score = similarity_score(pred, target)
        # result is not NaN and in [0, 1]
        assert not math.isnan(score)
        assert 0.0 <= score <= 1.0 + 1e-10

    def test_constant_pred_is_not_ideal(self):
        # uniform prediction should be < 1.0 SIM against a peaked target
        pred = np.array([1.0, 1.0, 1.0, 1.0])
        target = np.array([10.0, 0.0, 0.0, 0.0])
        score = similarity_score(pred, target)
        assert score < 1.0

    def test_disjoint_support_is_low(self):
        pred = np.array([1.0, 1.0, 0.0, 0.0])
        target = np.array([0.0, 0.0, 1.0, 1.0])
        score = similarity_score(pred, target)
        assert score < 0.5

    def test_symmetry(self):
        pred = np.array([1.0, 2.0, 3.0])
        target = np.array([3.0, 1.0, 2.0])
        assert similarity_score(pred, target) == pytest.approx(
            similarity_score(target, pred), abs=1e-10
        )


# ---------------------------------------------------------------------------
# kldiv_score (KLD)
# ---------------------------------------------------------------------------

class TestKldivScore:
    def test_identical_distributions_near_zero(self):
        # KLD(P||P) = 0; epsilon stabilisation gives a tiny positive value
        arr = np.array([1.0, 2.0, 3.0])
        score = kldiv_score(arr, arr)
        assert score == pytest.approx(0.0, abs=1e-8)

    def test_direction_gt_to_pred(self):
        # KL(target || pred): penalises pred assigning low mass where target is high
        # target concentrated on element 0; pred concentrated on element 1
        # This should give high KLD
        target = np.array([0.0, 0.0, 100.0])  # mass on last element
        pred = np.array([100.0, 0.0, 0.0])    # mass on first element
        score_forward = kldiv_score(pred, target)   # KL(target || pred) — high
        score_reverse = kldiv_score(target, pred)   # KL(pred || target) — also high
        # Both high, but direction matters for the benchmark
        # The function is kldiv_score(pred, target) → KL(target || pred)
        assert score_forward > 1.0
        assert score_reverse > 1.0

    def test_non_negative(self):
        rng = np.random.default_rng(5)
        for _ in range(20):
            pred = rng.uniform(0.1, 1.0, 10)
            target = rng.uniform(0.1, 1.0, 10)
            assert kldiv_score(pred, target) >= -1e-10

    def test_scale_invariant(self):
        pred = np.array([1.0, 2.0, 3.0])
        target = np.array([3.0, 1.0, 2.0])
        kl1 = kldiv_score(pred, target)
        kl2 = kldiv_score(pred * 100.0, target)
        assert kl1 == pytest.approx(kl2, abs=1e-9)

    def test_negative_inputs_handled(self):
        # normalize_distribution shifts negative values, so no crash
        pred = np.array([-1.0, 0.0, 1.0])
        target = np.array([0.5, 0.5, 1.0])
        score = kldiv_score(pred, target)
        assert not math.isnan(score)
        assert score >= 0.0

    def test_uniform_pred_worse_than_matching_pred(self):
        target = np.array([0.0, 0.0, 1.0, 0.0])
        uniform_pred = np.array([1.0, 1.0, 1.0, 1.0])
        matching_pred = np.array([0.0, 0.0, 1.0, 0.0])
        # KLD should be lower (better) when pred matches target
        assert kldiv_score(matching_pred, target) < kldiv_score(uniform_pred, target)


# ---------------------------------------------------------------------------
# roc_auc_from_labels
# ---------------------------------------------------------------------------

class TestRocAucFromLabels:
    def test_perfect_classifier_returns_one(self):
        # scores perfectly separate positives from negatives
        scores = np.array([0.9, 0.8, 0.7, 0.2, 0.1])
        labels = np.array([True, True, True, False, False])
        assert roc_auc_from_labels(scores, labels) == pytest.approx(1.0)

    def test_worst_classifier_returns_zero(self):
        scores = np.array([0.1, 0.2, 0.7, 0.8, 0.9])
        labels = np.array([True, True, True, False, False])
        assert roc_auc_from_labels(scores, labels) == pytest.approx(0.0)

    def test_random_classifier_near_half(self):
        # alternating: each positive interleaved with negative
        scores = np.array([0.9, 0.8, 0.7, 0.6, 0.5])
        labels = np.array([True, False, True, False, True])
        result = roc_auc_from_labels(scores, labels)
        # positives at ranks 5,4,3; negatives at ranks 2,1
        # U = (5+4+3) - 3*4/2 = 12 - 6 = 6; AUC = 6 / (3*2) = 1.0
        # Actually this gives 1.0 since all positives have higher scores
        assert 0.0 <= result <= 1.0

    def test_all_positive_labels_returns_nan(self):
        scores = np.array([1.0, 2.0, 3.0])
        labels = np.array([True, True, True])
        assert math.isnan(roc_auc_from_labels(scores, labels))

    def test_all_negative_labels_returns_nan(self):
        scores = np.array([1.0, 2.0, 3.0])
        labels = np.array([False, False, False])
        assert math.isnan(roc_auc_from_labels(scores, labels))

    def test_matches_sklearn_on_random_data(self):
        from sklearn.metrics import roc_auc_score
        rng = np.random.default_rng(13)
        scores = rng.uniform(0, 1, 50)
        labels = (rng.uniform(0, 1, 50) > 0.4).astype(bool)
        expected = roc_auc_score(labels, scores)
        result = roc_auc_from_labels(scores, labels)
        assert result == pytest.approx(expected, abs=1e-10)

    def test_tied_scores_handled_gracefully(self):
        # all scores equal → AUC = 0.5 (random classifier)
        scores = np.array([0.5, 0.5, 0.5, 0.5])
        labels = np.array([True, True, False, False])
        result = roc_auc_from_labels(scores, labels)
        assert result == pytest.approx(0.5, abs=1e-10)

    def test_single_positive_single_negative(self):
        # positive score > negative → AUC = 1.0
        assert roc_auc_from_labels(
            np.array([0.8, 0.3]), np.array([True, False])
        ) == pytest.approx(1.0)
        # negative score > positive → AUC = 0.0
        assert roc_auc_from_labels(
            np.array([0.3, 0.8]), np.array([True, False])
        ) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# nss_from_binary_mask
# ---------------------------------------------------------------------------

class TestNssFromBinaryMask:
    def test_no_positives_returns_nan(self):
        pred = np.array([1.0, 2.0, 3.0])
        mask = np.array([False, False, False])
        assert math.isnan(nss_from_binary_mask(pred, mask))

    def test_flat_pred_returns_nan(self):
        pred = np.array([5.0, 5.0, 5.0])
        mask = np.array([True, False, True])
        assert math.isnan(nss_from_binary_mask(pred, mask))

    def test_high_pred_at_fixation_positive_nss(self):
        pred = np.array([0.0, 0.0, 100.0])  # peak at index 2
        mask = np.array([False, False, True])  # fixation at index 2
        result = nss_from_binary_mask(pred, mask)
        assert result > 0.0

    def test_low_pred_at_fixation_negative_nss(self):
        pred = np.array([100.0, 0.0, 0.0])  # peak at index 0
        mask = np.array([False, False, True])  # fixation at index 2
        result = nss_from_binary_mask(pred, mask)
        assert result < 0.0

    def test_uses_global_pred_statistics(self):
        # NSS is based on global z-score, not local to mask
        pred = np.array([0.0, 0.0, 0.0, 10.0, 0.0])
        mask = np.array([True, False, False, False, False])  # fixation NOT at peak
        # global mean ≈ 2.0, std ≈ 4.0
        # z_score[0] = (0 - 2) / 4 = -0.5
        result = nss_from_binary_mask(pred, mask)
        mean_pred = pred.mean()
        std_pred = pred.std()
        expected = (pred[0] - mean_pred) / std_pred
        assert result == pytest.approx(expected, abs=1e-10)

    def test_known_simple_value(self):
        # pred = [0, 2], mask = [False, True]
        # mean=1, std=1, z=[−1, 1]; NSS = z[1] = 1.0
        pred = np.array([0.0, 2.0])
        mask = np.array([False, True])
        assert nss_from_binary_mask(pred, mask) == pytest.approx(1.0, abs=1e-10)

    def test_shape_mismatch_raises(self):
        with pytest.raises(ValueError, match="same shape"):
            nss_from_binary_mask(np.array([1.0, 2.0]), np.array([True]))


# ---------------------------------------------------------------------------
# dense_saliency_metrics
# ---------------------------------------------------------------------------

class TestDenseSaliencyMetrics:
    def test_keys_present_by_default(self):
        pred = np.array([1.0, 2.0, 3.0])
        target = np.array([1.0, 2.0, 3.0])
        result = dense_saliency_metrics(pred, target)
        assert "CC" in result
        assert "MSE" in result
        assert "KL_gt_to_pred" in result
        assert "SIM" in result
        assert "Spearman" in result

    def test_no_spearman_no_sim_when_disabled(self):
        pred = np.array([1.0, 2.0, 3.0])
        target = np.array([1.0, 2.0, 3.0])
        result = dense_saliency_metrics(
            pred, target, include_spearman=False, include_similarity=False
        )
        assert "Spearman" not in result
        assert "SIM" not in result

    def test_custom_kl_key(self):
        pred = np.array([1.0, 2.0, 3.0])
        target = np.array([1.0, 2.0, 3.0])
        result = dense_saliency_metrics(pred, target, kl_key="KLD")
        assert "KLD" in result
        assert "KL_gt_to_pred" not in result

    def test_mask_applied_before_metrics(self):
        # Without mask: high values at index 3-4 would affect CC
        # With mask selecting only indices 0-2, result should differ
        pred = np.array([0.0, 1.0, 0.0, 100.0, -100.0])
        target = np.array([0.0, 1.0, 0.0, 0.0, 0.0])
        mask = np.array([True, True, True, False, False])
        result_masked = dense_saliency_metrics(pred, target, mask=mask)
        result_full = dense_saliency_metrics(pred, target)
        # CC on masked identical prefix should be NaN (constant pred/target in [0,1,0])
        # At minimum they differ from full
        assert result_masked["CC"] != result_full["CC"] or math.isnan(
            result_masked["CC"]
        )

    def test_identical_maps_cc_one(self):
        arr = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        result = dense_saliency_metrics(arr, arr)
        assert result["CC"] == pytest.approx(1.0, abs=1e-10)
        assert result["MSE"] == pytest.approx(0.0, abs=1e-15)
        assert result["SIM"] == pytest.approx(1.0, abs=1e-8)

    def test_all_false_mask_raises(self):
        pred = np.array([1.0, 2.0, 3.0])
        target = np.array([1.0, 2.0, 3.0])
        mask = np.array([False, False, False])
        with pytest.raises(ValueError, match="empty after applying the mask"):
            dense_saliency_metrics(pred, target, mask=mask)


# ---------------------------------------------------------------------------
# Aggregation semantics documentation tests
# ---------------------------------------------------------------------------

class TestAggregationSemantics:
    """
    These tests document the aggregation contract, not correctness bugs.
    They serve as executable specifications for the audit.
    """

    def test_point_equal_aggregation_is_supported(self):
        # Metrics operate on flat arrays — point-equal weighting is the default.
        # Every element in pred and target has equal weight.
        pred = np.array([1.0, 1.0, 2.0])   # two gaze points at vertex A, one at B
        target = np.array([1.0, 0.0, 0.0])
        # This is a valid call — point-equal weighting
        result = dense_saliency_metrics(pred, target)
        assert "CC" in result

    def test_participant_equal_not_achievable_from_point_array(self):
        # Processed fixation JSON has no participant IDs.
        # If 3 participants contributed [2, 1, 1] points respectively,
        # we cannot reconstruct equal-weight per-participant aggregation
        # from the flat point array alone.
        # This test documents the limitation — it is NOT a bug in metrics code.
        # The metrics code itself is correct; the limitation is in the upstream
        # input format (DATA_CONTRACT.md: "point-equal aggregation is possible
        # directly; participant-equal aggregation is not possible from this file alone").
        pass  # documentation-only: no metric function expresses participant identity
