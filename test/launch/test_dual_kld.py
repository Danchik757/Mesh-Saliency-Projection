"""Tests for the dual-KLD helper (evaluator KLD vs trusted-module KLD)."""
from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

import numpy as np

_DIR = Path(__file__).resolve().parent


def _load(name):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


dk = _load("dual_kld")


def _sample(seed=0, n=2000):
    rng = np.random.default_rng(seed)
    pred = rng.normal(0.3, 1.0, size=n)
    gt = 0.6 * pred + rng.normal(0.0, 0.8, size=n)
    return pred, gt


def test_evaluator_kld_matches_real_evaluator():
    # dual_kld.evaluator_kld must reproduce the baseline evaluator's KLD exactly.
    evmod = importlib.import_module(
        "reprojection_methods.cone_projection_on_mesh.eval_meshmamba_cone")
    pred, gt = _sample()
    assert np.isclose(dk.evaluator_kld(pred, gt), evmod.compute_metrics(pred, gt)["KLD"])


def test_trusted_kld_matches_metrics_module():
    from metrics.common import kldiv_score
    pred, gt = _sample()
    assert np.isclose(dk.trusted_kld(pred, gt), float(kldiv_score(pred, gt)))


def test_evaluator_and_trusted_kld_differ_on_signed_input():
    pred, gt = _sample()
    assert abs(dk.evaluator_kld(pred, gt) - dk.trusted_kld(pred, gt)) > 1e-3


def test_enrich_row_with_arrays_sets_both_klds():
    pred, gt = _sample()
    row = {"model": "A", "status": "ok", "pred": pred, "gt": gt}
    out = dk.enrich_row_with_dual_kld(row)
    assert "pred" not in out and "gt" not in out          # arrays dropped
    assert np.isclose(out["KLD_evaluator"], dk.evaluator_kld(pred, gt))
    assert np.isclose(out["KLD_trusted"], dk.trusted_kld(pred, gt))
    assert np.isclose(out["KLD"], out["KLD_evaluator"])    # historical = evaluator


def test_enrich_row_without_arrays_falls_back_to_existing_kld():
    out = dk.enrich_row_with_dual_kld({"model": "B", "status": "ok", "KLD": 1.23})
    assert out["KLD_evaluator"] == 1.23                    # falls back to stored KLD
    assert "KLD_trusted" not in out                        # inputs unavailable -> absent
    assert out["KLD"] == 1.23                              # unchanged
