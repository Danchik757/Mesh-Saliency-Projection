"""Tests for the joint_refine family launcher (both cone + screen_space)."""
from __future__ import annotations

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


jr = _load("joint_refine_family_launcher")
agg = _load("ablation_aggregation")
ev = _load("run_evaluator_sweep")


# ── fixtures ────────────────────────────────────────────────────────────────

def _write_smoke(tmp_path, dataset, method):
    smoke_dir = tmp_path / "smoke"
    smoke_dir.mkdir(exist_ok=True)
    summary = smoke_dir / "summary.csv"
    summary.write_text("dataset_track,method\n")
    payload = {
        "verdict": {"ok": True, "reason": "green"},
        "repo_commit": "a" * 40,
        "metrics_summary_csv": str(summary),
        "point": {"dataset": dataset, "method": method},
    }
    p = smoke_dir / "smoke_gate.json"
    p.write_text(json.dumps(payload))
    return p


def _write_marker(tmp_path, *, leaf, family, dataset, method, best_params):
    d = tmp_path / leaf
    d.mkdir(parents=True, exist_ok=True)
    payload = {
        "family": family, "dataset": dataset, "method": method, "stage": "sweep",
        "points_to": f"aggregate/ablation_runs.jsonl#run_id=u_{leaf}",
        "repo_commit": "a" * 40, "promoted_at_utc": "2026-06-16T01:00:00Z",
        "best_params": best_params, "common_model_set": "rc3_reference_ok",
        "n_models_used": 1, "noise_floor_CC": 0.01, "best_CC": 0.5,
        "artifact_run_id": f"u_{leaf}",
    }
    p = d / "branch_best.json"
    p.write_text(json.dumps(payload))
    return p


def _cone_manifest(tmp_path):
    sigma = _write_marker(tmp_path, leaf="up_sigma", family="cone_sigma",
                          dataset="sal3d", method="cone",
                          best_params={"sigma_deg": 2.0, "radius_sigma_mult": 3.0})
    timing = _write_marker(tmp_path, leaf="up_timing", family="cone_timing",
                           dataset="sal3d", method="cone",
                           best_params={"sigma_deg": 2.0, "radius_sigma_mult": 3.0,
                                        "delay_seconds": 0.2})
    fo = _write_marker(tmp_path, leaf="up_fo", family="cone_frame_offset",
                       dataset="sal3d", method="cone",
                       best_params={"sigma_deg": 2.0, "radius_sigma_mult": 3.0,
                                    "delay_seconds": 0.2, "frame_offset": 54})
    smoke = _write_smoke(tmp_path, "sal3d", "cone")
    return {
        "submission": {
            "family": "cone_joint_refine", "dataset": "sal3d", "method": "cone",
            "texture_type": "", "repo_commit": "a" * 40,
            "smoke_artifact": str(smoke),
            "fixation_data_tag": "tag", "window_mode": "one_turn_from_start",
            "resolved_env": {"FIXATION_ROOT": "/x"}, "python": "python3",
            "timeout_seconds_per_invocation": 60, "max_workers": 1,
        },
        "models": {"subset_name": "rc3_reference_ok", "list": ["dog"]},
        "consumes": {
            "sigma_branch_best": str(sigma),
            "timing_branch_best": str(timing),
            "frame_offset_branch_best": str(fo),
        },
    }


def _screen_manifest(tmp_path):
    sigma = _write_marker(tmp_path, leaf="up_sigma", family="screen_space_sigma",
                          dataset="sal3d", method="screen_space",
                          best_params={"sigma_multiplier": 1.0, "sigma_px": 26.3,
                                       "base_sigma": 26.3})
    timing = _write_marker(tmp_path, leaf="up_timing", family="screen_space_timing",
                           dataset="sal3d", method="screen_space",
                           best_params={"sigma_multiplier": 1.0, "sigma_px": 26.3,
                                        "base_sigma": 26.3, "delay_seconds": 0.1})
    fo = _write_marker(tmp_path, leaf="up_fo", family="screen_space_frame_offset",
                       dataset="sal3d", method="screen_space",
                       best_params={"sigma_multiplier": 1.0, "sigma_px": 26.3,
                                    "base_sigma": 26.3, "delay_seconds": 0.1,
                                    "frame_offset": 30})
    smoke = _write_smoke(tmp_path, "sal3d", "screen_space")
    return {
        "submission": {
            "family": "screen_space_joint_refine", "dataset": "sal3d",
            "method": "screen_space", "texture_type": "", "repo_commit": "a" * 40,
            "smoke_artifact": str(smoke),
            "fixation_data_tag": "tag", "window_mode": "one_turn_from_start",
            "resolved_env": {"FIXATION_ROOT": "/x"}, "python": "python3",
            "timeout_seconds_per_invocation": 60, "max_workers": 1,
        },
        "models": {"subset_name": "rc3_reference_ok", "list": ["dog"]},
        "consumes": {
            "sigma_branch_best": str(sigma),
            "timing_branch_best": str(timing),
            "frame_offset_branch_best": str(fo),
        },
    }


# ── manifest validation ─────────────────────────────────────────────────────

def test_manifest_validates_for_cone(tmp_path):
    jr.validate_manifest(_cone_manifest(tmp_path))


def test_manifest_validates_for_screen_space(tmp_path):
    jr.validate_manifest(_screen_manifest(tmp_path))


def test_manifest_rejects_substage_marker(tmp_path):
    m = _cone_manifest(tmp_path)
    p = Path(m["consumes"]["timing_branch_best"])
    bad = p.parent / "coarse_best.json"
    bad.write_text(p.read_text())
    m["consumes"]["timing_branch_best"] = str(bad)
    with pytest.raises(jr.ManifestError, match="branch_best.json"):
        jr.validate_manifest(m)


def test_manifest_requires_all_three_markers(tmp_path):
    m = _cone_manifest(tmp_path)
    del m["consumes"]["frame_offset_branch_best"]
    with pytest.raises(jr.ManifestError, match="frame_offset_branch_best"):
        jr.validate_manifest(m)


def test_manifest_rejects_sigma_disagreement(tmp_path):
    m = _cone_manifest(tmp_path)
    tp = Path(m["consumes"]["timing_branch_best"])
    obj = json.loads(tp.read_text())
    obj["best_params"]["sigma_deg"] = 1.0  # disagrees with sigma marker's 2.0
    tp.write_text(json.dumps(obj))
    with pytest.raises(jr.ManifestError, match="sigma disagreement"):
        jr.validate_manifest(m)


def test_manifest_rejects_delay_disagreement(tmp_path):
    m = _cone_manifest(tmp_path)
    fp = Path(m["consumes"]["frame_offset_branch_best"])
    obj = json.loads(fp.read_text())
    obj["best_params"]["delay_seconds"] = 0.5  # disagrees with timing's 0.2
    fp.write_text(json.dumps(obj))
    with pytest.raises(jr.ManifestError, match="delay disagreement"):
        jr.validate_manifest(m)


def test_manifest_rejects_frame_offset_marker_without_frame_offset(tmp_path):
    m = _cone_manifest(tmp_path)
    fp = Path(m["consumes"]["frame_offset_branch_best"])
    obj = json.loads(fp.read_text())
    obj["best_params"].pop("frame_offset")
    fp.write_text(json.dumps(obj))
    with pytest.raises(jr.ManifestError, match="frame_offset"):
        jr.validate_manifest(m)


def test_manifest_rejects_subset_name_drift(tmp_path):
    m = _cone_manifest(tmp_path)
    m["models"]["subset_name"] = "different_subset"
    with pytest.raises(jr.ManifestError, match="subset_name"):
        jr.validate_manifest(m)


# ── centre derivation + grid ─────────────────────────────────────────────────

def test_derive_center_cone(tmp_path):
    m = _cone_manifest(tmp_path)
    markers = jr._load_consumed_markers(m)
    center = jr.derive_center("cone", markers)
    assert center["sigma_deg"] == 2.0
    assert center["radius_sigma_mult"] == 3.0
    assert center["delay_seconds"] == 0.2
    assert center["frame_offset"] == 54


def test_axis_grids_are_3x3x3_interior(tmp_path):
    m = _screen_manifest(tmp_path)
    center = jr.derive_center("screen_space", jr._load_consumed_markers(m))
    sigma_axis, delay_axis, fo_axis = jr.axis_grids("sal3d", "screen_space", center)
    assert sigma_axis == [0.95, 1.0, 1.05]
    assert delay_axis == [0.0, 0.1, 0.2]
    assert fo_axis == [15, 30, 45]
    assert jr.expected_point_count("sal3d", "screen_space", center) == 27


def test_axis_grids_collapse_near_zero_frame_offset():
    center = {"sigma_deg": 2.0, "radius_sigma_mult": 3.0, "delay_seconds": 0.2, "frame_offset": 0}
    _, _, fo_axis = jr.axis_grids("sal3d", "cone", center)
    assert fo_axis == [0, 15]  # max(0, -15)=0 collapses with centre 0
    assert jr.expected_point_count("sal3d", "cone", center) == 3 * 3 * 2


def test_axis_grids_clip_upper_frame_offset_by_dataset_limit():
    center = {"sigma_deg": 2.0, "radius_sigma_mult": 3.0, "delay_seconds": 0.2, "frame_offset": 54}
    _, _, fo_axis = jr.axis_grids("sal3d", "cone", center)
    assert fo_axis == [39, 54]
    assert jr.expected_point_count("sal3d", "cone", center) == 3 * 3 * 2


# ── identity / anchor / task tag ─────────────────────────────────────────────

def test_anchor_signature_packs_all_three_axes():
    center = {"sigma_deg": 2.0, "radius_sigma_mult": 3.0, "delay_seconds": 0.2, "frame_offset": 54}
    sig = jr.anchor_signature("cone", center)
    assert "sdeg=2.0" in sig and "d=0.2" in sig and "fo=54" in sig


def test_identity_sha1_changes_with_anchor_and_each_free_value():
    common = dict(repo_commit="a" * 40, family="cone_joint_refine", dataset="sal3d",
                  method="cone", texture_type="", axis="joint_refine",
                  window_mode="one_turn_from_start", fixation_data_tag="t", model="dog")
    base = jr.identity_sha1(anchor_signature="sdeg=2.0;rsm=3.0;d=0.2;fo=54",
                            sigma_value=2.0, delay_value=0.2, frame_offset_value=54, **common)
    diff_anchor = jr.identity_sha1(anchor_signature="sdeg=1.0;rsm=3.0;d=0.2;fo=54",
                                   sigma_value=2.0, delay_value=0.2, frame_offset_value=54, **common)
    diff_sigma = jr.identity_sha1(anchor_signature="sdeg=2.0;rsm=3.0;d=0.2;fo=54",
                                  sigma_value=1.9, delay_value=0.2, frame_offset_value=54, **common)
    diff_delay = jr.identity_sha1(anchor_signature="sdeg=2.0;rsm=3.0;d=0.2;fo=54",
                                  sigma_value=2.0, delay_value=0.1, frame_offset_value=54, **common)
    diff_fo = jr.identity_sha1(anchor_signature="sdeg=2.0;rsm=3.0;d=0.2;fo=54",
                               sigma_value=2.0, delay_value=0.2, frame_offset_value=39, **common)
    assert len({base, diff_anchor, diff_sigma, diff_delay, diff_fo}) == 5


def test_task_tag_includes_method_all_axes_and_anchor():
    point = {"sigma_deg": 1.9, "delay_seconds": 0.1, "frame_offset": 39,
             "window_mode": "one_turn_from_start"}
    tag = jr._task_tag_for_joint_point("cone", point, "sdeg=2.0;rsm=3.0;d=0.2;fo=54")
    assert "cone" in tag and "s1.9" in tag and "d0.1" in tag and "fo39" in tag
    assert "sdeg=2.0" in tag and "fo=54" in tag


# ── end-to-end branch run via mock invoke ────────────────────────────────────

def _mock_best_at(method, sigma_target, delay_target, fo_target):
    base_invoke = ev.make_mock_invoke()

    def invoke(point, model):
        row = base_invoke(point, model)
        sigma = point["sigma_deg"] if method == "cone" else point["sigma_multiplier"]
        if (abs(sigma - sigma_target) < 1e-9
                and abs(point["delay_seconds"] - delay_target) < 1e-9
                and int(point["frame_offset"]) == fo_target):
            row["CC"] = 0.99
        return row
    return invoke


def test_run_joint_refine_promotes_and_writes_refined_optimum(tmp_path):
    m = _cone_manifest(tmp_path)
    # best at a feasible off-centre point to prove the refine actually moved.
    invoke = _mock_best_at("cone", 2.1, 0.1, 39)
    result = jr.run_joint_refine_branch(
        m, results_root=tmp_path, invoke=invoke,
        check_smoke=False, check_runtime=False)
    assert result["promoted"] is True
    bb = json.loads(result["branch_best_path"].read_text())
    assert bb["best_params"]["sigma_deg"] == 2.1
    assert bb["best_params"]["radius_sigma_mult"] == 3.0
    assert bb["best_params"]["delay_seconds"] == 0.1
    assert bb["best_params"]["frame_offset"] == 39


def test_run_joint_refine_records_model_set_signature(tmp_path):
    m = _cone_manifest(tmp_path)
    m["models"]["list"] = ["dog", "Pear_L3"]
    jr.run_joint_refine_branch(
        m, results_root=tmp_path, invoke=ev.make_mock_invoke(),
        check_smoke=False, check_runtime=False)
    jsonl = (tmp_path / "ablation" / "cone_joint_refine" / "sal3d" / "cone"
             / "aggregate" / "ablation_runs.jsonl")
    rows = [json.loads(l) for l in jsonl.read_text().splitlines()]
    assert rows
    expected_sig = agg.model_set_signature(["dog", "Pear_L3"])
    for r in rows:
        assert r["model_set_signature"] == expected_sig


def test_run_joint_refine_writes_27_aggregate_points(tmp_path):
    m = _cone_manifest(tmp_path)
    jr.run_joint_refine_branch(
        m, results_root=tmp_path, invoke=ev.make_mock_invoke(),
        check_smoke=False, check_runtime=False)
    jsonl = (tmp_path / "ablation" / "cone_joint_refine" / "sal3d" / "cone"
             / "aggregate" / "ablation_runs.jsonl")
    rows = [json.loads(l) for l in jsonl.read_text().splitlines()
            if json.loads(l).get("status") != "superseded"]
    # Upper frame_offset point is clipped by dataset feasibility, so 18 remain.
    assert len({r["run_id"] for r in rows}) == 18


def test_screen_space_joint_refine_runs_end_to_end(tmp_path):
    m = _screen_manifest(tmp_path)
    invoke = _mock_best_at("screen_space", 1.05, 0.1, 30)
    result = jr.run_joint_refine_branch(
        m, results_root=tmp_path, invoke=invoke,
        check_smoke=False, check_runtime=False)
    assert result["promoted"] is True
    bb = json.loads(result["branch_best_path"].read_text())
    assert bb["best_params"]["sigma_multiplier"] == 1.05
    assert "sigma_px" in bb["best_params"]
    assert bb["best_params"]["delay_seconds"] == 0.1
    assert bb["best_params"]["frame_offset"] == 30
