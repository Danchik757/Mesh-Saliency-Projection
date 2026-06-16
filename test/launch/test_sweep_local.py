"""Tests for the local per-point sweep runner (test/launch/sweep_local.py).

Covers: grid enumeration, per-point params + metrics propagation into aggregate
rows, multiple points producing multiple aggregate rows with distinct run dirs,
and an end-to-end real-source sigma sweep (skipped if the rc3 CSV is absent).
"""
from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("sweep_local", _DIR / "sweep_local.py")
sweep = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sweep)

_REPO = _DIR.parents[1]
_RC3_SAL3D_LONG = (_REPO / "results/csv/rc3_baseline/benchmark_runs/"
                   "rc3_full_metrics_20260611_004003/csv_only/sal3d_reference_long.csv")


def _provider(point):
    """One ok model whose CC encodes the point's axis value, so different points
    yield different aggregate metrics (proves per-point metric propagation)."""
    v = point["value"]
    return [{"model": "A", "status": "ok", "CC": v, "SIM": 0.6, "KLD": 0.4, "MSE": 0.03,
             "MAE": 0.1, "Spearman": 0.5, "Cosine": 0.8,
             "AUC_Judd_gt_top_10pct_proxy": 0.8, "AUC_Judd_gt_top_5pct_proxy": 0.82,
             "AUC_Judd_gt_top_1pct_proxy": 0.88, "NSS_gt_top_10pct_proxy": 1.0,
             "NSS_gt_top_5pct_proxy": 1.2, "NSS_gt_top_1pct_proxy": 1.5, "hit_rate": 0.9}]


def _make_params(point):
    return {"stage_name": "sweep_test", "dataset": point["dataset"], "method": point["method"],
            point["axis"]: point["value"], "command": f"sweep {point['axis']}={point['value']}"}


def _agg_rows(tmp_path, dataset="sal3d", method="cone", stage="sweep_test"):
    p = tmp_path / "ablation" / stage / dataset / method / "aggregate" / "ablation_runs.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()]


# ── grid enumeration ───────────────────────────────────────────────────────────

def test_enumerate_grid():
    points = sweep.enumerate_grid(datasets=["sal3d"], methods=["cone", "screen_space"],
                                  axis="sigma_deg", values=[0.8, 1.0, 2.0])
    assert len(points) == 6
    assert {p["method"] for p in points} == {"cone", "screen_space"}
    assert [p["value"] for p in points if p["method"] == "cone"] == [0.8, 1.0, 2.0]
    assert all(p["axis"] == "sigma_deg" and p["dataset"] == "sal3d" for p in points)


# ── per-point propagation ──────────────────────────────────────────────────────

def test_per_point_params_and_metrics_propagate(tmp_path):
    points = sweep.enumerate_grid(datasets=["sal3d"], methods=["cone"],
                                  axis="sigma_deg", values=[0.8, 1.0, 2.0])
    sweep.run_sweep(points, tmp_path, provider=_provider, make_params=_make_params)

    rows = _agg_rows(tmp_path)
    by_sigma = {r["sigma_deg"]: r for r in rows}
    assert set(by_sigma) == {0.8, 1.0, 2.0}                 # per-point param propagated
    for sigma, r in by_sigma.items():
        assert r["CC"] == sigma                             # per-point metric propagated
        assert r["method"] == "cone" and r["dataset"] == "sal3d"
        assert r["n_ok"] == 1


def test_multiple_points_distinct_rows_and_dirs(tmp_path):
    points = sweep.enumerate_grid(datasets=["sal3d"], methods=["cone"],
                                  axis="sigma_deg", values=[0.8, 1.0, 2.0])
    run_dirs = sweep.run_sweep(points, tmp_path, provider=_provider, make_params=_make_params)

    assert len(run_dirs) == 3
    assert len({d.name for d in run_dirs}) == 3             # distinct run directories
    for d in run_dirs:
        assert (d / "metrics_summary.csv").is_file()

    rows = _agg_rows(tmp_path)
    assert len(rows) == 3                                   # one aggregate row per point
    assert len({r["run_id"] for r in rows}) == 3
    assert len({r["result_root"] for r in rows}) == 3


def test_screen_space_and_cone_go_to_separate_branches(tmp_path):
    points = sweep.enumerate_grid(datasets=["sal3d"], methods=["cone", "screen_space"],
                                  axis="sigma_deg", values=[1.0])
    sweep.run_sweep(points, tmp_path, provider=_provider, make_params=_make_params)
    base = tmp_path / "ablation" / "sweep_test" / "sal3d"
    assert (base / "cone" / "aggregate" / "ablation_runs.jsonl").is_file()
    assert (base / "screen_space" / "aggregate" / "ablation_runs.jsonl").is_file()


# ── end-to-end real-source sweep ───────────────────────────────────────────────

@pytest.mark.skipif(not _RC3_SAL3D_LONG.is_file(), reason="accepted rc3 long CSV not present")
def test_reference_sigma_sweep_real(tmp_path):
    run_dirs = sweep.run_reference_sigma_sweep(
        _RC3_SAL3D_LONG, tmp_path, dataset="sal3d", method="cone",
        sigma_values=[0.8, 1.0, 2.0], radius_sigma_mult=3.0)
    assert len(run_dirs) == 3 and len({d.name for d in run_dirs}) == 3

    rows = _agg_rows(tmp_path, stage="sweep_demo_sigma")
    assert len(rows) == 3
    assert sorted(r["sigma_deg"] for r in rows) == [0.8, 1.0, 2.0]   # axis varies per point
    # Prototype limitation (documented): metrics are identical across points because
    # the same accepted source is reused — the real runner would re-evaluate per sigma.
    assert len({r["CC"] for r in rows}) == 1
    assert all(r["n_ok"] == 54 for r in rows)
