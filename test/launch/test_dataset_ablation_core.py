"""Tests for the dataset-method ablation orchestrator (common-model-set fairness)."""
from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent


def _load(name):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


core = _load("dataset_ablation_core")
ssl = _load("screen_space_dataset_ablation")
conel = _load("cone_dataset_ablation")
ev = _load("run_evaluator_sweep")


# ── helpers ──────────────────────────────────────────────────────────────────

_COMPACT = ("CC", "SIM", "KLD", "MSE", "MAE", "Spearman", "Cosine",
            "AUC_at_10pct", "AUC_at_5pct", "AUC_at_1pct",
            "NSS_at_10pct", "NSS_at_5pct", "NSS_at_1pct", "hit_rate")


def _ok_row(model, cc):
    row = {"model": model, "status": "ok"}
    for m in _COMPACT:
        row[m] = 0.5
    row["CC"] = cc
    return row


def _invoke(*, fail=None, cc=None):
    """fail: {sigma_value: {models...}}; cc: callable(sigma_value, model)->CC."""
    fail = fail or {}
    def invoke(point, model):
        v = round(float(point["value"]), 6)
        if model in fail.get(v, set()):
            return {"model": model, "status": "failed", "error_type": "synthetic"}
        cc_val = cc(v, model) if cc else round(0.30 + 0.10 * v, 4)
        return _ok_row(model, cc_val)
    return invoke


def _request(stage="sigma", method="screen_space", models=None, **kw):
    req = {
        "dataset": "sal3d", "method": method, "stage": stage,
        "models": models or ["m1", "m2", "m3", "m4", "m5"],
        "subset_name": "rc3", "repo_commit": "a" * 40,
        "release_tag": "rc4", "fixation_data_tag": "tag",
        "timing_contract": "one_turn_from_start",
        "frame_offset_policy": "fixed:0", "delay_policy": "fixed:0.0",
        "window_mode": "one_turn_from_start",
        "fixed": {"delay_seconds": 0.0, "frame_offset": 0},
    }
    req.update(kw)
    return req


# ── 1. common-model-set logic ────────────────────────────────────────────────

def test_common_model_set_and_means():
    cand_rows = {
        "a": [_ok_row("m1", 0.4), _ok_row("m2", 0.6), {"model": "m3", "status": "failed"}],
        "b": [_ok_row("m1", 0.8), {"model": "m2", "status": "failed"}, _ok_row("m3", 0.2)],
    }
    common = core.common_model_set(cand_rows)
    assert common == {"m1"}  # only m1 ok in BOTH candidates
    means_a = core.means_on_models(cand_rows["a"], common)
    assert means_a["CC"] == 0.4
    means_b = core.means_on_models(cand_rows["b"], common)
    assert means_b["CC"] == 0.8


# ── 2. branch_best by common set, not raw n_ok ───────────────────────────────

def test_branch_best_uses_common_set_not_raw_n_ok(tmp_path):
    # sigma=1.0 drops m5 (4 raw ok) but has the highest CC on the common set;
    # sigma=0.5 keeps all 5 (more raw ok) but lower CC. Common set = {m1..m4}.
    def cc(v, model):
        if v == 0.5:
            return 0.40
        if v == 1.0:
            return 0.90
        return 0.50
    result = ssl.run(_request(), results_root=tmp_path,
                     invoke=_invoke(fail={1.0: {"m5"}}, cc=cc), update_table=False)
    assert result["promoted"] is True
    best = result["summary"]["best"]
    assert best["sigma_value"] == 1.0           # won on common-set mean CC
    assert best["n_ok_raw"] == 4                 # despite FEWER raw-ok models
    assert result["summary"]["n_common_models"] == 4


# ── 3. no per-model sigma selection ──────────────────────────────────────────

def test_selection_ignores_single_best_model(tmp_path):
    # sigma=0.7 has the single highest model CC (0.99) but a low mean; sigma=1.0
    # has a higher mean. The mean over the common set must win.
    def cc(v, model):
        if v == 0.7:
            return 0.99 if model == "m1" else 0.20
        if v == 1.0:
            return 0.50
        return 0.30
    result = ssl.run(_request(), results_root=tmp_path,
                     invoke=_invoke(cc=cc), update_table=False)
    best = result["summary"]["best"]
    assert best["sigma_value"] == 1.0
    # the single highest per-model CC lived at sigma 0.7, which did NOT win
    per = {c["sigma_value"]: c for c in result["summary"]["per_candidate"]}
    assert per[0.7]["mean_common"]["CC"] < per[1.0]["mean_common"]["CC"]


# ── 4. reject incompatible mixes ─────────────────────────────────────────────

def test_assert_homogeneous_rejects_incompatible():
    records = [
        {"release_tag": "rc4", "fixation_data_tag": "t", "timing_contract": "c",
         "frame_offset_policy": "p", "delay_policy": "d", "subset_signature": "x"},
        {"release_tag": "rc5", "fixation_data_tag": "t", "timing_contract": "c",
         "frame_offset_policy": "p", "delay_policy": "d", "subset_signature": "x"},
    ]
    with pytest.raises(core.BranchError, match="incompatible mix"):
        core.assert_homogeneous(records)


def test_assert_homogeneous_accepts_uniform():
    rec = {"release_tag": "rc4", "fixation_data_tag": "t", "timing_contract": "c",
           "frame_offset_policy": "p", "delay_policy": "d", "subset_signature": "x"}
    assert core.assert_homogeneous([rec, dict(rec)])


# ── 5. dataset-method table append / update ──────────────────────────────────

def test_table_append_then_update_same_key_then_new_signature(tmp_path):
    inv = _invoke()  # CC rises with sigma -> promotes
    ssl.run(_request(), results_root=tmp_path, invoke=inv)
    ssl.run(_request(), results_root=tmp_path, invoke=inv)  # same key -> update in place
    table = tmp_path / "ablation" / "_tables" / "dataset_method_ablation.csv"
    rows = list(csv.DictReader(table.open()))
    assert len(rows) == 1  # updated, not duplicated

    ssl.run(_request(release_tag="rc5"), results_root=tmp_path, invoke=inv)  # new signature
    rows = list(csv.DictReader(table.open()))
    assert len(rows) == 2  # incompatible run -> separate row, did not overwrite
    sigs = {r["comparability_signature"] for r in rows}
    assert len(sigs) == 2


# ── 6. hold when common coverage too low ─────────────────────────────────────

def test_hold_when_common_coverage_below_threshold(tmp_path):
    models = [f"m{i}" for i in range(1, 11)]  # 10 models
    grid = ssl.build_spec().coarse_grid       # 5 sigmas
    # each of the first four sigmas drops a distinct model -> common = 6/10 = 0.6 < 0.70
    fail = {grid[0]: {"m1"}, grid[1]: {"m2"}, grid[2]: {"m3"}, grid[3]: {"m4"}}
    result = ssl.run(_request(models=models), results_root=tmp_path,
                     invoke=_invoke(fail=fail))
    assert result["promoted"] is False
    assert "coverage_common" in result["summary"]["hold_reason"]
    assert result["held_path"].exists()
    held = json.loads(result["held_path"].read_text())
    assert held["n_common_models"] == 6
    table = tmp_path / "ablation" / "_tables" / "dataset_method_ablation.csv"
    row = list(csv.DictReader(table.open()))[0]
    assert row["promoted"] == "False"


# ── 7. per-branch artifacts ──────────────────────────────────────────────────

def test_branch_artifacts_written(tmp_path):
    result = ssl.run(_request(), results_root=tmp_path, invoke=_invoke())
    bd = result["branch_dir"]
    assert (bd / "manifest.json").exists()
    assert (bd / "README.md").exists()
    assert (bd / "aggregate" / "ablation_runs.jsonl").exists()
    assert (bd / "aggregate" / "ablation_runs.csv").exists()
    assert (bd / "aggregate" / "common_model_summary.json").exists()
    assert (bd / "branch_best.json").exists()
    bb = json.loads((bd / "branch_best.json").read_text())
    assert bb["selection_rule"] == "mean_CC_on_common_model_set"
    assert "sigma_multiplier" in bb["best_params"]
    # README states the per-(dataset,method) policy explicitly
    assert "per (dataset, method)" in (bd / "README.md").read_text()


# ── 8. screen_space end-to-end via launcher + mock ───────────────────────────

def test_screen_space_end_to_end_with_default_mock(tmp_path):
    result = ssl.run(_request(), results_root=tmp_path, invoke=ev.make_mock_invoke())
    assert result["promoted"] is True
    bb = json.loads(result["branch_best_path"].read_text())
    # default mock CC rises with sigma -> the largest coarse multiplier wins
    assert bb["best_params"]["sigma_multiplier"] == 1.5
    assert "sigma_px" in bb["best_params"]


# ── 9. cone refined sub-stage ────────────────────────────────────────────────

def test_cone_refined_substage_adds_candidates(tmp_path):
    # tent peaked at sigma_deg=1.0 -> coarse best interior -> refined grid around 1.0
    def cc(v, model):
        return round(0.60 - abs(v - 1.0) * 0.10, 4)
    req = _request(method="cone", sigma={"refined": True})
    result = conel.run(req, results_root=tmp_path, invoke=_invoke(cc=cc))
    assert result["promoted"] is True
    sub_stages = {c["sub_stage"] for c in result["summary"]["per_candidate"]}
    assert "coarse" in sub_stages and "refined" in sub_stages
    bb = json.loads(result["branch_best_path"].read_text())
    assert "sigma_deg" in bb["best_params"]
    assert bb["best_params"]["radius_sigma_mult"] == 3.0


# ── 10. validation ───────────────────────────────────────────────────────────

def test_validate_rejects_timing_without_fixed_sigma():
    req = _request(stage="timing", axis_values=[0.0, 0.2])
    with pytest.raises(core.BranchError, match="fixed_sigma"):
        core.validate_request(req)


def test_validate_rejects_bad_repo_commit():
    req = _request()
    req["repo_commit"] = "short"
    with pytest.raises(core.BranchError, match="repo_commit"):
        core.validate_request(req)


# ── 11. timing stage end-to-end (fixed sigma, swept delay) ───────────────────

def test_timing_stage_runs_and_records_chosen_delay(tmp_path):
    def cc(v, model):
        return 0.90 if v == 0.2 else 0.40   # delay 0.2 best
    req = _request(stage="timing",
                   fixed_sigma={"sigma_multiplier": 1.0, "sigma_px": 26.3},
                   axis_values=[0.0, 0.2, 0.5])
    result = ssl.run(req, results_root=tmp_path, invoke=_invoke(cc=cc))
    assert result["promoted"] is True
    bb = json.loads(result["branch_best_path"].read_text())
    assert bb["best_params"]["delay_seconds"] == 0.2
    assert bb["best_params"]["sigma_multiplier"] == 1.0


# ── 12. P1-1: incompatible runs must not overwrite branch-level markers ───────

def test_incompatible_runs_get_separate_branch_dirs(tmp_path):
    inv = _invoke()
    r_a = ssl.run(_request(release_tag="rc4"), results_root=tmp_path, invoke=inv)
    r_b = ssl.run(_request(release_tag="rc5"), results_root=tmp_path, invoke=inv)
    # different comparability signature -> different signature-scoped branch dir
    assert r_a["comparability_signature"] != r_b["comparability_signature"]
    assert r_a["branch_dir"] != r_b["branch_dir"]
    # both branch_best markers survive (neither overwrote the other)
    assert r_a["branch_best_path"].exists() and r_b["branch_best_path"].exists()
    bb_a = json.loads(r_a["branch_best_path"].read_text())
    bb_b = json.loads(r_b["branch_best_path"].read_text())
    assert bb_a["comparability_signature"] == r_a["comparability_signature"]
    assert bb_b["comparability_signature"] == r_b["comparability_signature"]
    # the signature dir is a path component of the branch dir
    assert r_a["comparability_signature"] in r_a["branch_dir"].parts
    assert r_b["comparability_signature"] in r_b["branch_dir"].parts


# ── 13. P1-2: aggregate run_ids must be comparability-aware ───────────────────

def test_aggregate_run_ids_differ_across_signatures(tmp_path):
    inv = _invoke()
    r_a = ssl.run(_request(release_tag="rc4"), results_root=tmp_path, invoke=inv)
    r_b = ssl.run(_request(release_tag="rc5"), results_root=tmp_path, invoke=inv)

    def _run_ids(branch_dir):
        p = branch_dir / "aggregate" / "ablation_runs.jsonl"
        rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
        # no candidate was superseded within its own (now signature-scoped) aggregate
        assert all(r.get("status") != "superseded" for r in rows)
        return {r["run_id"] for r in rows}

    ids_a = _run_ids(r_a["branch_dir"])
    ids_b = _run_ids(r_b["branch_dir"])
    # run_ids are comparability-suffixed -> disjoint across the two configs
    assert ids_a and ids_b
    assert ids_a.isdisjoint(ids_b)
    assert all(r_a["comparability_signature"] in rid for rid in ids_a)
    assert all(r_b["comparability_signature"] in rid for rid in ids_b)


def test_candidate_run_id_changes_with_signature():
    params = {"window_mode": "w", "sigma_multiplier": 1.0, "delay_seconds": 0.0,
              "frame_offset": 0, "model_set_signature": "abc"}
    a = core._candidate_run_id(params, "sig_aaaaaaaa")
    b = core._candidate_run_id(params, "sig_bbbbbbbb")
    assert a != b
    assert a.endswith("sig_aaaaaaaa") and b.endswith("sig_bbbbbbbb")
