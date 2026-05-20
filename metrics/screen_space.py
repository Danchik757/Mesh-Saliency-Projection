from __future__ import annotations

from typing import Iterable, Optional, Sequence

import numpy as np

from .common import (
    dense_saliency_metrics,
    kldiv_score,
    mse_score,
    nss_from_binary_mask,
    pearson_cc,
    roc_auc_from_labels,
    similarity_score,
)


def cc_from_maps(pred: np.ndarray, gt: np.ndarray) -> float:
    return pearson_cc(pred, gt)


def sim_from_maps(pred: np.ndarray, gt: np.ndarray) -> float:
    return similarity_score(pred, gt)


def kld_from_maps(pred: np.ndarray, gt: np.ndarray) -> float:
    return kldiv_score(pred, gt)


def mse_from_maps(pred: np.ndarray, gt: np.ndarray) -> float:
    return mse_score(pred, gt)


def binary_mask_from_fixation_points(
    shape: Sequence[int],
    fixation_points: Iterable[tuple[int, int]],
) -> np.ndarray:
    height, width = int(shape[0]), int(shape[1])
    mask = np.zeros((height, width), dtype=np.uint8)
    for x, y in fixation_points:
        if 0 <= x < width and 0 <= y < height:
            mask[y, x] = 1
    return mask


def nss_from_fixation_points(
    pred: np.ndarray,
    fixation_points: Iterable[tuple[int, int]],
) -> float:
    mask = binary_mask_from_fixation_points(pred.shape, fixation_points)
    return nss_from_binary_mask(pred, mask)


def auc_from_binary_mask(pred: np.ndarray, mask: np.ndarray) -> float:
    return roc_auc_from_labels(np.asarray(pred, dtype=np.float64), np.asarray(mask, dtype=bool))


def screen_map_metrics(
    pred: np.ndarray,
    gt: np.ndarray,
    *,
    fixation_points: Optional[Iterable[tuple[int, int]]] = None,
    fixation_mask: Optional[np.ndarray] = None,
) -> dict[str, float]:
    metrics = dense_saliency_metrics(pred, gt, kl_key="KLD")

    if fixation_mask is None and fixation_points is not None:
        fixation_mask = binary_mask_from_fixation_points(pred.shape, fixation_points)

    if fixation_mask is not None:
        mask_bool = np.asarray(fixation_mask, dtype=bool)
        metrics["AUC"] = auc_from_binary_mask(pred, mask_bool)
        metrics["NSS"] = nss_from_binary_mask(pred, mask_bool)

    return metrics
