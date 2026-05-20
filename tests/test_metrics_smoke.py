from __future__ import annotations

import numpy as np

from metrics.mesh_space import auc_from_positive_indices, map_metrics, nss_from_positive_indices
from metrics.screen_space import (
    auc_from_binary_mask,
    binary_mask_from_fixation_points,
    cc_from_maps,
    kld_from_maps,
    mse_from_maps,
    nss_from_fixation_points,
    screen_map_metrics,
    sim_from_maps,
)


def test_screen_metrics_smoke() -> None:
    pred = np.array([[0.0, 1.0], [0.2, 0.8]], dtype=np.float64)
    gt = np.array([[0.1, 0.9], [0.3, 0.7]], dtype=np.float64)
    fixation_points = [(1, 0), (1, 1)]
    mask = binary_mask_from_fixation_points((2, 2), fixation_points)

    assert -1.0 <= cc_from_maps(pred, gt) <= 1.0
    assert 0.0 <= sim_from_maps(pred, gt) <= 1.0
    assert kld_from_maps(pred, gt) >= 0.0
    assert np.isclose(mse_from_maps(pred, gt), 0.01)
    assert np.isfinite(nss_from_fixation_points(pred, fixation_points))
    assert 0.0 <= auc_from_binary_mask(pred, mask) <= 1.0

    summary = screen_map_metrics(pred, gt, fixation_points=fixation_points)
    assert set(summary) >= {"CC", "SIM", "KLD", "MSE", "AUC", "NSS", "Spearman"}


def test_mesh_metrics_smoke() -> None:
    pred = np.array([0.1, 0.3, 0.4, 0.2], dtype=np.float64)
    gt = np.array([0.05, 0.25, 0.5, 0.2], dtype=np.float64)
    vis = np.array([True, True, True, True])

    out = map_metrics(pred, gt, vis, include_auc_visible_top20=True)
    assert -1.0 <= out["CC"] <= 1.0
    assert -1.0 <= out["Spearman"] <= 1.0
    assert 0.0 <= out["SIM"] <= 1.0
    assert out["MSE"] >= 0.0
    assert out["KL_gt_to_pred"] >= 0.0
    assert 0.0 <= out["AUC_visible_top20"] <= 1.0

    pos = np.array([1, 2, 2], dtype=np.int64)
    assert 0.0 <= auc_from_positive_indices(pred, pos) <= 1.0
    assert np.isfinite(nss_from_positive_indices(pred, pos))


def test_identical_dense_maps_have_perfect_similarity() -> None:
    pred = np.array([0.1, 0.4, 0.2, 0.8], dtype=np.float64)
    out = map_metrics(pred, pred)

    assert np.isclose(out["CC"], 1.0)
    assert np.isclose(out["Spearman"], 1.0)
    assert np.isclose(out["SIM"], 1.0)
    assert np.isclose(out["MSE"], 0.0)
    assert np.isclose(out["KL_gt_to_pred"], 0.0)
