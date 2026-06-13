"""
Gate 2b guard tests for test/launch/run_sigma_sweep_rc3.py:

- dry-run rows are never counted as completed on resume.
- canonical --fixation-data-tag passed to the evaluator.
- env-driven release tag.
- deterministic *_report.json selection and strict provenance (missing fields).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

_PATH = REPO_ROOT / "test" / "launch" / "run_sigma_sweep_rc3.py"


def _load():
    spec = importlib.util.spec_from_file_location("run_sigma_sweep_rc3", _PATH)
    m = importlib.util.module_from_spec(spec)
    sys.modules["run_sigma_sweep_rc3"] = m
    spec.loader.exec_module(m)
    return m


_m = _load()


def test_dry_run_rows_not_counted(tmp_path):
    p = tmp_path / "sigma_sweep_rows.jsonl"
    p.write_text(json.dumps({"job_key": "x", "status": "ok", "error_type": "dry_run"}) + "\n")
    # Reviewer reproduction: this used to return {"x"}.
    assert _m.load_completed_keys(p) == set()


def test_real_ok_counted(tmp_path):
    p = tmp_path / "sigma_sweep_rows.jsonl"
    p.write_text(json.dumps({"job_key": "real", "status": "ok"}) + "\n")
    assert _m.load_completed_keys(p) == {"real"}


def test_build_command_passes_fixation_data_tag():
    job = _m.SigmaSweepJob(dataset="sal3d", model="A380", method="cone",
                           sigma_deg=1.0, radius_sigma_mult=3.0)

    class A:
        fixation_root = None
        batch_output_dir = "/tmp/sw"
    cmd = _m.build_command(job, A())
    assert "--fixation-data-tag" in cmd
    assert cmd[cmd.index("--fixation-data-tag") + 1] == _m.FIXATION_DATA_TAG
    assert "--model" in cmd and "--models" not in cmd


def test_release_tag_env_driven(monkeypatch):
    monkeypatch.setenv("REPROJECT_RELEASE_TAG", "v2.0-data-rc4")
    m = _load()
    assert m.RELEASE_TAG == "v2.0-data-rc4"


def test_select_report_prefers_report_json(tmp_path):
    (tmp_path / "provenance.json").write_text("{}")
    (tmp_path / "A380_report.json").write_text("{}")
    assert _m._select_report(tmp_path).name == "A380_report.json"


def test_provenance_missing_fields_flagged():
    assert _m._provenance_mismatches({}) == ["participant_input missing or not an object"]
    partial = {"participant_input": {"timing_contract": _m.TIMING_CONTRACT}}
    problems = _m._provenance_mismatches(partial)
    assert any("missing frame_offset" in p for p in problems)


# ── item 1: config signature in key AND per-task paths ──────────────────────────

class _Args:
    batch_output_dir = "/tmp/sweep"
    fixation_root = None


def _job():
    return _m.SigmaSweepJob(dataset="sal3d", model="alien", method="cone",
                            sigma_deg=1.0, radius_sigma_mult=3.0)


def test_key_and_path_change_with_release_tag(monkeypatch):
    job = _job()
    k1, p1 = job.key, str(_m._task_output_dir(job, _Args()))
    monkeypatch.setattr(_m, "RELEASE_TAG", "v2.0-data-rc5")
    assert job.key != k1
    assert str(_m._task_output_dir(job, _Args())) != p1


def test_key_and_path_change_with_timing_contract(monkeypatch):
    job = _job()
    k1, p1 = job.key, str(_m._task_output_dir(job, _Args()))
    monkeypatch.setattr(_m, "TIMING_CONTRACT", "cropped_reset")
    assert job.key != k1
    assert str(_m._task_output_dir(job, _Args())) != p1


def test_key_changes_with_fixation_tag_and_delay(monkeypatch):
    job = _job()
    k1 = job.key
    monkeypatch.setattr(_m, "FIXATION_DATA_TAG", "something_else")
    assert job.key != k1
    monkeypatch.undo()
    monkeypatch.setattr(_m, "DELAY_SECONDS", 0.2)
    assert job.key != k1


def test_key_includes_full_contract():
    k = _job().key
    for token in (_m.RELEASE_TAG, _m.TIMING_CONTRACT, _m.FIXATION_DATA_TAG, "fo0", "dl0.0"):
        assert token in k


# ── item 2: delay/gaze/placement provenance ─────────────────────────────────────

def test_delay_frames_mismatch_flagged():
    # Reviewer reproduction: delay_frames=6 while delay_seconds=0.0 (expected 0).
    prov = {"participant_input": {
        "timing_contract": "one_turn_from_start", "frame_offset": 0,
        "fixation_data_tag": _m.FIXATION_DATA_TAG, "fps": 30,
        "delay_frames": 6, "gaze_start_frame": 0, "placement_start_frame": 0}}
    assert any("delay_frames=6" in p for p in _m._provenance_mismatches(prov))


def test_gaze_and_placement_start_validated():
    prov = {"participant_input": {
        "timing_contract": "one_turn_from_start", "frame_offset": 0,
        "fixation_data_tag": _m.FIXATION_DATA_TAG, "fps": 30,
        "delay_frames": 0, "gaze_start_frame": 7, "placement_start_frame": 3}}
    problems = _m._provenance_mismatches(prov)
    assert any("gaze_start_frame" in p for p in problems)
    assert any("placement_start_frame" in p for p in problems)


def test_correct_sweep_provenance_clean():
    prov = {"participant_input": {
        "timing_contract": "one_turn_from_start", "frame_offset": 0,
        "fixation_data_tag": _m.FIXATION_DATA_TAG, "fps": 30,
        "delay_frames": 0, "gaze_start_frame": 0, "placement_start_frame": 0}}
    assert _m._provenance_mismatches(prov) == []
