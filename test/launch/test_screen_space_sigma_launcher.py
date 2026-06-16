"""Tests for the screen_space_sigma family launcher."""
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


launcher = _load("screen_space_sigma_launcher")


def _sha40():
    return "b" * 40


def _texture_type_for(dataset: str) -> str:
    if dataset == "meshmamba_non_texture":
        return "non_texture"
    if dataset == "meshmamba_rgb_texture":
        return "rgb_texture"
    return ""


def _smoke_files(tmp_path, dataset="sal3d"):
    summary = tmp_path / "smoke" / "metrics_summary.csv"
    summary.parent.mkdir(parents=True, exist_ok=True)
    summary.write_text("dataset_track,method,n_ok,CC\nsal3d,screen_space,1,0.5\n")
    smoke = tmp_path / "smoke" / "smoke_gate.json"
    smoke.write_text(json.dumps({
        "repo_commit": _sha40(),
        "metrics_summary_csv": str(summary),
        "point": {"dataset": dataset, "method": "screen_space"},
        "verdict": {"ok": True, "reason": "green"},
    }))
    return smoke


def _manifest(tmp_path, *, dataset="sal3d", stage="coarse", sigma_values=None, consumes=None):
    if sigma_values is None:
        sigma_values = list(launcher.COARSE_GRID)
    return {
        "submission": {
            "family": "screen_space_sigma",
            "branch_stage": stage,
            "dataset": dataset,
            "method": "screen_space",
            "texture_type": _texture_type_for(dataset),
            "repo_commit": _sha40(),
            "branch": "orchestra/metric-ablation-lab",
            "approved_by": "user",
            "approved_at_utc": "2026-06-15T12:00:00Z",
            "smoke_artifact": str(_smoke_files(tmp_path, dataset=dataset)),
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
            "sigma_param": "sigma_multiplier",
            "sigma_values": sigma_values,
            "edge_expansion": False,
        },
        "models": {
            "subset_name": "rc3_reference_ok",
            "list": ["m1", "m2"],
        },
        "consumes": consumes or {},
    }


def _peak_invoke(peak: float = 1.0):
    def invoke(point, model):
        sigma = float(point["sigma_multiplier"])
        cc = max(0.0, 1.0 - abs(sigma - peak))
        row = {
            "model": model, "status": "ok",
            "CC": round(cc, 4), "SIM": 0.6, "KLD": 0.4, "MSE": 0.03, "MAE": 0.1,
            "Spearman": round(cc, 4), "Cosine": 0.8,
            "AUC_Judd_gt_top_10pct_proxy": 0.8, "AUC_Judd_gt_top_5pct_proxy": 0.82,
            "AUC_Judd_gt_top_1pct_proxy": 0.88, "NSS_gt_top_10pct_proxy": 1.0,
            "NSS_gt_top_5pct_proxy": 1.2, "NSS_gt_top_1pct_proxy": 1.5,
        }
        return row
    return invoke


def test_validate_manifest_refined_requires_matching_coarse_marker(tmp_path):
    coarse_marker = tmp_path / "coarse_best.json"
    coarse_marker.write_text(json.dumps({
        "family": "screen_space_sigma",
        "stage": "coarse",
        "dataset": "sal3d",
        "method": "screen_space",
        "repo_commit": _sha40(),
        "best_params": {"sigma_multiplier": 1.0, "sigma_px": 26.3, "base_sigma": 26.3},
    }))
    manifest = _manifest(
        tmp_path, stage="refined",
        sigma_values=launcher.refined_grid(1.0),
        consumes={"coarse_best_marker": str(coarse_marker)},
    )
    launcher.validate_manifest(manifest)

    bad = _manifest(
        tmp_path, stage="refined",
        sigma_values=[0.8, 0.9, 1.0],
        consumes={"coarse_best_marker": str(coarse_marker)},
    )
    with pytest.raises(launcher.ManifestError):
        launcher.validate_manifest(bad)


def test_absolute_sigma_mapping_for_px_and_screen():
    assert launcher._absolute_sigma_mapping("3dva", 0.7) == {"sigma_px": 34.3}
    assert launcher._absolute_sigma_mapping("sal3d", 1.5) == {"sigma_px": 39.45}
    assert launcher._absolute_sigma_mapping("meshmamba_non_texture", 0.7) == {"sigma_screen": 0.035}


def test_refined_grid_and_skip_refined_policy():
    assert launcher.refined_grid(1.0) == [0.75, 0.88, 1.0, 1.12, 1.25]
    gate = {
        "promoted": True,
        "best": {"sigma_multiplier": 1.0},
        "best_CC": 0.50,
        "second_best_CC": 0.40,
        "noise_floor_CC": 0.02,
    }
    assert launcher.decide_skip_refined(gate) is True
    gate_edge = dict(gate, best={"sigma_multiplier": 1.5})
    assert launcher.decide_skip_refined(gate_edge) is False


def test_coarse_run_creates_family_layout_and_refined_stub(tmp_path):
    manifest = _manifest(tmp_path, dataset="sal3d")
    result = launcher.run_screen_space_sigma_branch(
        manifest, results_root=tmp_path, invoke=launcher.ev.make_mock_invoke(), check_smoke=True,
    )
    coarse_root = tmp_path / "ablation" / "screen_space_sigma" / "sal3d" / "screen_space" / "coarse"
    assert result["promoted"] is True
    assert result["skip_refined"] is False
    assert (coarse_root / "aggregate" / "ablation_runs.csv").is_file()
    assert result["coarse_best_path"] == coarse_root / "coarse_best.json"
    assert result["refined_manifest_stub_path"] == (
        tmp_path / "ablation" / "screen_space_sigma" / "sal3d" / "screen_space" / "refined" / "refined_manifest_stub.json"
    )
    assert result["branch_best_path"] is None


def test_coarse_skip_refined_writes_root_branch_best_and_best_params(tmp_path):
    manifest = _manifest(tmp_path, dataset="meshmamba_non_texture")
    result = launcher.run_screen_space_sigma_branch(
        manifest, results_root=tmp_path, invoke=_peak_invoke(1.0), check_smoke=True,
    )
    branch_root = tmp_path / "ablation" / "screen_space_sigma" / "meshmamba_non_texture" / "screen_space"
    assert result["promoted"] is True
    assert result["skip_refined"] is True
    assert result["branch_best_path"] == branch_root / "branch_best.json"
    branch_best = json.loads((branch_root / "branch_best.json").read_text())
    assert branch_best["stage"] == "coarse_skipped_refine"
    assert branch_best["points_to"] == "coarse/coarse_best.json"
    assert branch_best["best_params"]["sigma_multiplier"] == 1.0
    assert branch_best["best_params"]["sigma_screen"] == 0.05


def test_refined_run_writes_final_best_and_root_pointer(tmp_path):
    coarse_manifest = _manifest(tmp_path, dataset="sal3d")
    coarse_result = launcher.run_screen_space_sigma_branch(
        coarse_manifest, results_root=tmp_path, invoke=launcher.ev.make_mock_invoke(), check_smoke=True,
    )
    refined_manifest = json.loads(Path(coarse_result["refined_manifest_stub_path"]).read_text())
    result = launcher.run_screen_space_sigma_branch(
        refined_manifest, results_root=tmp_path, invoke=_peak_invoke(1.0), check_smoke=True,
    )
    branch_root = tmp_path / "ablation" / "screen_space_sigma" / "sal3d" / "screen_space"
    assert result["promoted"] is True
    assert result["final_best_path"] == branch_root / "refined" / "final_best.json"
    assert result["branch_best_path"] == branch_root / "branch_best.json"
    branch_best = json.loads((branch_root / "branch_best.json").read_text())
    assert branch_best["stage"] == "refined"
    assert branch_best["points_to"] == "refined/final_best.json"


def test_resume_reuses_identity_rows_and_does_not_duplicate_points(tmp_path):
    manifest = _manifest(tmp_path, dataset="sal3d")
    launcher.run_screen_space_sigma_branch(
        manifest, results_root=tmp_path, invoke=_peak_invoke(1.0), check_smoke=True,
    )
    coarse_jsonl = (
        tmp_path / "ablation" / "screen_space_sigma" / "sal3d" / "screen_space"
        / "coarse" / "aggregate" / "ablation_runs.jsonl"
    )
    before = coarse_jsonl.read_text().splitlines()
    launcher.run_screen_space_sigma_branch(
        manifest, results_root=tmp_path,
        invoke=lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not rerun atoms")),
        check_smoke=True,
    )
    after = coarse_jsonl.read_text().splitlines()
    assert before == after


def test_screen_space_sigma_records_model_set_signature(tmp_path):
    manifest = _manifest(tmp_path, dataset="sal3d")
    launcher.run_screen_space_sigma_branch(
        manifest, results_root=tmp_path, invoke=_peak_invoke(1.0), check_smoke=True,
    )
    coarse_jsonl = (
        tmp_path / "ablation" / "screen_space_sigma" / "sal3d" / "screen_space"
        / "coarse" / "aggregate" / "ablation_runs.jsonl"
    )
    rows = [json.loads(line) for line in coarse_jsonl.read_text().splitlines()]
    expected = launcher.agg.model_set_signature(["m1", "m2"])
    assert rows
    assert all(r["model_set_signature"] == expected for r in rows)


def test_real_invoke_for_manifest_uses_submission_runtime_contract(tmp_path, monkeypatch):
    manifest = _manifest(tmp_path, dataset="sal3d")
    captured = {}

    def fake_subprocess_invoke(point, model, **kwargs):
        captured["point"] = point
        captured["model"] = model
        captured["kwargs"] = kwargs
        return {"model": model, "status": "ok", "CC": 0.5}

    monkeypatch.setattr(launcher.ev, "subprocess_evaluator_invoke", fake_subprocess_invoke)
    invoke = launcher._real_invoke_for_manifest(manifest, results_root=tmp_path)
    invoke({"dataset": "sal3d", "method": "screen_space", "sigma_multiplier": 1.5, "sigma_px": 39.45}, "dog")

    assert captured["model"] == "dog"
    assert captured["kwargs"]["work_dir"] == (
        tmp_path / "ablation" / "_work" / "screen_space_sigma" / "sal3d" / "screen_space" / "coarse"
    )
    assert captured["kwargs"]["timeout"] == 1800
    assert captured["kwargs"]["preflight"] is False
    assert captured["kwargs"]["python"] == "/usr/bin/python3"
    assert captured["kwargs"]["env"] == {"FIXATION_ROOT": "/tmp/fix"}
    assert captured["kwargs"]["fixation_root"] == "/tmp/fix"


def test_main_non_mock_rejects_repo_commit_drift(tmp_path, monkeypatch, capsys):
    manifest = _manifest(tmp_path, dataset="sal3d")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))

    monkeypatch.setattr(launcher, "_require_current_checkout_commit", lambda manifest: (_ for _ in ()).throw(
        launcher.RuntimeGateError("HEAD drift")
    ))
    monkeypatch.setattr(launcher, "_require_manifest_runtime", lambda manifest: None)
    monkeypatch.setattr(launcher, "run_screen_space_sigma_branch", lambda **kwargs: (_ for _ in ()).throw(
        AssertionError("run_screen_space_sigma_branch must not be called")
    ))
    monkeypatch.setattr(sys, "argv", [
        "screen_space_sigma_launcher.py", "--manifest", str(manifest_path), "--results-root", str(tmp_path),
    ])

    rc = launcher.main()
    err = capsys.readouterr().err
    assert rc == 2
    assert "RUNTIME GATE FAILED" in err
    assert "HEAD drift" in err


def test_main_non_mock_runs_with_stage_preflight_and_real_invoke(tmp_path, monkeypatch):
    manifest = _manifest(tmp_path, dataset="sal3d")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))

    called = {"commit": 0, "runtime": 0, "invoke": None}

    monkeypatch.setattr(launcher, "_require_current_checkout_commit", lambda manifest: called.__setitem__("commit", called["commit"] + 1))
    monkeypatch.setattr(launcher, "_require_manifest_runtime", lambda manifest: called.__setitem__("runtime", called["runtime"] + 1))

    def fake_run_branch(manifest, *, results_root, invoke, check_smoke):
        called["invoke"] = invoke
        return {
            "stage": manifest["submission"]["branch_stage"],
            "promoted": True,
            "skip_refined": False,
            "branch_best_path": None,
        }

    monkeypatch.setattr(launcher, "run_screen_space_sigma_branch", fake_run_branch)
    monkeypatch.setattr(sys, "argv", [
        "screen_space_sigma_launcher.py", "--manifest", str(manifest_path), "--results-root", str(tmp_path),
    ])

    rc = launcher.main()
    assert rc == 0
    assert called["commit"] == 1
    assert called["runtime"] == 1

    captured = {}

    def fake_subprocess_invoke(point, model, **kwargs):
        captured["point"] = point
        captured["model"] = model
        captured["kwargs"] = kwargs
        return {"model": model, "status": "ok", "CC": 0.5}

    monkeypatch.setattr(launcher.ev, "subprocess_evaluator_invoke", fake_subprocess_invoke)
    called["invoke"]({"dataset": "sal3d", "method": "screen_space", "sigma_multiplier": 1.0, "sigma_px": 26.3}, "dog")
    assert captured["kwargs"]["preflight"] is False
    assert captured["kwargs"]["timeout"] == 1800
    assert captured["kwargs"]["python"] == "/usr/bin/python3"
