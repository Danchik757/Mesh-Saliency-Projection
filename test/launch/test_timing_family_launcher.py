"""Tests for the Stage-2 timing family launcher."""
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


launcher = _load("timing_family_launcher")


def _sha40():
    return "c" * 40


def _smoke_files(tmp_path, *, dataset: str, method: str):
    summary = tmp_path / "smoke" / "metrics_summary.csv"
    summary.parent.mkdir(parents=True, exist_ok=True)
    summary.write_text(f"dataset_track,method,n_ok,CC\n{dataset},{method},1,0.5\n")
    smoke = tmp_path / "smoke" / "smoke_gate.json"
    smoke.write_text(json.dumps({
        "repo_commit": _sha40(),
        "metrics_summary_csv": str(summary),
        "point": {"dataset": dataset, "method": method},
        "verdict": {"ok": True, "reason": "green"},
    }))
    return smoke


def _upstream_branch_best(tmp_path, *, family: str, dataset: str, method: str, best_params: dict):
    path = tmp_path / "upstream" / family / dataset / method / "branch_best.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "family": family,
        "dataset": dataset,
        "method": method,
        "stage": "refined" if family.endswith("_sigma") else "sweep",
        "points_to": "refined/final_best.json" if family.endswith("_sigma") else "aggregate/ablation_runs.jsonl#run_id=r1",
        "repo_commit": _sha40(),
        "promoted_at_utc": "2026-06-15T12:00:00Z",
        "best_params": best_params,
        "common_model_set": "rc3_reference_ok",
        "n_models_used": 2,
        "noise_floor_CC": 0.01,
        "best_CC": 0.5,
    }, indent=2))
    return path


def _manifest(tmp_path, *, family: str, dataset: str, method: str, best_params: dict):
    upstream = _upstream_branch_best(
        tmp_path,
        family="cone_sigma" if family == "cone_timing" else "screen_space_sigma",
        dataset=dataset,
        method=method,
        best_params=best_params,
    )
    return {
        "submission": {
            "family": family,
            "dataset": dataset,
            "method": method,
            "texture_type": "non_texture" if dataset == "meshmamba_non_texture" else "",
            "repo_commit": _sha40(),
            "branch": "orchestra/metric-ablation-lab",
            "approved_by": "user",
            "approved_at_utc": "2026-06-15T12:00:00Z",
            "smoke_artifact": str(_smoke_files(tmp_path, dataset=dataset, method=method)),
            "server": "vg-iai",
            "host_root": "/mnt/ssd1/29d_kon/summer_2026",
            "python": "/usr/bin/python3",
            "resolved_env": {"FIXATION_ROOT": "/tmp/fix"},
            "nice_level": 19,
            "ionice_class": 2,
            "ionice_level": 7,
            "timeout_seconds_per_invocation": 1800,
            "max_workers": 4,
            "fixation_data_tag": "processed_fixations_offset0_full_cleaned",
            "window_mode": "one_turn_from_start",
            "delay_seconds": 0.0,
            "frame_offset": 0,
        },
        "sweep": {
            "axis": "delay_seconds",
            "delay_values": [-0.2, 0.0, 0.2],
        },
        "models": {
            "subset_name": "rc3_reference_ok",
            "list": ["m1", "m2"],
        },
        "consumes": {
            "sigma_branch_best": str(upstream),
        },
    }


def _peak_invoke(peak: float = 0.2):
    def invoke(point, model):
        delay = float(point["delay_seconds"])
        cc = max(0.0, 1.0 - abs(delay - peak))
        return {
            "model": model, "status": "ok",
            "CC": round(cc, 4), "SIM": 0.6, "KLD": 0.4, "MSE": 0.03, "MAE": 0.1,
            "Spearman": round(cc, 4), "Cosine": 0.8,
            "AUC_Judd_gt_top_10pct_proxy": 0.8, "AUC_Judd_gt_top_5pct_proxy": 0.82,
            "AUC_Judd_gt_top_1pct_proxy": 0.88, "NSS_gt_top_10pct_proxy": 1.0,
            "NSS_gt_top_5pct_proxy": 1.2, "NSS_gt_top_1pct_proxy": 1.5,
        }
    return invoke


def test_validate_manifest_requires_branch_best_not_stage_marker(tmp_path):
    manifest = _manifest(
        tmp_path, family="cone_timing", dataset="sal3d", method="cone",
        best_params={"sigma_deg": 1.0, "radius_sigma_mult": 3.0},
    )
    bad = json.loads(json.dumps(manifest))
    bad["consumes"]["sigma_branch_best"] = str(tmp_path / "upstream" / "coarse_best.json")
    with pytest.raises(launcher.ManifestError):
        launcher.validate_manifest(bad, check_smoke=False)


def test_cone_timing_branch_writes_branch_best(tmp_path):
    manifest = _manifest(
        tmp_path, family="cone_timing", dataset="sal3d", method="cone",
        best_params={"sigma_deg": 1.0, "radius_sigma_mult": 3.0},
    )
    result = launcher.run_timing_branch(
        manifest, results_root=tmp_path, invoke=_peak_invoke(0.2), check_smoke=True,
    )
    branch_root = tmp_path / "ablation" / "cone_timing" / "sal3d" / "cone"
    assert result["promoted"] is True
    assert result["branch_best_path"] == branch_root / "branch_best.json"
    payload = json.loads((branch_root / "branch_best.json").read_text())
    assert payload["best_params"]["sigma_deg"] == 1.0
    assert payload["best_params"]["radius_sigma_mult"] == 3.0
    assert payload["best_params"]["delay_seconds"] == 0.2
    assert payload["points_to"].startswith("aggregate/ablation_runs.jsonl#run_id=")


def test_screen_space_timing_branch_carries_absolute_sigma(tmp_path):
    manifest = _manifest(
        tmp_path, family="screen_space_timing", dataset="3dva", method="screen_space",
        best_params={"sigma_multiplier": 0.7, "sigma_px": 34.3, "base_sigma": 49.0},
    )
    result = launcher.run_timing_branch(
        manifest, results_root=tmp_path, invoke=_peak_invoke(0.2), check_smoke=True,
    )
    branch_root = tmp_path / "ablation" / "screen_space_timing" / "3dva" / "screen_space"
    assert result["promoted"] is True
    payload = json.loads((branch_root / "branch_best.json").read_text())
    assert payload["best_params"]["sigma_multiplier"] == 0.7
    assert payload["best_params"]["sigma_px"] == 34.3
    assert payload["best_params"]["base_sigma"] == 49.0
    assert payload["best_params"]["delay_seconds"] == 0.2


def test_timing_branch_preserves_explicit_frame_offset_54(tmp_path):
    manifest = _manifest(
        tmp_path, family="cone_timing", dataset="3dva", method="cone",
        best_params={"sigma_deg": 1.0, "radius_sigma_mult": 3.0},
    )
    manifest["submission"]["frame_offset"] = 54
    seen = []

    def invoke(point, model):
        seen.append((point["frame_offset"], point["delay_seconds"]))
        return _peak_invoke(0.2)(point, model)

    result = launcher.run_timing_branch(
        manifest, results_root=tmp_path, invoke=invoke, check_smoke=True,
    )
    assert result["promoted"] is True
    assert seen
    assert all(frame_offset == 54 for frame_offset, _ in seen)
    assert {delay for _, delay in seen} == {-0.2, 0.0, 0.2}


def test_stage_points_embed_fixed_sigma_in_task_tag(tmp_path):
    manifest = _manifest(
        tmp_path, family="screen_space_timing", dataset="3dva", method="screen_space",
        best_params={"sigma_multiplier": 0.7, "sigma_px": 34.3, "base_sigma": 49.0},
    )
    consumed = launcher._load_consumed_branch_best(manifest)
    points = launcher._stage_points(manifest, consumed)
    assert {p["delay_seconds"] for p in points} == {-0.2, 0.0, 0.2}
    assert all("smul=0.7" in p["task_tag"] for p in points)
    assert all("spx=34.3" in p["task_tag"] for p in points)


def test_timing_branch_records_model_set_signature(tmp_path):
    manifest = _manifest(
        tmp_path, family="cone_timing", dataset="sal3d", method="cone",
        best_params={"sigma_deg": 1.0, "radius_sigma_mult": 3.0},
    )
    launcher.run_timing_branch(
        manifest, results_root=tmp_path, invoke=_peak_invoke(0.2), check_smoke=True,
    )
    jsonl = tmp_path / "ablation" / "cone_timing" / "sal3d" / "cone" / "aggregate" / "ablation_runs.jsonl"
    rows = [json.loads(line) for line in jsonl.read_text().splitlines()]
    expected = launcher.agg.model_set_signature(["m1", "m2"])
    assert rows
    assert all(r["model_set_signature"] == expected for r in rows)


def test_resume_reuses_identity_rows_and_does_not_duplicate_points(tmp_path):
    manifest = _manifest(
        tmp_path, family="cone_timing", dataset="sal3d", method="cone",
        best_params={"sigma_deg": 1.0, "radius_sigma_mult": 3.0},
    )
    launcher.run_timing_branch(
        manifest, results_root=tmp_path, invoke=_peak_invoke(0.2), check_smoke=True,
    )
    jsonl = tmp_path / "ablation" / "cone_timing" / "sal3d" / "cone" / "aggregate" / "ablation_runs.jsonl"
    before = jsonl.read_text().splitlines()
    launcher.run_timing_branch(
        manifest, results_root=tmp_path,
        invoke=lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not rerun atoms")),
        check_smoke=True,
    )
    after = jsonl.read_text().splitlines()
    assert before == after


def test_real_invoke_for_manifest_uses_submission_runtime_contract(tmp_path, monkeypatch):
    manifest = _manifest(
        tmp_path, family="screen_space_timing", dataset="3dva", method="screen_space",
        best_params={"sigma_multiplier": 0.7, "sigma_px": 34.3, "base_sigma": 49.0},
    )
    captured = {}

    def fake_subprocess_invoke(point, model, **kwargs):
        captured["point"] = point
        captured["model"] = model
        captured["kwargs"] = kwargs
        return {"model": model, "status": "ok", "CC": 0.5}

    monkeypatch.setattr(launcher.ev, "subprocess_evaluator_invoke", fake_subprocess_invoke)
    invoke = launcher._real_invoke_for_manifest(manifest, results_root=tmp_path)
    invoke({"dataset": "3dva", "method": "screen_space", "delay_seconds": 0.2, "sigma_px": 34.3}, "camel")

    assert captured["model"] == "camel"
    assert captured["kwargs"]["work_dir"] == (
        tmp_path / "ablation" / "_work" / "screen_space_timing" / "3dva" / "screen_space"
    )
    assert captured["kwargs"]["timeout"] == 1800
    assert captured["kwargs"]["preflight"] is False
    assert captured["kwargs"]["python"] == "/usr/bin/python3"
    assert captured["kwargs"]["env"] == {"FIXATION_ROOT": "/tmp/fix"}


def test_main_non_mock_rejects_repo_commit_drift(tmp_path, monkeypatch, capsys):
    manifest = _manifest(
        tmp_path, family="cone_timing", dataset="sal3d", method="cone",
        best_params={"sigma_deg": 1.0, "radius_sigma_mult": 3.0},
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))

    monkeypatch.setattr(launcher, "_require_current_checkout_commit", lambda manifest: (_ for _ in ()).throw(
        launcher.RuntimeGateError("HEAD drift")
    ))
    monkeypatch.setattr(launcher, "_require_manifest_runtime", lambda manifest: None)
    monkeypatch.setattr(launcher, "run_timing_branch", lambda **kwargs: (_ for _ in ()).throw(
        AssertionError("run_timing_branch must not be called")
    ))
    monkeypatch.setattr(sys, "argv", [
        "timing_family_launcher.py", "--manifest", str(manifest_path), "--results-root", str(tmp_path),
    ])

    rc = launcher.main()
    err = capsys.readouterr().err
    assert rc == 2
    assert "RUNTIME GATE FAILED" in err
    assert "HEAD drift" in err
