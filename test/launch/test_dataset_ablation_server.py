"""Tests for the dataset-level ablation server contract + monitor/resume layer."""
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


srv = _load("dataset_ablation_server")
core = _load("dataset_ablation_core")
ssl = _load("screen_space_dataset_ablation")
ev = _load("run_evaluator_sweep")


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


# ── manifest emission ────────────────────────────────────────────────────────

def test_emit_manifest_has_low_priority_and_real_launcher():
    m = srv.build_server_manifest(
        _request(), host="vg-iai", results_root="/srv/results",
        request_path="/srv/req.json")
    assert m["schema_version"] == srv.SCHEMA_VERSION
    assert m["host"] == "vg-iai"
    # low priority is mandatory and baked into the command
    assert m["command"][:7] == ["nice", "-n", "19", "ionice", "-c", "2", "-n"]
    assert m["command"][7] == "7"
    assert "test/launch/screen_space_dataset_ablation.py" in m["command"]
    # NOT a mock run
    assert "--mock" not in m["command"]
    assert "--request" in m["command"] and "--results-root" in m["command"]
    assert m["repo"]["commit"] == "a" * 40


def test_emit_rejects_unapproved_host():
    with pytest.raises(srv.ServerError, match="not approved"):
        srv.build_server_manifest(_request(), host="laptop",
                                  results_root="/r", request_path="/req.json")


def test_emit_rejects_invalid_request():
    bad = _request()
    bad["repo_commit"] = "short"
    with pytest.raises(core.BranchError, match="repo_commit"):
        srv.build_server_manifest(bad, host="vg-iai",
                                  results_root="/r", request_path="/req.json")


def test_emit_expected_run_ids_match_real_aggregate(tmp_path):
    # the run_ids the manifest predicts must equal what a real (mock) run records.
    req = _request()
    spec = ssl.build_spec()
    expected = srv.expected_candidate_run_ids(req, spec)
    assert set(expected) == {"s0.5", "s0.7", "s1", "s1.3", "s1.5"}
    ssl.run(req, results_root=tmp_path, invoke=ev.make_mock_invoke())
    branch_dir = core.branch_dir_for(tmp_path, req, spec)
    recorded = {json.loads(l)["run_id"]
                for l in (branch_dir / "aggregate" / "ablation_runs.jsonl").read_text().splitlines() if l.strip()}
    # every predicted static run_id was actually recorded
    assert set(expected.values()) <= recorded


def test_emit_signature_in_command_path(tmp_path):
    m = srv.build_server_manifest(_request(), host="vg-gml02",
                                  results_root="/srv/results", request_path="/srv/req.json")
    assert m["comparability_signature"] in m["branch_dir"]
    assert m["host"] == "vg-gml02"


# ── status / monitor / resume ────────────────────────────────────────────────

def test_status_pending_before_any_run(tmp_path):
    req = _request()
    status = srv.server_run_status(str(tmp_path), req)
    assert status["state"] == "pending"
    assert status["n_static_done"] == 0
    assert status["n_static_pending"] == status["n_static_candidates"] == 5


def test_status_promoted_after_run(tmp_path):
    req = _request()
    ssl.run(req, results_root=tmp_path, invoke=ev.make_mock_invoke())
    status = srv.server_run_status(str(tmp_path), req)
    assert status["state"] == "promoted"
    assert status["promoted"] is True
    assert status["n_static_pending"] == 0
    assert status["n_static_done"] == 5


def test_status_held_after_low_coverage_run(tmp_path):
    models = [f"m{i}" for i in range(1, 11)]
    grid = ssl.build_spec().coarse_grid
    # drop 4 distinct models so the common set is 6/10 = 0.6 < 0.70 -> held
    def invoke(point, model):
        v = round(float(point["value"]), 6)
        drop = {grid[0]: "m1", grid[1]: "m2", grid[2]: "m3", grid[3]: "m4"}.get(v)
        if model == drop:
            return {"model": model, "status": "failed", "error_type": "synthetic"}
        base = ev.make_mock_invoke()(point, model)
        return base
    ssl.run(_request(models=models), results_root=tmp_path, invoke=invoke)
    status = srv.server_run_status(str(tmp_path), _request(models=models))
    assert status["state"] == "held"
    assert status["held"] is True


def test_status_separates_incompatible_signatures(tmp_path):
    inv = ev.make_mock_invoke()
    ssl.run(_request(release_tag="rc4"), results_root=tmp_path, invoke=inv)
    # a different release_tag is a different branch -> still pending under its own sig
    st_b = srv.server_run_status(str(tmp_path), _request(release_tag="rc5"))
    assert st_b["state"] == "pending"
    st_a = srv.server_run_status(str(tmp_path), _request(release_tag="rc4"))
    assert st_a["state"] == "promoted"
    assert st_a["comparability_signature"] != st_b["comparability_signature"]


def test_write_server_manifest_roundtrip(tmp_path):
    m = srv.build_server_manifest(_request(), host="vg-iai",
                                  results_root="/r", request_path="/req.json")
    out = srv.write_server_manifest(m, tmp_path / "sub" / "manifest.json")
    assert out.exists()
    assert json.loads(out.read_text())["comparability_signature"] == m["comparability_signature"]
