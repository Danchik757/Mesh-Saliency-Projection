"""
Unit tests for metrics/mesh_space.py.

Covers: normalize_distribution (re-export), auc_visible_top20, map_metrics,
nss_from_positive_indices, auc_from_positive_indices.
"""
from __future__ import annotations

import math
import numpy as np
import pytest

from metrics.mesh_space import (
    normalize_distribution,
    auc_visible_top20,
    map_metrics,
    nss_from_positive_indices,
    auc_from_positive_indices,
)


# ---------------------------------------------------------------------------
# normalize_distribution (re-export, light smoke tests)
# ---------------------------------------------------------------------------

class TestNormalizeDistributionReexport:
    def test_sums_to_one(self):
        result = normalize_distribution(np.array([1.0, 2.0, 3.0]))
        assert result.sum() == pytest.approx(1.0, abs=1e-9)

    def test_mask_returns_subset(self):
        result = normalize_distribution(
            np.array([1.0, 2.0, 3.0, 4.0]),
            mask=np.array([True, False, True, False]),
        )
        assert result.shape == (2,)


# ---------------------------------------------------------------------------
# auc_visible_top20
# ---------------------------------------------------------------------------

class TestAucVisibleTop20:
    def test_perfect_pred_returns_one(self):
        # pred ranking matches GT ranking exactly
        pred = np.array([4.0, 3.0, 2.0, 1.0, 0.5])
        target = np.array([4.0, 3.0, 2.0, 1.0, 0.5])
        visible = np.array([True, True, True, True, True])
        result = auc_visible_top20(pred, target, visible)
        assert result == pytest.approx(1.0, abs=1e-10)

    def test_worst_pred_returns_zero(self):
        # pred is perfectly anti-correlated with GT
        pred = np.array([0.5, 1.0, 2.0, 3.0, 4.0])  # low where GT is high
        target = np.array([4.0, 3.0, 2.0, 1.0, 0.5])
        visible = np.array([True, True, True, True, True])
        result = auc_visible_top20(pred, target, visible)
        assert result == pytest.approx(0.0, abs=1e-10)

    def test_k_is_20_percent_of_visible(self):
        # 10 visible elements → k = 2 (top 20%)
        rng = np.random.default_rng(1)
        n = 10
        pred = rng.uniform(0, 1, n)
        target = rng.uniform(0, 1, n)
        visible = np.ones(n, dtype=bool)
        # Does not crash; k = max(1, round(0.2*10)) = 2
        result = auc_visible_top20(pred, target, visible)
        assert 0.0 <= result <= 1.0

    def test_k_minimum_one(self):
        # 1 visible element → k = max(1, round(0.2*1)) = 1
        # → all positives, no negatives → NaN
        pred = np.array([0.5])
        target = np.array([1.0])
        visible = np.array([True])
        result = auc_visible_top20(pred, target, visible)
        assert math.isnan(result)

    def test_subset_visible_mask(self):
        # only first 4 of 6 elements are visible
        pred = np.array([0.9, 0.8, 0.1, 0.2, 100.0, -100.0])
        target = np.array([1.0, 0.9, 0.1, 0.0, 999.0, -999.0])
        visible = np.array([True, True, True, True, False, False])
        # Uses only first 4 elements; k=max(1, round(0.2*4))=1
        result = auc_visible_top20(pred, target, visible)
        # pred[0]=0.9 is highest and target[0]=1.0 is GT-top → should be 1.0
        assert result == pytest.approx(1.0, abs=1e-10)

    def test_all_same_gt_gives_valid_auc(self):
        # k first elements all tie; AUC still defined if pred varies
        pred = np.array([0.9, 0.1, 0.5, 0.3])
        target = np.array([1.0, 1.0, 1.0, 1.0])  # all identical
        visible = np.ones(4, dtype=bool)
        result = auc_visible_top20(pred, target, visible)
        # k=max(1, round(0.8))=1; ties mean argsort is arbitrary but valid
        assert 0.0 <= result <= 1.0 or math.isnan(result)

    def test_masking_excludes_outlier_values(self):
        # Large values outside the visible mask must NOT affect the result
        pred = np.array([0.9, 0.1, 1000.0])
        target = np.array([1.0, 0.0, 1000.0])
        visible = np.array([True, True, False])
        result = auc_visible_top20(pred, target, visible)
        # k=max(1, round(0.2*2))=1; positive is idx 0 (highest GT); pred[0]=0.9 > pred[1]=0.1
        assert result == pytest.approx(1.0, abs=1e-10)


# ---------------------------------------------------------------------------
# map_metrics
# ---------------------------------------------------------------------------

class TestMapMetrics:
    def test_returns_standard_keys(self):
        pred = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        target = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        result = map_metrics(pred, target)
        assert "CC" in result
        assert "MSE" in result
        assert "Spearman" in result
        assert "SIM" in result

    def test_no_auc_by_default(self):
        pred = np.array([1.0, 2.0, 3.0])
        target = np.array([1.0, 2.0, 3.0])
        result = map_metrics(pred, target)
        assert "AUC_visible_top20" not in result

    def test_auc_visible_top20_requires_mask(self):
        pred = np.array([1.0, 2.0, 3.0])
        target = np.array([1.0, 2.0, 3.0])
        with pytest.raises(ValueError, match="visible_mask is required"):
            map_metrics(pred, target, include_auc_visible_top20=True)

    def test_auc_visible_top20_included_when_requested(self):
        pred = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        target = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        visible = np.ones(5, dtype=bool)
        result = map_metrics(
            pred, target, visible_mask=visible, include_auc_visible_top20=True
        )
        assert "AUC_visible_top20" in result

    def test_mask_restricts_support(self):
        pred = np.array([1.0, 2.0, 100.0, -100.0])
        target = np.array([1.0, 2.0, 0.0, 0.0])
        mask = np.array([True, True, False, False])
        result_masked = map_metrics(pred, target, visible_mask=mask)
        result_full = map_metrics(pred, target)
        assert result_masked["CC"] != result_full["CC"] or math.isnan(
            result_masked["CC"]
        )

    def test_identical_pred_target_cc_one(self):
        arr = np.array([0.1, 0.5, 0.3, 0.8])
        result = map_metrics(arr, arr)
        assert result["CC"] == pytest.approx(1.0, abs=1e-10)
        assert result["MSE"] == pytest.approx(0.0, abs=1e-15)

    def test_custom_kl_key(self):
        pred = np.array([1.0, 2.0, 3.0])
        target = np.array([1.0, 2.0, 3.0])
        result = map_metrics(pred, target, kl_key="KLD")
        assert "KLD" in result


# ---------------------------------------------------------------------------
# nss_from_positive_indices
# ---------------------------------------------------------------------------

class TestNssFromPositiveIndices:
    def test_basic_positive_nss(self):
        pred = np.array([0.0, 0.0, 100.0])
        # fixation at index 2 (the peak)
        result = nss_from_positive_indices(pred, np.array([2]))
        assert result > 0.0

    def test_basic_negative_nss(self):
        pred = np.array([100.0, 0.0, 0.0])
        # fixation at index 2 (the trough)
        result = nss_from_positive_indices(pred, np.array([2]))
        assert result < 0.0

    def test_duplicate_indices_deduplicated(self):
        pred = np.array([0.0, 0.0, 100.0])
        result_dup = nss_from_positive_indices(pred, np.array([2, 2, 2]))
        result_single = nss_from_positive_indices(pred, np.array([2]))
        assert result_dup == pytest.approx(result_single, abs=1e-10)

    def test_empty_indices_returns_nan(self):
        pred = np.array([1.0, 2.0, 3.0])
        result = nss_from_positive_indices(pred, np.array([], dtype=np.int64))
        assert math.isnan(result)

    def test_flat_pred_returns_nan(self):
        pred = np.array([5.0, 5.0, 5.0])
        result = nss_from_positive_indices(pred, np.array([0]))
        assert math.isnan(result)


# ---------------------------------------------------------------------------
# auc_from_positive_indices
# ---------------------------------------------------------------------------

class TestAucFromPositiveIndices:
    def test_perfect_classifier(self):
        # pred has highest values at positive indices
        pred = np.array([0.1, 0.2, 0.9, 0.8])
        positives = np.array([2, 3])  # indices of the two highest pred values
        result = auc_from_positive_indices(pred, positives)
        assert result == pytest.approx(1.0, abs=1e-10)

    def test_worst_classifier(self):
        pred = np.array([0.9, 0.8, 0.1, 0.2])
        positives = np.array([2, 3])  # lowest pred values are positives
        result = auc_from_positive_indices(pred, positives)
        assert result == pytest.approx(0.0, abs=1e-10)

    def test_duplicate_indices_deduplicated(self):
        pred = np.array([0.1, 0.2, 0.9, 0.8])
        result_dup = auc_from_positive_indices(pred, np.array([2, 2, 3, 3]))
        result_single = auc_from_positive_indices(pred, np.array([2, 3]))
        assert result_dup == pytest.approx(result_single, abs=1e-10)

    def test_all_positive_returns_nan(self):
        pred = np.array([0.5, 0.6, 0.7])
        result = auc_from_positive_indices(pred, np.array([0, 1, 2]))
        assert math.isnan(result)

    def test_empty_positives_returns_nan(self):
        pred = np.array([0.5, 0.6, 0.7])
        result = auc_from_positive_indices(pred, np.array([], dtype=np.int64))
        assert math.isnan(result)
