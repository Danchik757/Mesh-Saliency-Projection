"""Tests for the evaluator-backed local per-point sweep runner.

Covers: real evaluator command construction (no execution), per-point provenance
propagation, NON-STATIC metrics across points via a mock invoke, failed-model
accounting, and distinct run directories per point. The real subprocess invoke is
not executed here (it needs the external dataset assets); its command construction
is asserted directly and a mock is injected for the orchestration tests.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import os
import subprocess
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


ev = _load("run_evaluator_sweep")


def _agg_rows(tmp_path, dataset, method, stage):
    p = tmp_path / "ablation" / stage / dataset / method / "aggregate" / "ablation_runs.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()]


# ── real command construction (no execution) ───────────────────────────────────

def test_build_evaluator_command_cone():
    point = ev.make_sigma_grid("meshmamba_non_texture", "cone", sigma_param="sigma_deg",
                               sigma_values=[0.8], radius_sigma_mult=3.0)[0]
    cmd = ev.build_evaluator_command(
        point, "Pear_L3", output_dir=Path("/tmp/x"),
        resolved_env={
            "MESHMAMBA_NON_TEXTURE_ROOT": "/srv/mm",
            "MESHMAMBA_JSON_ROOT": "/srv/mm_json",
        },
    )
    assert cmd[1].endswith("reprojection_methods/cone_projection_on_mesh/eval_meshmamba_cone.py")
    assert cmd[2:4] == ["--model", "Pear_L3"]
    assert "--sigma-deg" in cmd and cmd[cmd.index("--sigma-deg") + 1] == "0.8"
    assert "--radius-sigma-mult" in cmd and cmd[cmd.index("--radius-sigma-mult") + 1] == "3.0"
    assert cmd[cmd.index("--frame-offset") + 1] == "0"
    assert cmd[cmd.index("--timing-contract") + 1] == "one_turn_from_start"
    assert cmd[cmd.index("--dataset-root") + 1] == "/srv/mm"
    assert cmd[cmd.index("--json-root") + 1] == "/srv/mm_json"
    assert cmd[cmd.index("--texture-type") + 1] == "non_texture"
    assert "--output-dir" in cmd and "--tag" in cmd
    assert "--sigma-px" not in cmd


def test_build_evaluator_command_screen_space():
    point = ev.make_sigma_grid("sal3d", "screen_space", sigma_param="sigma_px",
                               sigma_values=[26.3])[0]
    cmd = ev.build_evaluator_command(
        point, "dog", output_dir=Path("/tmp/y"),
        resolved_env={
            "SAL3D_DATASET_ROOT": "/srv/sal3d",
            "SAL3D_JSON_ROOT": "/srv/sal3d_json",
            "SAL3D_FIXED_GT_DIR": "/srv/sal3d_gt",
            "SAL3D_MANIFEST": "/srv/sal3d_manifest.csv",
        },
    )
    assert cmd[1].endswith("reprojection_methods/screen_space_gaussian/eval_sal3d_screen_space.py")
    assert cmd[cmd.index("--dataset-root") + 1] == "/srv/sal3d"
    assert cmd[cmd.index("--json-root") + 1] == "/srv/sal3d_json"
    assert cmd[cmd.index("--fixed-gt-dir") + 1] == "/srv/sal3d_gt"
    assert cmd[cmd.index("--sal3d-manifest") + 1] == "/srv/sal3d_manifest.csv"
    assert "--sigma-px" in cmd and cmd[cmd.index("--sigma-px") + 1] == "26.3"
    assert "--sigma-deg" not in cmd and "--texture-type" not in cmd


def test_build_evaluator_command_3dva_explicit_dataset_root():
    point = ev.make_sigma_grid("3dva", "screen_space", sigma_param="sigma_px",
                               sigma_values=[49.0])[0]
    cmd = ev.build_evaluator_command(
        point, "A380", output_dir=Path("/tmp/z"),
        resolved_env={
            "VISUAL_ATTENTION_3D_SHAPES_ROOT": "/srv/3dva",
            "THREE_DVA_JSON_ROOT": "/srv/3dva_json",
            "THREE_DVA_COMBINED_GT_DIR": "/srv/3dva_gt",
        },
    )
    assert cmd[cmd.index("--dataset-root") + 1] == "/srv/3dva"
    assert cmd[cmd.index("--json-root") + 1] == "/srv/3dva_json"
    assert cmd[cmd.index("--combined-gt-dir") + 1] == "/srv/3dva_gt"
    assert "--texture-type" not in cmd


def test_build_evaluator_command_meshmamba_rgb_uses_rgb_specific_roots():
    point = ev.make_sigma_grid("meshmamba_rgb_texture", "screen_space", sigma_param="sigma_screen",
                               sigma_values=[0.05])[0]
    cmd = ev.build_evaluator_command(
        point, "Kangaroo_v1_L3", output_dir=Path("/tmp/rgb"),
        resolved_env={
            "MESHMAMBA_RGB_TEXTURE_ROOT": "/srv/mm_rgb",
            "MESHMAMBA_RGB_TEXTURE_JSON_ROOT": "/srv/mm_rgb_json",
        },
    )
    assert cmd[cmd.index("--dataset-root") + 1] == "/srv/mm_rgb"
    assert cmd[cmd.index("--json-root") + 1] == "/srv/mm_rgb_json"
    assert cmd[cmd.index("--texture-type") + 1] == "rgb_texture"


# ── orchestration via mock invoke ──────────────────────────────────────────────

def test_mock_sweep_produces_non_static_metrics(tmp_path):
    points = ev.make_sigma_grid("meshmamba_non_texture", "cone", sigma_param="sigma_deg",
                                sigma_values=[0.8, 2.0], radius_sigma_mult=3.0)
    ev.run_evaluator_sweep(points, ["Pear_L3", "Starfruit_L3"], tmp_path,
                           invoke=ev.make_mock_invoke(), stage="evsweep")

    rows = _agg_rows(tmp_path, "meshmamba_non_texture", "cone", "evsweep")
    assert len(rows) == 2
    by_sigma = {r["sigma_deg"]: r for r in rows}
    assert set(by_sigma) == {0.8, 2.0}
    assert by_sigma[0.8]["CC"] != by_sigma[2.0]["CC"]      # NON-static across points
    assert all(r["n_ok"] == 2 for r in rows)


def test_mock_sweep_emits_both_klds_end_to_end(tmp_path):
    # The evaluator-backed runner (real producer path) must propagate KLD,
    # KLD_evaluator and KLD_trusted — computed from the mock's pred/GT arrays.
    points = ev.make_sigma_grid("meshmamba_non_texture", "cone", sigma_param="sigma_deg",
                                sigma_values=[0.8, 2.0], radius_sigma_mult=3.0)
    run_dirs = ev.run_evaluator_sweep(points, ["Pear_L3", "Starfruit_L3"], tmp_path,
                                      invoke=ev.make_mock_invoke(), stage="kldsweep")
    rows = _agg_rows(tmp_path, "meshmamba_non_texture", "cone", "kldsweep")
    assert rows
    for r in rows:
        assert r["KLD"] != "" and r["KLD_evaluator"] != "" and r["KLD_trusted"] != ""
        assert r["KLD"] == pytest.approx(r["KLD_evaluator"])      # historical == evaluator
        assert float(r["KLD_trusted"]) != pytest.approx(float(r["KLD_evaluator"]))  # distinct

    sheader = next(csv.reader((run_dirs[0] / "metrics_summary.csv").open()))
    assert "KLD" in sheader and "KLD_evaluator" not in sheader and "KLD_trusted" not in sheader

    long0 = json.loads((run_dirs[0] / "metrics_long.jsonl").read_text().splitlines()[0])
    assert long0["KLD_evaluator"] is not None and long0["KLD_trusted"] is not None


def test_per_point_provenance_propagation(tmp_path):
    points = ev.make_sigma_grid("meshmamba_non_texture", "cone", sigma_param="sigma_deg",
                                sigma_values=[1.0], radius_sigma_mult=3.0)
    ev.run_evaluator_sweep(points, ["Pear_L3"], tmp_path, invoke=ev.make_mock_invoke(),
                           stage="evsweep")
    row = _agg_rows(tmp_path, "meshmamba_non_texture", "cone", "evsweep")[0]
    assert row["sigma_deg"] == 1.0
    assert row["radius_sigma_mult"] == 3.0
    assert row["timing_contract"] == "one_turn_from_start"
    assert row["dataset"] == "meshmamba_non_texture" and row["method"] == "cone"


def test_failed_model_is_counted(tmp_path):
    def invoke(point, model):
        if model == "Broken":
            return {"model": model, "status": "failed", "error_type": "evaluator_nonzero"}
        return ev.make_mock_invoke()(point, model)

    points = ev.make_sigma_grid("sal3d", "cone", sigma_param="sigma_deg",
                                sigma_values=[1.0], radius_sigma_mult=3.0)
    ev.run_evaluator_sweep(points, ["dog", "Broken"], tmp_path, invoke=invoke, stage="evsweep")
    row = _agg_rows(tmp_path, "sal3d", "cone", "evsweep")[0]
    assert row["n_ok"] == 1 and row["n_failed"] == 1 and row["n_total_models"] == 2
    assert row["status"] == "partial"


def test_distinct_run_dirs_per_point(tmp_path):
    points = ev.make_sigma_grid("sal3d", "cone", sigma_param="sigma_deg",
                                sigma_values=[0.8, 1.0, 2.0], radius_sigma_mult=3.0)
    run_dirs = ev.run_evaluator_sweep(points, ["dog"], tmp_path, invoke=ev.make_mock_invoke(),
                                      stage="evsweep")
    assert len(run_dirs) == 3 and len({d.name for d in run_dirs}) == 3


_COMPACT = ("CC", "SIM", "KLD", "MSE", "MAE", "Spearman", "Cosine",
            "AUC_at_10pct", "AUC_at_5pct", "AUC_at_1pct",
            "NSS_at_10pct", "NSS_at_5pct", "NSS_at_1pct", "hit_rate")


def _run_mock_cli(out_root: Path, hashseed: str) -> dict:
    """Run the --mock CLI in a separate process with a given PYTHONHASHSEED and
    return {sigma_deg: [compact metric vector]} from the aggregate JSONL."""
    env = dict(os.environ, PYTHONHASHSEED=hashseed)
    subprocess.run(
        [sys.executable, str(_DIR / "run_evaluator_sweep.py"),
         "--dataset", "meshmamba_non_texture", "--method", "cone",
         "--models", "Pear_L3,Starfruit_L3,BellPepper_v1_L3",
         "--sigma-param", "sigma_deg", "--sigma-values", "0.8,1.0,2.0",
         "--radius-sigma-mult", "3.0", "--stage", "det_check",
         "--results-root", str(out_root), "--mock"],
        cwd=_DIR.parents[1], check=True, capture_output=True, env=env)
    jsonl = (out_root / "ablation" / "det_check" / "meshmamba_non_texture" / "cone"
             / "aggregate" / "ablation_runs.jsonl")
    rows = [json.loads(l) for l in jsonl.read_text().splitlines()]
    return {r["sigma_deg"]: [r[m] for m in _COMPACT] for r in rows}


def test_subprocess_invoke_fails_fast_without_assets(monkeypatch, tmp_path):
    # With the dataset roots unset, the real invoke must raise PreflightError
    # BEFORE running any subprocess (no per_task dir created).
    for var in ("MESHMAMBA_JSON_ROOT", "MESHMAMBA_NON_TEXTURE_ROOT"):
        monkeypatch.delenv(var, raising=False)
    point = ev.make_sigma_grid("meshmamba_non_texture", "cone", sigma_param="sigma_deg",
                               sigma_values=[1.0], radius_sigma_mult=3.0)[0]
    with pytest.raises(ev.pf.PreflightError):
        ev.subprocess_evaluator_invoke(
            point, "Pear_L3", work_dir=tmp_path,
            fixation_root=str(tmp_path / "definitely_missing_fix_root"),
        )
    assert not (tmp_path / "per_task").exists()   # failed fast, no work started


def test_subprocess_invoke_passes_preflight_env_to_child(monkeypatch, tmp_path):
    point = ev.make_sigma_grid("meshmamba_non_texture", "cone", sigma_param="sigma_deg",
                               sigma_values=[1.0], radius_sigma_mult=3.0)[0]
    out_dir = (tmp_path / "per_task" / point["dataset"] / "Pear_L3" / "cone_sigma_deg1.0")
    out_dir.mkdir(parents=True)
    report_path = out_dir / "report.json"
    report_path.write_text(json.dumps({
        "metrics_vs_gt": {
            "cone_gaussian_on_mesh": {
                "CC": 0.5, "SIM": 0.6, "KLD": 1.2, "MSE": 0.1, "MAE": 0.2,
                "Spearman": 0.4, "Cosine": 0.7,
                "AUC_Judd_gt_top_10pct_proxy": 0.8,
                "AUC_Judd_gt_top_5pct_proxy": 0.81,
                "AUC_Judd_gt_top_1pct_proxy": 0.82,
                "NSS_gt_top_10pct_proxy": 1.0,
                "NSS_gt_top_5pct_proxy": 1.1,
                "NSS_gt_top_1pct_proxy": 1.2,
                "hit_rate": 0.9,
            }
        }
    }))

    captured = {}

    def fake_require(dataset, method, *, fixation_root=None, env=None):
        return {"dataset": dataset, "method": method, "ok": True, "items": []}

    dep_calls = []

    def fake_require_runtime_dependencies(method, *, python=None):
        dep_calls.append((method, python))
        return {"method": method, "python": python, "ok": True, "items": []}

    def fake_resolved_env(report):
        return {
            "MESHMAMBA_JSON_ROOT": "/tmp/json_root",
            "MESHMAMBA_NON_TEXTURE_ROOT": "/tmp/dataset_root",
            "FIXATION_ROOT": "/tmp/fix_root",
        }

    def fake_run(cmd, capture_output, text, timeout, env):
        captured["env"] = env
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(ev.pf, "require", fake_require)
    monkeypatch.setattr(ev.pf, "require_runtime_dependencies", fake_require_runtime_dependencies)
    monkeypatch.setattr(ev.pf, "resolved_env", fake_resolved_env)
    monkeypatch.setattr(ev.rawd, "_select_report", lambda _: report_path)
    monkeypatch.setattr(ev.subprocess, "run", fake_run)

    row = ev.subprocess_evaluator_invoke(
        point, "Pear_L3", work_dir=tmp_path, python="/opt/py/bin/python3",
    )
    assert row["status"] == "ok"
    assert dep_calls and dep_calls[0] == ("cone", "/opt/py/bin/python3")
    assert captured["env"]["MESHMAMBA_JSON_ROOT"] == "/tmp/json_root"
    assert captured["env"]["MESHMAMBA_NON_TEXTURE_ROOT"] == "/tmp/dataset_root"
    assert captured["env"]["FIXATION_ROOT"] == "/tmp/fix_root"


def test_subprocess_invoke_uses_explicit_env_without_preflight(monkeypatch, tmp_path):
    point = ev.make_sigma_grid("meshmamba_non_texture", "cone", sigma_param="sigma_deg",
                               sigma_values=[1.0], radius_sigma_mult=3.0)[0]
    out_dir = (tmp_path / "per_task" / point["dataset"] / "Pear_L3" / "cone_sigma_deg1.0")
    out_dir.mkdir(parents=True)
    report_path = out_dir / "report.json"
    report_path.write_text(json.dumps({
        "metrics_vs_gt": {
            "cone_gaussian_on_mesh": {
                "CC": 0.5, "SIM": 0.6, "KLD": 1.2, "MSE": 0.1, "MAE": 0.2,
                "Spearman": 0.4, "Cosine": 0.7,
                "AUC_Judd_gt_top_10pct_proxy": 0.8,
                "AUC_Judd_gt_top_5pct_proxy": 0.81,
                "AUC_Judd_gt_top_1pct_proxy": 0.82,
                "NSS_gt_top_10pct_proxy": 1.0,
                "NSS_gt_top_5pct_proxy": 1.1,
                "NSS_gt_top_1pct_proxy": 1.2,
                "hit_rate": 0.9,
            }
        }
    }))

    called = {"preflight": 0, "runtime": 0}
    captured = {}

    monkeypatch.setattr(ev.pf, "require", lambda *a, **k: called.__setitem__("preflight", called["preflight"] + 1))
    monkeypatch.setattr(ev.pf, "require_runtime_dependencies", lambda *a, **k: called.__setitem__("runtime", called["runtime"] + 1))
    monkeypatch.setattr(ev.rawd, "_select_report", lambda _: report_path)

    def fake_run(cmd, capture_output, text, timeout, env):
        captured["cmd"] = cmd
        captured["env"] = env
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(ev.subprocess, "run", fake_run)

    row = ev.subprocess_evaluator_invoke(
        point, "Pear_L3", work_dir=tmp_path,
        preflight=False,
        env={"MESHMAMBA_JSON_ROOT": "/tmp/json_root", "FIXATION_ROOT": "/tmp/fix_root"},
        python="/custom/python3",
    )
    assert row["status"] == "ok"
    assert called == {"preflight": 0, "runtime": 0}
    assert captured["cmd"][0] == "/custom/python3"
    assert captured["env"]["MESHMAMBA_JSON_ROOT"] == "/tmp/json_root"
    assert captured["env"]["FIXATION_ROOT"] == "/tmp/fix_root"


def test_subprocess_invoke_uses_explicit_task_tag_for_raw_dir(monkeypatch, tmp_path):
    point = ev.make_sigma_grid("sal3d", "cone", sigma_param="sigma_deg",
                               sigma_values=[1.0], radius_sigma_mult=3.0)[0]
    point["task_tag"] = "cone_delay_seconds0p2_sdeg=1p0_rsm=3p0_fo54"
    out_dir = tmp_path / "per_task" / "sal3d" / "dog" / point["task_tag"]
    out_dir.mkdir(parents=True)
    report_path = out_dir / "report.json"
    report_path.write_text(json.dumps({
        "metrics_vs_gt": {
            "cone_gaussian_on_mesh": {
                "CC": 0.5, "SIM": 0.6, "KLD": 1.2, "MSE": 0.1, "MAE": 0.2,
                "Spearman": 0.4, "Cosine": 0.7,
                "AUC_Judd_gt_top_10pct_proxy": 0.8,
                "AUC_Judd_gt_top_5pct_proxy": 0.81,
                "AUC_Judd_gt_top_1pct_proxy": 0.82,
                "NSS_gt_top_10pct_proxy": 1.0,
                "NSS_gt_top_5pct_proxy": 1.1,
                "NSS_gt_top_1pct_proxy": 1.2,
                "hit_rate": 0.9,
            }
        }
    }))

    monkeypatch.setattr(ev.rawd, "_select_report", lambda _: report_path)
    monkeypatch.setattr(
        ev.subprocess,
        "run",
        lambda cmd, capture_output, text, timeout, env: subprocess.CompletedProcess(cmd, 0, stdout="", stderr=""),
    )

    row = ev.subprocess_evaluator_invoke(point, "dog", work_dir=tmp_path, preflight=False)
    assert row["status"] == "ok"


def test_subprocess_invoke_fails_fast_on_missing_runtime_dependency(monkeypatch, tmp_path):
    point = ev.make_sigma_grid("meshmamba_non_texture", "cone", sigma_param="sigma_deg",
                               sigma_values=[1.0], radius_sigma_mult=3.0)[0]

    monkeypatch.setattr(ev.pf, "require", lambda *a, **k: {"dataset": "x", "method": "cone", "ok": True, "items": []})
    monkeypatch.setattr(ev.pf, "resolved_env", lambda report: {})
    monkeypatch.setattr(
        ev.pf,
        "require_runtime_dependencies",
        lambda method, *, python=None: (_ for _ in ()).throw(ev.pf.PreflightError("missing rtree")),
    )

    with pytest.raises(ev.pf.PreflightError):
        ev.subprocess_evaluator_invoke(point, "Pear_L3", work_dir=tmp_path)
    assert not (tmp_path / "per_task").exists()


def test_mock_sweep_is_cross_process_deterministic(tmp_path):
    # Two separate interpreter runs with DIFFERENT hash seeds must produce identical
    # aggregate metrics (regression for the salted hash() perturbation bug).
    first = _run_mock_cli(tmp_path / "run1", "0")
    second = _run_mock_cli(tmp_path / "run2", "12345")
    assert first == second
    assert sorted(first) == [0.8, 1.0, 2.0]
