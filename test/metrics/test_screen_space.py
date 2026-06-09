"""
Unit tests for metrics/screen_space.py.

Covers: cc_from_maps, sim_from_maps, kld_from_maps, mse_from_maps,
binary_mask_from_fixation_points, nss_from_fixation_points,
auc_from_binary_mask, screen_map_metrics.
"""
from __future__ import annotations

import math
import numpy as np
import pytest

from metrics.screen_space import (
    cc_from_maps,
    sim_from_maps,
    kld_from_maps,
    mse_from_maps,
    binary_mask_from_fixation_points,
    nss_from_fixation_points,
    auc_from_binary_mask,
    screen_map_metrics,
)


# ---------------------------------------------------------------------------
# Thin wrapper smoke tests (cc, sim, kld, mse)
# ---------------------------------------------------------------------------

class TestThinWrappers:
    def test_cc_identical_is_one(self):
        arr = np.array([1.0, 2.0, 3.0])
        assert cc_from_maps(arr, arr) == pytest.approx(1.0, abs=1e-10)

    def test_sim_identical_is_one(self):
        arr = np.array([1.0, 2.0, 3.0])
        assert sim_from_maps(arr, arr) == pytest.approx(1.0, abs=1e-8)

    def test_kld_identical_near_zero(self):
        arr = np.array([1.0, 2.0, 3.0])
        assert kld_from_maps(arr, arr) == pytest.approx(0.0, abs=1e-8)

    def test_mse_identical_is_zero(self):
        arr = np.array([1.0, 2.0, 3.0])
        assert mse_from_maps(arr, arr) == pytest.approx(0.0, abs=1e-15)


# ---------------------------------------------------------------------------
# binary_mask_from_fixation_points
# ---------------------------------------------------------------------------

class TestBinaryMaskFromFixationPoints:
    def test_single_point_in_bounds(self):
        # shape=(4,6) → height=4, width=6; point (x=2, y=1) → row=1, col=2
        mask = binary_mask_from_fixation_points((4, 6), [(2, 1)])
        assert mask[1, 2] == 1
        assert mask.sum() == 1

    def test_out_of_bounds_points_filtered(self):
        mask = binary_mask_from_fixation_points((4, 6), [(-1, 0), (6, 0), (0, 4), (0, -1)])
        assert mask.sum() == 0

    def test_x_is_column_y_is_row(self):
        # Verify coordinate convention: x = column index, y = row index
        mask = binary_mask_from_fixation_points((10, 10), [(3, 7)])
        # Should be set at row=7, col=3
        assert mask[7, 3] == 1
        assert mask[3, 7] == 0

    def test_duplicate_points_set_once(self):
        mask = binary_mask_from_fixation_points((5, 5), [(2, 2), (2, 2), (2, 2)])
        assert mask[2, 2] == 1
        assert mask.sum() == 1

    def test_border_points_included(self):
        mask = binary_mask_from_fixation_points((4, 6), [(0, 0), (5, 3)])
        # (x=0, y=0) → row=0, col=0; (x=5, y=3) → row=3, col=5
        assert mask[0, 0] == 1
        assert mask[3, 5] == 1

    def test_empty_fixation_list_gives_zero_mask(self):
        mask = binary_mask_from_fixation_points((4, 6), [])
        assert mask.sum() == 0
        assert mask.shape == (4, 6)

    def test_output_dtype_uint8(self):
        mask = binary_mask_from_fixation_points((4, 4), [(1, 1)])
        assert mask.dtype == np.uint8

    def test_1d_shape_raises_clear_error(self):
        with pytest.raises(ValueError, match="2-D shape"):
            binary_mask_from_fixation_points((10,), [(2, 3)])


# ---------------------------------------------------------------------------
# nss_from_fixation_points
# ---------------------------------------------------------------------------

class TestNssFromFixationPoints:
    def test_fixation_at_peak_positive_nss(self):
        pred = np.zeros((5, 5))
        pred[2, 3] = 100.0  # peak at row=2, col=3 → point (x=3, y=2)
        result = nss_from_fixation_points(pred, [(3, 2)])
        assert result > 0.0

    def test_fixation_at_trough_negative_nss(self):
        pred = np.zeros((5, 5))
        pred[0, 0] = 100.0  # peak elsewhere
        result = nss_from_fixation_points(pred, [(4, 4)])  # fixation at trough
        assert result < 0.0

    def test_out_of_bounds_fixation_handled(self):
        # Out-of-bounds point filtered → empty mask → NaN
        pred = np.ones((4, 4)) * 0.5
        pred[0, 0] = 1.0
        result = nss_from_fixation_points(pred, [(100, 100)])
        assert math.isnan(result)

    def test_flat_pred_returns_nan(self):
        pred = np.ones((4, 4)) * 3.0
        result = nss_from_fixation_points(pred, [(2, 2)])
        assert math.isnan(result)


# ---------------------------------------------------------------------------
# auc_from_binary_mask
# ---------------------------------------------------------------------------

class TestAucFromBinaryMask:
    def test_perfect_auc_one(self):
        pred = np.array([0.9, 0.8, 0.7, 0.2, 0.1])
        mask = np.array([True, True, True, False, False])
        assert auc_from_binary_mask(pred, mask) == pytest.approx(1.0)

    def test_worst_auc_zero(self):
        pred = np.array([0.1, 0.2, 0.7, 0.8, 0.9])
        mask = np.array([True, True, True, False, False])
        assert auc_from_binary_mask(pred, mask) == pytest.approx(0.0)

    def test_all_true_returns_nan(self):
        pred = np.array([0.5, 0.6, 0.7])
        mask = np.array([True, True, True])
        assert math.isnan(auc_from_binary_mask(pred, mask))

    def test_all_false_returns_nan(self):
        pred = np.array([0.5, 0.6, 0.7])
        mask = np.array([False, False, False])
        assert math.isnan(auc_from_binary_mask(pred, mask))


# ---------------------------------------------------------------------------
# screen_map_metrics
# ---------------------------------------------------------------------------

class TestScreenMapMetrics:
    def test_default_keys_without_fixations(self):
        pred = np.array([1.0, 2.0, 3.0, 4.0])
        gt = np.array([1.0, 2.0, 3.0, 4.0])
        result = screen_map_metrics(pred, gt)
        assert "CC" in result
        assert "MSE" in result
        assert "KLD" in result
        assert "SIM" in result
        assert "Spearman" in result
        assert "AUC" not in result
        assert "NSS" not in result

    def test_fixation_points_triggers_auc_nss(self):
        # fixation_points requires 2D pred; point (x=2, y=0) → row=0, col=2
        pred = np.zeros((1, 4))
        pred[0, 2] = 100.0
        gt = np.zeros((1, 4))
        gt[0, 2] = 1.0
        result = screen_map_metrics(pred, gt, fixation_points=[(2, 0)])
        assert "AUC" in result
        assert "NSS" in result

    def test_1d_pred_with_fixation_points_raises(self):
        # binary_mask_from_fixation_points requires 2D shape — 1D pred must raise
        pred = np.array([0.0, 0.0, 100.0, 0.0])
        gt = np.array([0.0, 0.0, 1.0, 0.0])
        with pytest.raises(ValueError, match="2-D shape"):
            screen_map_metrics(pred, gt, fixation_points=[(2, 0)])

    def test_fixation_mask_triggers_auc_nss(self):
        pred = np.array([0.0, 0.0, 100.0, 0.0])
        gt = np.array([0.0, 0.0, 1.0, 0.0])
        mask = np.array([False, False, True, False])
        result = screen_map_metrics(pred, gt, fixation_mask=mask)
        assert "AUC" in result
        assert "NSS" in result

    def test_fixation_mask_takes_precedence_over_points(self):
        # When fixation_mask is provided, fixation_points is ignored
        pred = np.array([0.0, 0.0, 100.0, 0.0])
        gt = np.array([0.0, 0.0, 1.0, 0.0])
        mask = np.array([False, False, True, False])
        result_mask = screen_map_metrics(pred, gt, fixation_mask=mask)
        # fixation_points pointing elsewhere; mask should take precedence
        result_pts = screen_map_metrics(pred, gt, fixation_points=[(0, 0)],
                                        fixation_mask=mask)
        assert result_mask["NSS"] == pytest.approx(result_pts["NSS"], abs=1e-10)

    def test_kl_key_is_kld(self):
        pred = np.array([1.0, 2.0, 3.0])
        gt = np.array([1.0, 2.0, 3.0])
        result = screen_map_metrics(pred, gt)
        # screen_map_metrics passes kl_key="KLD" to dense_saliency_metrics
        assert "KLD" in result
        assert "KL_gt_to_pred" not in result

    def test_2d_input_supported(self):
        pred = np.ones((4, 4))
        pred[2, 2] = 5.0
        gt = np.zeros((4, 4))
        gt[2, 2] = 1.0
        result = screen_map_metrics(pred, gt)
        assert "CC" in result

    def test_identical_maps_cc_one(self):
        arr = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        result = screen_map_metrics(arr, arr)
        assert result["CC"] == pytest.approx(1.0, abs=1e-10)
        assert result["MSE"] == pytest.approx(0.0, abs=1e-15)
        assert result["SIM"] == pytest.approx(1.0, abs=1e-8)
