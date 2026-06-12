"""
Tests for test/launch/run_full_metrics_optimized_sigma.py (Gate 2 reliability):

- dry-run rows are never counted as completed on resume.
- the resume job_key embeds the timing/fixation/sigma/release configuration.
- provenance verification rejects a report from a different contract.
- the final-CSV helper aggregates+dedups the full JSONL (ok preferred).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

_PATH = REPO_ROOT / "test" / "launch" / "run_full_metrics_optimized_sigma.py"
_spec = importlib.util.spec_from_file_location("run_full_metrics_optimized_sigma", _PATH)
_m = importlib.util.module_from_spec(_spec)
sys.modules["run_full_metrics_optimized_sigma"] = _m
_spec.loader.exec_module(_m)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_dry_run_rows_not_counted_completed(tmp_path):
    p = tmp_path / "metrics_rows.jsonl"
    real_key = _m._job_key("3dva", "cone", "A380")
    dry_key = _m._job_key("3dva", "cone", "bimba")
    _write_jsonl(p, [
        {"job_key": real_key, "status": "ok"},
        {"job_key": dry_key, "status": "ok", "error_type": "dry_run"},
    ])
    done = _m.load_completed_keys(p)
    assert real_key in done
    assert dry_key not in done


def test_job_key_embeds_config():
    key = _m._job_key("sal3d", "cone", "A380")
    assert _m.RELEASE_TAG in key
    assert _m.TIMING_CONTRACT in key
    assert _m.FIXATION_DATA_TAG in key
    assert "cone_sd" in key  # sigma signature for a cone job
    # cone vs screen_space produce different keys for the same model
    assert _m._job_key("sal3d", "cone", "A380") != _m._job_key("sal3d", "screen_space", "A380")


def test_provenance_mismatch_detected():
    good = {"participant_input": {
        "timing_contract": _m.TIMING_CONTRACT, "frame_offset": _m.FRAME_OFFSET,
        "fixation_data_tag": _m.FIXATION_DATA_TAG, "delay_frames": 0, "fps": 30.0}}
    assert _m._provenance_mismatches(good) == []

    bad = {"participant_input": {
        "timing_contract": "cropped_reset", "frame_offset": 54,
        "fixation_data_tag": "processed_fixations_offset_2000", "delay_frames": 6, "fps": 30.0}}
    problems = _m._provenance_mismatches(bad)
    assert any("timing_contract" in p for p in problems)
    assert any("frame_offset" in p for p in problems)
    assert any("fixation_data_tag" in p for p in problems)


def test_load_and_dedup_prefers_ok(tmp_path):
    p = tmp_path / "metrics_rows.jsonl"
    key = _m._job_key("3dva", "cone", "A380")
    _write_jsonl(p, [
        {"job_key": key, "status": "failed", "error_type": "timeout", "CC": ""},
        {"job_key": key, "status": "ok", "CC": 0.42},
    ])
    rows = _m._load_and_dedup_jsonl(p)
    assert len(rows) == 1
    assert rows[0]["status"] == "ok"
    assert rows[0]["CC"] == 0.42


def test_select_report_prefers_report_json(tmp_path):
    task = tmp_path / "task"
    task.mkdir()
    (task / "provenance.json").write_text("{}")
    (task / "A380_report.json").write_text("{}")
    chosen = _m._select_report(task)
    assert chosen is not None
    assert chosen.name == "A380_report.json"
