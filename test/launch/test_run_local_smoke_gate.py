"""Tests for the local Stage-2 smoke gate launcher."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent


def _load(name):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


gate = _load("run_local_smoke_gate")
ev = _load("run_evaluator_sweep")


def test_mock_smoke_gate_green(tmp_path, monkeypatch):
    asset_report = {
        "dataset": "meshmamba_non_texture", "method": "cone", "ok": True,
        "items": [
            {"name": "fixation_root", "kind": "fixation", "required": True, "present": True,
             "resolved_path": "/tmp/fix", "source_env": None, "envs": ["FIXATION_ROOT"],
             "source": "default", "checked_paths": []},
            {"name": "json_root", "kind": "placement_json", "required": True, "present": True,
             "resolved_path": "/tmp/json", "source_env": None, "envs": ["MESHMAMBA_JSON_ROOT"],
             "source": "auto", "checked_paths": []},
        ],
        "missing": [],
    }
    monkeypatch.setattr(gate.pf, "preflight", lambda *a, **k: asset_report)
    monkeypatch.setattr(gate, "_git", lambda *a: "abc123")

    verdict, run_dir = gate.run_local_smoke_gate(
        dataset="meshmamba_non_texture", method="cone", model="Pear_L3",
        sigma_param="sigma_deg", sigma_value=1.0, radius_sigma_mult=3.0,
        results_root=tmp_path, stage="smoke_gate_test", mock=True, command_argv=["python3", "gate.py"],
    )

    assert verdict["ok"] is True and verdict["reason"] == "green"
    assert (run_dir / "aggregate_row.json").is_file()
    smoke_root = tmp_path / "ablation" / "smoke_gate_test" / "meshmamba_non_texture" / "cone" / "_smoke_gate"
    payload = json.loads((smoke_root / "smoke_gate.json").read_text())
    assert payload["verdict"]["ok"] is True
    assert payload["repo_commit"] == "abc123"
    assert payload["command_argv"] == ["python3", "gate.py"]
    assert payload["metrics_summary_csv"].endswith("/metrics_summary.csv")
    assert (smoke_root / "resolved_env.sh").is_file()
    runtime_md = (smoke_root / "runtime_preflight.md").read_text()
    assert "mock_skip" in runtime_md


def test_asset_preflight_failure_stops_before_run(tmp_path, monkeypatch):
    asset_report = {
        "dataset": "meshmamba_non_texture", "method": "cone", "ok": False,
        "items": [], "missing": [{"name": "dataset_root", "flag": "--dataset-root", "kind": "mesh",
                                  "envs": ["MESHMAMBA_NON_TEXTURE_ROOT"], "checked_paths": []}],
    }
    monkeypatch.setattr(gate.pf, "preflight", lambda *a, **k: asset_report)
    monkeypatch.setattr(gate, "_git", lambda *a: "abc123")

    called = {"n": 0}

    def _boom(*a, **k):
        called["n"] += 1
        raise AssertionError("run_evaluator_sweep must not be called")

    monkeypatch.setattr(gate.ev, "run_evaluator_sweep", _boom)
    verdict, smoke_root = gate.run_local_smoke_gate(
        dataset="meshmamba_non_texture", method="cone", model="Pear_L3",
        sigma_param="sigma_deg", sigma_value=1.0, radius_sigma_mult=3.0,
        results_root=tmp_path, stage="smoke_gate_fail", mock=False,
    )
    assert verdict == {"ok": False, "reason": "asset_preflight_failed"}
    assert called["n"] == 0
    assert (smoke_root / "smoke_gate.json").is_file()


def test_runtime_dependency_failure_stops_before_run(tmp_path, monkeypatch):
    asset_report = {
        "dataset": "meshmamba_non_texture", "method": "cone", "ok": True,
        "items": [], "missing": [],
    }
    runtime_report = {
        "method": "cone", "python": "python3", "ok": False,
        "items": [{"module": "rtree", "present": False, "reason": "ray", "error": "missing"}],
        "missing": [{"module": "rtree"}],
    }
    monkeypatch.setattr(gate.pf, "preflight", lambda *a, **k: asset_report)
    monkeypatch.setattr(gate.pf, "runtime_dependency_report", lambda *a, **k: runtime_report)
    monkeypatch.setattr(gate, "_git", lambda *a: "abc123")

    called = {"n": 0}
    monkeypatch.setattr(gate.ev, "run_evaluator_sweep", lambda *a, **k: called.__setitem__("n", called["n"] + 1))

    verdict, smoke_root = gate.run_local_smoke_gate(
        dataset="meshmamba_non_texture", method="cone", model="Pear_L3",
        sigma_param="sigma_deg", sigma_value=1.0, radius_sigma_mult=3.0,
        results_root=tmp_path, stage="smoke_gate_dep_fail", mock=False,
    )
    assert verdict == {"ok": False, "reason": "runtime_dependency_failed"}
    assert called["n"] == 0
    assert (smoke_root / "runtime_preflight.md").is_file()


def test_red_smoke_when_aggregate_not_ok(tmp_path, monkeypatch):
    asset_report = {
        "dataset": "meshmamba_non_texture", "method": "cone", "ok": True,
        "items": [], "missing": [],
    }
    monkeypatch.setattr(gate.pf, "preflight", lambda *a, **k: asset_report)
    monkeypatch.setattr(gate, "_git", lambda *a: "abc123")

    run_dir = tmp_path / "fake_run"
    run_dir.mkdir()
    (run_dir / "aggregate_row.json").write_text(json.dumps({
        "artifact_run_id": "r1", "status": "empty", "n_ok": 0, "n_failed": 1, "n_total_models": 1,
    }))
    monkeypatch.setattr(gate.ev, "run_evaluator_sweep", lambda *a, **k: [run_dir])

    verdict, out_dir = gate.run_local_smoke_gate(
        dataset="meshmamba_non_texture", method="cone", model="Pear_L3",
        sigma_param="sigma_deg", sigma_value=1.0, radius_sigma_mult=3.0,
        results_root=tmp_path, stage="smoke_gate_red", mock=True,
    )
    assert verdict["ok"] is False and verdict["reason"] == "smoke_run_failed"
    assert out_dir == run_dir


def test_build_point_applies_override():
    point = gate._build_point(
        dataset="sal3d", method="cone", sigma_param="sigma_deg", sigma_value=2.0,
        radius_sigma_mult=3.0, delay_seconds=0.2, window_mode="one_turn_from_start",
        frame_offset=54,
    )
    assert point["dataset"] == "sal3d"
    assert point["sigma_deg"] == 2.0
    assert point["radius_sigma_mult"] == 3.0
    assert point["delay_seconds"] == 0.2
    assert point["frame_offset"] == 54


def test_git_cwd_returns_repo_commit_inside_repo(tmp_path):
    # Regression for the _DIR.parents[2] vs .parents[1] cwd bug: when running
    # inside this git repo, _git("rev-parse", "HEAD") must return a 40-char sha,
    # NOT empty. Skipped automatically if the checkout has no .git directory.
    if not (gate._REPO_ROOT / ".git").exists():
        import pytest
        pytest.skip("not a git checkout")
    sha = gate._git("rev-parse", "HEAD")
    assert len(sha) == 40 and all(c in "0123456789abcdef" for c in sha)
