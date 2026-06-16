"""Tests for the frame_offset family launcher (both cone + screen_space)."""
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


fo = _load("frame_offset_family_launcher")
agg = _load("ablation_aggregation")
ev = _load("run_evaluator_sweep")


# ── fixtures ────────────────────────────────────────────────────────────────

def _write_smoke(tmp_path, dataset, method):
    smoke_dir = tmp_path / "smoke"
    smoke_dir.mkdir()
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


def _write_upstream_timing_branch_best(tmp_path, *, family, dataset, method, best_params):
    upstream_dir = tmp_path / "upstream"
    upstream_dir.mkdir()
    payload = {
        "family": family,
        "dataset": dataset,
        "method": method,
        "stage": "sweep",
        "points_to": "aggregate/ablation_runs.jsonl#run_id=u1",
        "repo_commit": "a" * 40,
        "promoted_at_utc": "2026-06-16T01:00:00Z",
        "best_params": best_params,
        "common_model_set": "rc3_reference_ok",
        "n_models_used": 1,
        "noise_floor_CC": 0.01,
        "best_CC": 0.5,
        "artifact_run_id": "u1",
    }
    p = upstream_dir / "branch_best.json"
    p.write_text(json.dumps(payload))
    return p


def _cone_manifest(tmp_path):
    upstream = _write_upstream_timing_branch_best(
        tmp_path, family="cone_timing", dataset="sal3d", method="cone",
        best_params={"sigma_deg": 2.0, "radius_sigma_mult": 3.0, "delay_seconds": 0.2})
    smoke = _write_smoke(tmp_path, "sal3d", "cone")
    return {
        "submission": {
            "family": "cone_frame_offset", "dataset": "sal3d", "method": "cone",
            "texture_type": "", "repo_commit": "a" * 40,
            "smoke_artifact": str(smoke),
            "fixation_data_tag": "tag", "window_mode": "one_turn_from_start",
            "resolved_env": {"FIXATION_ROOT": "/x"}, "python": "python3",
            "timeout_seconds_per_invocation": 60, "max_workers": 1,
        },
        "sweep": {"frame_offset_values": [0, 15, 30, 54]},
        "models": {"subset_name": "rc3_reference_ok", "list": ["dog"]},
        "consumes": {"timing_branch_best": str(upstream)},
    }


def _screen_manifest(tmp_path):
    upstream = _write_upstream_timing_branch_best(
        tmp_path, family="screen_space_timing", dataset="sal3d", method="screen_space",
        best_params={"sigma_multiplier": 1.0, "sigma_px": 26.3,
                     "base_sigma": 26.3, "delay_seconds": 0.1})
    smoke = _write_smoke(tmp_path, "sal3d", "screen_space")
    return {
        "submission": {
            "family": "screen_space_frame_offset", "dataset": "sal3d", "method": "screen_space",
            "texture_type": "", "repo_commit": "a" * 40,
            "smoke_artifact": str(smoke),
            "fixation_data_tag": "tag", "window_mode": "one_turn_from_start",
            "resolved_env": {"FIXATION_ROOT": "/x"}, "python": "python3",
            "timeout_seconds_per_invocation": 60, "max_workers": 1,
        },
        "sweep": {"frame_offset_values": [0, 15, 30, 54]},
        "models": {"subset_name": "rc3_reference_ok", "list": ["dog"]},
        "consumes": {"timing_branch_best": str(upstream)},
    }


# ── manifest validation ─────────────────────────────────────────────────────

def test_manifest_validates_for_cone(tmp_path):
    fo.validate_manifest(_cone_manifest(tmp_path))


def test_manifest_validates_for_screen_space(tmp_path):
    fo.validate_manifest(_screen_manifest(tmp_path))


def test_manifest_rejects_substage_marker(tmp_path):
    m = _cone_manifest(tmp_path)
    # rename target file to look like a sub-stage marker
    p = Path(m["consumes"]["timing_branch_best"])
    bad = p.parent / "coarse_best.json"
    bad.write_text(p.read_text())
    m["consumes"]["timing_branch_best"] = str(bad)
    with pytest.raises(fo.ManifestError, match="branch_best.json"):
        fo.validate_manifest(m)


def test_manifest_rejects_upstream_without_delay_seconds(tmp_path):
    m = _cone_manifest(tmp_path)
    src_path = Path(m["consumes"]["timing_branch_best"])
    obj = json.loads(src_path.read_text())
    obj["best_params"].pop("delay_seconds")
    src_path.write_text(json.dumps(obj))
    with pytest.raises(fo.ManifestError, match="delay_seconds"):
        fo.validate_manifest(m)


def test_manifest_rejects_duplicate_frame_offsets(tmp_path):
    m = _cone_manifest(tmp_path)
    m["sweep"]["frame_offset_values"] = [0, 30, 30, 54]
    with pytest.raises(fo.ManifestError, match="unique"):
        fo.validate_manifest(m)


def test_manifest_rejects_infeasible_frame_offsets_for_fixed_delay(tmp_path):
    upstream = _write_upstream_timing_branch_best(
        tmp_path,
        family="screen_space_timing",
        dataset="meshmamba_non_texture",
        method="screen_space",
        best_params={
            "sigma_multiplier": 0.38,
            "sigma_screen": 0.019,
            "base_sigma": 0.05,
            "delay_seconds": 0.0,
        },
    )
    smoke = _write_smoke(tmp_path, "meshmamba_non_texture", "screen_space")
    manifest = {
        "submission": {
            "family": "screen_space_frame_offset",
            "dataset": "meshmamba_non_texture",
            "method": "screen_space",
            "texture_type": "non_texture",
            "repo_commit": "a" * 40,
            "smoke_artifact": str(smoke),
            "fixation_data_tag": "tag",
            "window_mode": "one_turn_from_start",
            "resolved_env": {"FIXATION_ROOT": "/x"},
            "python": "python3",
            "timeout_seconds_per_invocation": 60,
            "max_workers": 1,
        },
        "sweep": {"frame_offset_values": [0, 54, 90]},
        "models": {"subset_name": "rc3_reference_ok", "list": ["Watermelon_V1_L3"]},
        "consumes": {"timing_branch_best": str(upstream)},
    }
    with pytest.raises(fo.ManifestError, match="infeasible points"):
        fo.validate_manifest(manifest)


def test_manifest_rejects_subset_name_drift(tmp_path):
    m = _cone_manifest(tmp_path)
    m["models"]["subset_name"] = "different_subset"
    with pytest.raises(fo.ManifestError, match="subset_name"):
        fo.validate_manifest(m)


# ── identity & task tag ──────────────────────────────────────────────────────

def test_identity_uses_fixed_upstream_signature_packing_sigma_and_delay():
    cone_params = {"sigma_deg": 2.0, "radius_sigma_mult": 3.0, "delay_seconds": 0.2}
    sig_a = fo._fixed_upstream_signature("cone", cone_params)
    sig_b = fo._fixed_upstream_signature("cone", {**cone_params, "delay_seconds": 0.5})
    sig_c = fo._fixed_upstream_signature("cone", {**cone_params, "sigma_deg": 1.0})
    # Different delay or different sigma -> different signature
    assert sig_a != sig_b
    assert sig_a != sig_c
    # And both sigma + delay show up in the string
    assert "sdeg=2.0" in sig_a and "d=0.2" in sig_a


def test_identity_sha1_changes_with_upstream_signature():
    common = dict(repo_commit="a" * 40, family="cone_frame_offset", dataset="sal3d",
                  method="cone", texture_type="", axis="frame_offset", axis_value=54,
                  window_mode="one_turn_from_start", fixation_data_tag="t", model="dog")
    sha_a = fo.identity_sha1(fixed_upstream_signature="sdeg=2.0;rsm=3.0;d=0.2", **common)
    sha_b = fo.identity_sha1(fixed_upstream_signature="sdeg=1.0;rsm=3.0;d=0.2", **common)
    sha_c = fo.identity_sha1(fixed_upstream_signature="sdeg=2.0;rsm=3.0;d=0.5", **common)
    assert sha_a != sha_b and sha_a != sha_c


def test_task_tag_includes_method_frame_offset_and_upstream_signature():
    point = {"frame_offset": 54}
    tag = fo._task_tag_for_frame_offset_point("cone", point, "sdeg=2.0;rsm=3.0;d=0.2")
    assert "cone" in tag and "fo54" in tag
    # upstream signature parts must be packed in (semicolons become underscores)
    assert "sdeg=2.0" in tag and "d=0.2" in tag


# ── end-to-end branch run via mock invoke ───────────────────────────────────


def _mock_with_better_fo54(point, model):
    base = ev.make_mock_invoke()(point, model)
    fo_val = int(point.get("frame_offset", 0))
    base["CC"] = round(0.40 + (0.10 if fo_val == 54 else 0.0), 4)
    return base


def test_run_frame_offset_branch_promotes_and_writes_branch_best(tmp_path):
    m = _cone_manifest(tmp_path)
    result = fo.run_frame_offset_branch(
        m, results_root=tmp_path, invoke=_mock_with_better_fo54,
        check_smoke=False, check_runtime=False)
    assert result["promoted"] is True
    bb = json.loads(result["branch_best_path"].read_text())
    # best_params must carry sigma + delay (from upstream) AND frame_offset (the swept axis)
    assert bb["best_params"]["sigma_deg"] == 2.0
    assert bb["best_params"]["radius_sigma_mult"] == 3.0
    assert bb["best_params"]["delay_seconds"] == 0.2
    assert bb["best_params"]["frame_offset"] == 54


def test_run_frame_offset_branch_records_model_set_signature(tmp_path):
    m = _cone_manifest(tmp_path)
    m["models"]["list"] = ["dog", "Pear_L3"]
    fo.run_frame_offset_branch(
        m, results_root=tmp_path, invoke=ev.make_mock_invoke(),
        check_smoke=False, check_runtime=False)
    jsonl = (tmp_path / "ablation" / "cone_frame_offset" / "sal3d" / "cone"
             / "aggregate" / "ablation_runs.jsonl")
    rows = [json.loads(l) for l in jsonl.read_text().splitlines()]
    assert rows
    expected_sig = agg.model_set_signature(["dog", "Pear_L3"])
    for r in rows:
        assert r["model_set_signature"] == expected_sig


def test_screen_space_frame_offset_runs_end_to_end(tmp_path):
    m = _screen_manifest(tmp_path)
    result = fo.run_frame_offset_branch(
        m, results_root=tmp_path, invoke=ev.make_mock_invoke(),
        check_smoke=False, check_runtime=False)
    assert result["promoted"] is True
    bb = json.loads(result["branch_best_path"].read_text())
    assert bb["best_params"]["sigma_px"] == 26.3
    assert bb["best_params"]["delay_seconds"] == 0.1
    assert "frame_offset" in bb["best_params"]


def test_aggregate_rows_ignores_superseded_entries(tmp_path):
    agg_dir = tmp_path / "aggregate"
    agg_dir.mkdir(parents=True)
    jsonl = agg_dir / "ablation_runs.jsonl"
    jsonl.write_text(
        "\n".join([
            json.dumps({"run_id": "r1", "status": "superseded", "frame_offset": 0, "CC": 0.1}),
            json.dumps({"run_id": "r1", "status": "ok", "frame_offset": 0, "CC": 0.2}),
        ])
    )
    rows = fo._aggregate_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["status"] == "ok"
    assert rows[0]["CC"] == 0.2


def test_submission_fixation_root_accepts_processed_fixations_fallback(tmp_path, monkeypatch):
    m = _cone_manifest(tmp_path)
    m["submission"]["resolved_env"] = {"REPROJECT_PROCESSED_FIXATIONS_ROOT": "/alt/fix"}
    seen = {}

    def fake_require(dataset, method, *, fixation_root=None, env=None):
        seen["fixation_root"] = fixation_root
        seen["env"] = env
        return {"ok": True, "items": []}

    monkeypatch.setattr(fo.pf, "require", fake_require)
    monkeypatch.setattr(fo.pf, "require_runtime_dependencies", lambda *a, **k: None)
    fo._require_manifest_runtime(m)
    assert seen["fixation_root"] == "/alt/fix"
    assert seen["env"]["REPROJECT_PROCESSED_FIXATIONS_ROOT"] == "/alt/fix"
