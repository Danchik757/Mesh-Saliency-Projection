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
