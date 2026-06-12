"""
Tests for test/launch/merge_rc3_final.py (Gate 2):

- finite_float drops NaN/Inf (and non-numeric) so means are not poisoned.
- check_merge_compatibility flags conflicting run-wide config and per-group sigma.
- write_compact_csv excludes non-finite metric values from the mean.
- main() aborts on incompatible inputs unless --allow-incompatible.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

_PATH = REPO_ROOT / "test" / "launch" / "merge_rc3_final.py"
_spec = importlib.util.spec_from_file_location("merge_rc3_final", _PATH)
_m = importlib.util.module_from_spec(_spec)
sys.modules["merge_rc3_final"] = _m
_spec.loader.exec_module(_m)


def _ok_row(**over):
    row = {
        "job_key": "optrun:cfg:3dva:A380:cone",
        "dataset": "3dva", "model": "A380", "method": "cone",
        "status": "ok", "error_type": "",
        "release_tag": "v2.0-data-rc3", "timing_contract": "one_turn_from_start",
        "fixation_data_tag": "processed_fixations_offset0_full_cleaned",
        "frame_offset": 0, "delay_seconds": 0.0,
        "sigma_deg": 2.0, "radius_sigma_mult": 3.0, "sigma_px": "", "sigma_screen": "",
        "CC": 0.4,
    }
    row.update(over)
    return row


# ── finite_float ────────────────────────────────────────────────────────────────

def test_finite_float_drops_non_finite():
    assert _m.finite_float("0.5") == 0.5
    assert _m.finite_float(float("nan")) is None
    assert _m.finite_float(float("inf")) is None
    assert _m.finite_float("NaN") is None
    assert _m.finite_float("Infinity") is None
    assert _m.finite_float("") is None
    assert _m.finite_float(None) is None


# ── compatibility guard ─────────────────────────────────────────────────────────

def test_compatible_rows_have_no_problems():
    rows = [_ok_row(), _ok_row(job_key="optrun:cfg:3dva:bimba:cone", model="bimba")]
    assert _m.check_merge_compatibility(rows) == []


def test_conflicting_release_tag_flagged():
    rows = [_ok_row(), _ok_row(model="bimba", release_tag="v2.0-data-rc1")]
    problems = _m.check_merge_compatibility(rows)
    assert any("release_tag" in p for p in problems)


def test_conflicting_timing_contract_flagged():
    rows = [_ok_row(), _ok_row(model="bimba", timing_contract="cropped_reset")]
    assert any("timing_contract" in p for p in _m.check_merge_compatibility(rows))


def test_conflicting_sigma_within_group_flagged():
    rows = [_ok_row(), _ok_row(model="bimba", sigma_deg=1.0)]
    problems = _m.check_merge_compatibility(rows)
    assert any("sigma_deg" in p and "3dva/cone" in p for p in problems)


def test_failed_rows_ignored_by_guard():
    # A failed row carries blank config fields; it must not trigger a conflict.
    rows = [_ok_row(), {"job_key": "x", "dataset": "3dva", "method": "cone",
                        "status": "failed", "error_type": "timeout"}]
    assert _m.check_merge_compatibility(rows) == []


# ── NaN/Inf exclusion in the compact mean ───────────────────────────────────────

def test_compact_mean_excludes_non_finite(tmp_path):
    rows = [
        _ok_row(model="a", CC=0.4),
        _ok_row(model="b", CC=0.6),
        _ok_row(model="c", CC=float("nan")),
        _ok_row(model="d", CC=float("inf")),
    ]
    out = tmp_path / "compact.csv"
    dropped = _m.write_compact_csv(rows, out)
    reader = list(csv.DictReader(out.open()))
    cone = next(r for r in reader if r["dataset_track"] == "3dva" and r["method"] == "cone")
    assert cone["n_ok"] == "4"               # all four rows counted
    assert cone["CC"] == "0.5000"            # mean over the two finite values
    assert dropped.get("CC") == 2            # two non-finite dropped


# ── main() integration ──────────────────────────────────────────────────────────

def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_main_aborts_on_incompatible(tmp_path, monkeypatch):
    a = tmp_path / "a.jsonl"
    b = tmp_path / "b.jsonl"
    _write_jsonl(a, [_ok_row()])
    _write_jsonl(b, [_ok_row(model="bimba", job_key="optrun:cfg:3dva:bimba:cone",
                             release_tag="v2.0-data-rc1")])
    out = tmp_path / "merged"
    argv = ["merge", "--jsonl-files", str(a), str(b), "--output-dir", str(out)]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(_m.IncompatibleMergeError):
        _m.main()


def test_main_allows_incompatible_with_flag(tmp_path, monkeypatch):
    a = tmp_path / "a.jsonl"
    b = tmp_path / "b.jsonl"
    _write_jsonl(a, [_ok_row()])
    _write_jsonl(b, [_ok_row(model="bimba", job_key="optrun:cfg:3dva:bimba:cone",
                             release_tag="v2.0-data-rc1")])
    out = tmp_path / "merged"
    argv = ["merge", "--jsonl-files", str(a), str(b),
            "--output-dir", str(out), "--allow-incompatible"]
    monkeypatch.setattr(sys, "argv", argv)
    assert _m.main() == 0
    assert (out / "metrics_long.csv").is_file()
