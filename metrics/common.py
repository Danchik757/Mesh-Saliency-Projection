from __future__ import annotations

from typing import Optional

import numpy as np


EPS = 1e-12


def _as_float_array(values: np.ndarray) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    if array.size == 0:
        raise ValueError("metric input must not be empty")
    if not np.isfinite(array).all():
        raise ValueError("metric input must contain only finite values")
    return array


def _validate_same_shape(a: np.ndarray, b: np.ndarray, label_a: str, label_b: str) -> None:
    if a.shape != b.shape:
        raise ValueError(f"{label_a} and {label_b} must have the same shape, got {a.shape} vs {b.shape}")


def _validate_mask_shape(values: np.ndarray, mask: np.ndarray) -> None:
    if values.shape != mask.shape:
        raise ValueError(f"mask must have the same shape as values, got {mask.shape} vs {values.shape}")


def flatten_pair(
    pred: np.ndarray,
    target: np.ndarray,
    mask: Optional[np.ndarray] = None,
) -> tuple[np.ndarray, np.ndarray]:
    pred_arr = _as_float_array(pred)
    target_arr = _as_float_array(target)
    _validate_same_shape(pred_arr, target_arr, "pred", "target")

    if mask is not None:
        mask_arr = np.asarray(mask, dtype=bool)
        _validate_mask_shape(pred_arr, mask_arr)
        pred_arr = pred_arr[mask_arr]
        target_arr = target_arr[mask_arr]

    pred_flat = pred_arr.reshape(-1)
    target_flat = target_arr.reshape(-1)
    if pred_flat.size == 0:
        raise ValueError("metric support is empty after applying the mask")
    return pred_flat, target_flat


def rankdata_average(values: np.ndarray) -> np.ndarray:
    values_arr = _as_float_array(values).reshape(-1)
    order = np.argsort(values_arr, kind="mergesort")
    sorted_values = values_arr[order]
    ranks = np.empty(values_arr.size, dtype=np.float64)

    start = 0
    while start < sorted_values.size:
        stop = start + 1
        while stop < sorted_values.size and sorted_values[stop] == sorted_values[start]:
            stop += 1
        average_rank = 0.5 * (start + stop - 1) + 1.0
        ranks[order[start:stop]] = average_rank
        start = stop

    return ranks


def pearson_cc(pred: np.ndarray, target: np.ndarray) -> float:
    pred_flat, target_flat = flatten_pair(pred, target)
    pred_std = pred_flat.std()
    target_std = target_flat.std()
    if pred_std <= EPS or target_std <= EPS:
        return float("nan")
    pred_centered = pred_flat - pred_flat.mean()
    target_centered = target_flat - target_flat.mean()
    denominator = np.sqrt(np.sum(pred_centered ** 2) * np.sum(target_centered ** 2))
    if denominator <= EPS:
        return float("nan")
    return float(np.sum(pred_centered * target_centered) / denominator)


def spearman_cc(pred: np.ndarray, target: np.ndarray) -> float:
    pred_flat, target_flat = flatten_pair(pred, target)
    pred_rank = rankdata_average(pred_flat)
    target_rank = rankdata_average(target_flat)
    return pearson_cc(pred_rank, target_rank)


def mse_score(pred: np.ndarray, target: np.ndarray) -> float:
    pred_flat, target_flat = flatten_pair(pred, target)
    return float(np.mean((pred_flat - target_flat) ** 2))


def normalize_minmax(values: np.ndarray) -> np.ndarray:
    array = _as_float_array(values)
    min_value = np.min(array)
    max_value = np.max(array)
    if max_value - min_value <= EPS:
        return np.zeros_like(array, dtype=np.float64)
    return (array - min_value) / (max_value - min_value)


def normalize_distribution(values: np.ndarray, mask: Optional[np.ndarray] = None) -> np.ndarray:
    array = _as_float_array(values)
    if mask is not None:
        mask_arr = np.asarray(mask, dtype=bool)
        _validate_mask_shape(array, mask_arr)
        array = array[mask_arr]

    min_value = np.min(array)
    if min_value < 0.0:
        array = array - min_value
    total = np.sum(array)
    if total <= EPS:
        return np.full(array.shape, 1.0 / array.size, dtype=np.float64)
    return (array + EPS) / (total + EPS * array.size)


def similarity_score(pred: np.ndarray, target: np.ndarray) -> float:
    pred_flat, target_flat = flatten_pair(pred, target)
    pred_norm = normalize_distribution(normalize_minmax(pred_flat))
    target_norm = normalize_distribution(normalize_minmax(target_flat))
    return float(np.sum(np.minimum(pred_norm, target_norm)))


def kldiv_score(pred: np.ndarray, target: np.ndarray) -> float:
    pred_flat, target_flat = flatten_pair(pred, target)
    pred_norm = normalize_distribution(pred_flat)
    target_norm = normalize_distribution(target_flat)
    return float(np.sum(target_norm * np.log(target_norm / pred_norm)))


def roc_auc_from_labels(scores: np.ndarray, labels: np.ndarray) -> float:
    scores_arr = _as_float_array(scores).reshape(-1)
    labels_arr = np.asarray(labels, dtype=bool).reshape(-1)
    _validate_same_shape(scores_arr, labels_arr, "scores", "labels")

    positives = int(labels_arr.sum())
    negatives = int((~labels_arr).sum())
    if positives == 0 or negatives == 0:
        return float("nan")

    ranks = rankdata_average(scores_arr)
    positive_rank_sum = float(ranks[labels_arr].sum())
    u_statistic = positive_rank_sum - positives * (positives + 1) / 2.0
    return float(u_statistic / (positives * negatives))


def nss_from_binary_mask(pred: np.ndarray, mask: np.ndarray) -> float:
    pred_arr = _as_float_array(pred)
    mask_arr = np.asarray(mask, dtype=bool)
    _validate_same_shape(pred_arr, mask_arr, "pred", "mask")

    positive_count = int(mask_arr.sum())
    if positive_count == 0:
        return float("nan")

    pred_std = pred_arr.std()
    if pred_std <= EPS:
        return float("nan")

    z_score = (pred_arr - pred_arr.mean()) / pred_std
    return float(np.mean(z_score[mask_arr]))


def dense_saliency_metrics(
    pred: np.ndarray,
    target: np.ndarray,
    mask: Optional[np.ndarray] = None,
    *,
    include_spearman: bool = True,
    include_similarity: bool = True,
    kl_key: str = "KL_gt_to_pred",
) -> dict[str, float]:
    pred_flat, target_flat = flatten_pair(pred, target, mask=mask)
    metrics = {
        "CC": pearson_cc(pred_flat, target_flat),
        "MSE": mse_score(pred_flat, target_flat),
        kl_key: kldiv_score(pred_flat, target_flat),
    }
    if include_similarity:
        metrics["SIM"] = similarity_score(pred_flat, target_flat)
    if include_spearman:
        metrics["Spearman"] = spearman_cc(pred_flat, target_flat)
    return metrics
