"""Tests for the evaluator asset preflight / discovery layer."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
import subprocess

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


pf = _load("evaluator_preflight")


def test_asset_spec_covers_all_datasets():
    assert set(pf.ASSET_SPEC) == {"3dva", "meshmamba_non_texture",
                                  "meshmamba_rgb_texture", "sal3d"}
    names = {r["name"]: r for r in pf.ASSET_SPEC["meshmamba_non_texture"]}
    assert names["json_root"]["envs"] == ["MESHMAMBA_JSON_ROOT"]
    assert names["dataset_root"]["envs"] == ["MESHMAMBA_NON_TEXTURE_ROOT"]
    # sal3d carries the full asset set
    sal = {r["name"] for r in pf.ASSET_SPEC["sal3d"]}
    assert {"json_root", "dataset_root", "fixed_gt_dir", "sal3d_manifest"} <= sal


def test_preflight_reports_missing_roots(tmp_path, monkeypatch):
    # Empty env: dataset roots unset/missing; fixation resolves to its tracked default.
    monkeypatch.setattr(pf, "_REPO_ROOT", tmp_path / "repo")
    monkeypatch.setattr(pf, "_WORKSPACE_ROOT", tmp_path / "workspace")
    report = pf.preflight("meshmamba_non_texture", "cone", env={},
                          fixation_root=str(_DIR / "definitely_missing_fix_root"))
    assert report["ok"] is False
    missing = {i["name"] for i in report["missing"]}
    assert missing == {"fixation_root", "json_root", "dataset_root"}
    fixation = next(i for i in report["items"] if i["name"] == "fixation_root")
    assert fixation["present"] is False and fixation["source"] == "argument"


def test_preflight_ok_when_all_present(tmp_path):
    jdir = tmp_path / "json"; fdir = tmp_path / "fix"
    mdir = tmp_path / "mesh"
    jdir.mkdir()
    fdir.mkdir()
    (jdir / "MeshMamba_non_texture_Pear_L3.json").write_text("{}")
    (mdir / "MeshFile/non_texture").mkdir(parents=True)
    (mdir / "SaliencyMap/non_texture").mkdir(parents=True)
    env = {"MESHMAMBA_JSON_ROOT": str(jdir), "MESHMAMBA_NON_TEXTURE_ROOT": str(mdir)}
    report = pf.preflight("meshmamba_non_texture", "cone", fixation_root=str(fdir), env=env)
    assert report["ok"] is True
    assert all(i["present"] for i in report["items"])
    jr = next(i for i in report["items"] if i["name"] == "json_root")
    assert jr["source"] == "env" and jr["source_env"] == "MESHMAMBA_JSON_ROOT"


def test_preflight_meshmamba_auto_discovers_local_roots(tmp_path, monkeypatch):
    repo = tmp_path / "repo"; ws = tmp_path / "workspace"
    (repo / "participant_data/processed_fixations_offset0_full_cleaned").mkdir(parents=True)
    (repo / "jsons/object_placement/mamba_non_jsons").mkdir(parents=True)
    (repo / "jsons/object_placement/mamba_non_jsons/MeshMamba_non_texture_Pear_L3.json").write_text("{}")
    (ws / "GAZE_DATA/datasets/MeshMamba/MeshMambaSaliency/MeshFile/non_texture").mkdir(parents=True)
    (ws / "GAZE_DATA/datasets/MeshMamba/MeshMambaSaliency/SaliencyMap/non_texture").mkdir(parents=True)
    monkeypatch.setattr(pf, "_REPO_ROOT", repo)
    monkeypatch.setattr(pf, "_WORKSPACE_ROOT", ws)

    report = pf.preflight("meshmamba_non_texture", "cone", env={})
    assert report["ok"] is True
    json_root = next(i for i in report["items"] if i["name"] == "json_root")
    data_root = next(i for i in report["items"] if i["name"] == "dataset_root")
    assert json_root["source"] == "auto"
    assert json_root["resolved_path"] == str(repo / "jsons/object_placement/mamba_non_jsons")
    assert data_root["source"] == "auto"
    assert data_root["resolved_path"] == str(ws / "GAZE_DATA/datasets/MeshMamba/MeshMambaSaliency")
    exports = pf.shell_exports(report)
    assert 'export MESHMAMBA_JSON_ROOT="' in exports
    assert 'export MESHMAMBA_NON_TEXTURE_ROOT="' in exports


def test_resolved_env_returns_canonical_mapping(tmp_path, monkeypatch):
    repo = tmp_path / "repo"; ws = tmp_path / "workspace"
    (repo / "participant_data/processed_fixations_offset0_full_cleaned").mkdir(parents=True)
    (repo / "jsons/object_placement/mamba_non_jsons").mkdir(parents=True)
    (repo / "jsons/object_placement/mamba_non_jsons/MeshMamba_non_texture_Pear_L3.json").write_text("{}")
    (ws / "GAZE_DATA/datasets/MeshMamba/MeshMambaSaliency/MeshFile/non_texture").mkdir(parents=True)
    (ws / "GAZE_DATA/datasets/MeshMamba/MeshMambaSaliency/SaliencyMap/non_texture").mkdir(parents=True)
    monkeypatch.setattr(pf, "_REPO_ROOT", repo)
    monkeypatch.setattr(pf, "_WORKSPACE_ROOT", ws)

    env_map = pf.resolved_env(pf.preflight("meshmamba_non_texture", "cone", env={}))
    assert env_map["FIXATION_ROOT"].endswith("processed_fixations_offset0_full_cleaned")
    assert env_map["MESHMAMBA_JSON_ROOT"] == str(repo / "jsons/object_placement/mamba_non_jsons")
    assert env_map["MESHMAMBA_NON_TEXTURE_ROOT"] == str(ws / "GAZE_DATA/datasets/MeshMamba/MeshMambaSaliency")


def test_explicit_env_precedence_over_auto_discovery(tmp_path, monkeypatch):
    repo = tmp_path / "repo"; ws = tmp_path / "workspace"
    bad = tmp_path / "bad_json_root"
    (repo / "participant_data/processed_fixations_offset0_full_cleaned").mkdir(parents=True)
    (repo / "jsons/object_placement/mamba_non_jsons").mkdir(parents=True)
    (repo / "jsons/object_placement/mamba_non_jsons/MeshMamba_non_texture_Pear_L3.json").write_text("{}")
    (ws / "GAZE_DATA/datasets/MeshMamba/MeshMambaSaliency/MeshFile/non_texture").mkdir(parents=True)
    (ws / "GAZE_DATA/datasets/MeshMamba/MeshMambaSaliency/SaliencyMap/non_texture").mkdir(parents=True)
    monkeypatch.setattr(pf, "_REPO_ROOT", repo)
    monkeypatch.setattr(pf, "_WORKSPACE_ROOT", ws)

    report = pf.preflight(
        "meshmamba_non_texture", "cone",
        env={"MESHMAMBA_JSON_ROOT": str(bad)},
    )
    json_root = next(i for i in report["items"] if i["name"] == "json_root")
    assert json_root["source"] == "env"
    assert json_root["resolved_path"] == str(bad)
    assert json_root["present"] is False
    assert report["ok"] is False


def test_require_raises_actionable_message(tmp_path, monkeypatch):
    monkeypatch.setattr(pf, "_REPO_ROOT", tmp_path / "repo")
    monkeypatch.setattr(pf, "_WORKSPACE_ROOT", tmp_path / "workspace")
    with pytest.raises(pf.PreflightError) as e:
        pf.require("meshmamba_non_texture", "cone", env={},
                   fixation_root=str(_DIR / "definitely_missing_fix_root"))
    msg = str(e.value)
    assert "MESHMAMBA_JSON_ROOT" in msg and "MESHMAMBA_NON_TEXTURE_ROOT" in msg
    assert "--fixation-root" in msg and "--json-root" in msg and "--dataset-root" in msg


def test_format_report_marks_not_ready_and_lists_envs():
    text = pf.format_report(pf.preflight("sal3d", "cone", env={}))
    assert "NOT READY" in text
    assert "SAL3D_DATASET_ROOT" in text and "SAL3D_MANIFEST" in text


def test_failure_report_lists_auto_candidates(tmp_path, monkeypatch):
    repo = tmp_path / "repo"; ws = tmp_path / "workspace"
    (repo / "participant_data/processed_fixations_offset0_full_cleaned").mkdir(parents=True)
    monkeypatch.setattr(pf, "_REPO_ROOT", repo)
    monkeypatch.setattr(pf, "_WORKSPACE_ROOT", ws)
    text = pf.format_report(pf.preflight("meshmamba_non_texture", "cone", env={}))
    assert "searched local candidates:" in text
    assert "GAZE_DATA/datasets/MeshMamba/MeshMambaSaliency" in text


def test_unknown_dataset_or_method_raises():
    with pytest.raises(pf.PreflightError):
        pf.preflight("nope", "cone", env={})
    with pytest.raises(pf.PreflightError):
        pf.preflight("sal3d", "nope", env={})


def test_runtime_dependency_report_and_require(monkeypatch):
    calls = []

    def fake_run(cmd, capture_output, text, timeout):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="ModuleNotFoundError: No module named 'rtree'")

    monkeypatch.setattr(pf.subprocess, "run", fake_run)
    report = pf.runtime_dependency_report("cone", python="pythonX")
    assert report["ok"] is False
    assert report["missing"][0]["module"] == "rtree"
    assert calls == [["pythonX", "-c", "import rtree"]]

    with pytest.raises(pf.PreflightError) as e:
        pf.require_runtime_dependencies("cone", python="pythonX")
    assert "missing ['rtree']" in str(e.value)
