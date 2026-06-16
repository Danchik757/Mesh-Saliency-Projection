"""Dual-KLD helper: evaluator KLD (current benchmark) vs trusted-module KLD.

Per the 2026-06-15 user decision, new diagnostic/aggregate outputs carry both:
  - `KLD_evaluator` == the historical compact `KLD` (current benchmark output);
  - `KLD_trusted`   == the trusted-module KLD (`metrics.common.kldiv_score`,
                       the mathematical reference),
computed from the SAME pred/GT inputs when they are available. Historical compact
`KLD` keeps meaning evaluator KLD — trusted KLD is added, never silently swapped.

This module reuses the trusted `metrics/` module and reproduces the evaluators'
KLD formula; it imports/modifies no baseline evaluator.
"""
from __future__ import annotations

import numpy as np

from metrics.common import kldiv_score  # trusted-module KLD (mathematical reference)

EPS = 1e-12


def _normalize_sum_clip(values) -> np.ndarray:
    """clip(x, 0, None) then divide by the sum — the evaluators' probability
    normalisation (NOT the trusted module's shift-by-min)."""
    arr = np.asarray(values, dtype=np.float64).reshape(-1)
    arr = np.clip(arr, 0.0, None)
    total = float(arr.sum())
    return arr / total if total > 0.0 and np.isfinite(total) else np.zeros_like(arr)


def evaluator_kld(pred, gt) -> float:
    """Reproduce the baseline evaluators' KLD exactly: clip>=0 -> sum-normalise ->
    +eps, then KL(GT || pred). Matches reprojection_methods/*/compute_metrics."""
    pred_prob = _normalize_sum_clip(pred) + EPS
    gt_prob = _normalize_sum_clip(gt) + EPS
    return float(np.sum(gt_prob * np.log(gt_prob / pred_prob)))


def trusted_kld(pred, gt) -> float:
    """Trusted-module KLD (mathematical reference)."""
    return float(kldiv_score(np.asarray(pred, dtype=np.float64),
                             np.asarray(gt, dtype=np.float64)))


def enrich_row_with_dual_kld(row, *, pred_key: str = "pred", gt_key: str = "gt") -> dict:
    """Return a copy of `row` carrying `KLD_evaluator` and, when computable,
    `KLD_trusted`.

    - If pred/GT arrays are present under `pred_key`/`gt_key`, both KLDs are
      computed from those same inputs and historical `KLD` is set to the evaluator
      value if not already present.
    - Otherwise `KLD_evaluator` falls back to the row's existing `KLD` (evaluator
      output) and `KLD_trusted` is left absent (inputs unavailable).

    The pred/GT array keys are dropped from the returned row.
    """
    out = dict(row)
    pred, gt = row.get(pred_key), row.get(gt_key)
    if pred is not None and gt is not None:
        kld_eval = evaluator_kld(pred, gt)
        out["KLD_evaluator"] = kld_eval
        out["KLD_trusted"] = trusted_kld(pred, gt)
        out.setdefault("KLD", kld_eval)  # keep historical column = evaluator KLD
    elif row.get("KLD") not in (None, ""):
        out["KLD_evaluator"] = row["KLD"]
    out.pop(pred_key, None)
    out.pop(gt_key, None)
    return out
