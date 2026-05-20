from __future__ import annotations

from typing import Optional

import numpy as np

from .common import (
    dense_saliency_metrics,
    normalize_distribution as _normalize_distribution,
    nss_from_binary_mask,
    roc_auc_from_labels,
)


def normalize_distribution(values: np.ndarray, mask: Optional[np.ndarray] = None) -> np.ndarray:
    return _normalize_distribution(values, mask=mask)


def auc_visible_top20(pred: np.ndarray, target: np.ndarray, visible_mask: np.ndarray) -> float:
    scores = pred[visible_mask]
    gt = target[visible_mask]
    k = max(1, int(round(0.2 * len(scores))))
    order = np.argsort(gt)[::-1]
    positives = np.zeros(len(scores), dtype=bool)
    positives[order[:k]] = True
    return roc_auc_from_labels(scores, positives)


def map_metrics(
    pred: np.ndarray,
    target: np.ndarray,
    visible_mask: Optional[np.ndarray] = None,
    *,
    include_auc_visible_top20: bool = False,
    kl_key: str = "KL_gt_to_pred",
) -> dict[str, float]:
    out = dense_saliency_metrics(pred, target, mask=visible_mask, kl_key=kl_key)
    if include_auc_visible_top20:
        if visible_mask is None:
            raise ValueError("visible_mask is required when include_auc_visible_top20=True")
        out["AUC_visible_top20"] = auc_visible_top20(
            np.asarray(pred, dtype=np.float64),
            np.asarray(target, dtype=np.float64),
            np.asarray(visible_mask, dtype=bool),
        )
    return out


def nss_from_positive_indices(pred: np.ndarray, positive_indices: np.ndarray) -> float:
    p = np.asarray(pred, dtype=np.float64).reshape(-1)
    labels = np.zeros(len(p), dtype=bool)
    labels[np.unique(np.asarray(positive_indices, dtype=np.int64))] = True
    return nss_from_binary_mask(p, labels)


def auc_from_positive_indices(pred: np.ndarray, positive_indices: np.ndarray) -> float:
    p = np.asarray(pred, dtype=np.float64).reshape(-1)
    labels = np.zeros(len(p), dtype=bool)
    labels[np.unique(np.asarray(positive_indices, dtype=np.int64))] = True
    return roc_auc_from_labels(p, labels)
