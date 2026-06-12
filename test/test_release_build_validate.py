"""
Tests for the rc4 release builder and the strengthened validator (Gate 2):

builder (scripts/build_release_candidate.py)
  - manifest metadata is schema_version 2, offset0 / one_turn_from_start
  - based_on never mentions offset_2000 / cropped-reset
  - --dry-run exits 0 without touching source data

validator (scripts/validate_release_candidate.py)
  - exact frame counts keyed on dataset prefix (510 / 720 / 41)
  - based_on stale-data sanity check
  - Smooth Gaze + fixed-face GT inventory and the documented mismatch sets
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_builder = _load("build_release_candidate", REPO_ROOT / "scripts" / "build_release_candidate.py")
_validator = _load("validate_release_candidate", REPO_ROOT / "scripts" / "validate_release_candidate.py")


# ── builder manifest metadata ───────────────────────────────────────────────────

def test_manifest_metadata_is_schema2_offset0():
    m = _builder.build_manifest_metadata("v2.0-data-rc4", "deadbeef")
    assert m["schema_version"] == 2
    assert m["tag"] == "v2.0-data-rc4"
    assert m["timing_contract"]["name"] == "one_turn_from_start"
    assert m["timing_contract"]["crop_start_seconds"] == 0.0
    assert m["timing_contract"]["crop_end_seconds"] == 0.0
    pdc = m["participant_data_contract"]
    assert pdc["processed_json_archive"] == "participant_fixations_offset0_full_cleaned.zip"
    assert pdc["fixation_format"] == "one_turn_from_start_offset_0"
    assert pdc["automatic_fallback_allowed"] is False
    assert pdc["expected_file_count"] == 298


def test_manifest_based_on_has_no_legacy_terms():
    based_on = _builder.build_manifest_metadata("v2.0-data-rc4", "x")["based_on"].lower()
    for stale in ("offset_2000", "offset-2000", "cropped-reset", "cropped_reset"):
        assert stale not in based_on


def test_builder_dry_run_exits_zero():
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "build_release_candidate.py"), "--dry-run"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "schema_version=2" in proc.stdout
    assert "participant_fixations_offset0_full_cleaned.zip" in proc.stdout


# ── validator: per-prefix frame lengths ─────────────────────────────────────────

def test_expected_frames_by_prefix():
    assert _validator._expected_frames_for("3DVA_A380") == 510
    assert _validator._expected_frames_for("MeshMamba_Cat_v1_L3") == 510
    assert _validator._expected_frames_for("SAL3D_alien") == 720
    assert _validator._expected_frames_for("3DVA_jessi") == 41
    assert _validator._expected_frames_for("Mystery_model") is None


def _make_fixation_zip(path: Path, entries: dict[str, int]) -> None:
    root = "participant_fixations_offset0_full_cleaned"
    with zipfile.ZipFile(path, "w") as z:
        for model_id, n in entries.items():
            z.writestr(f"{root}/{model_id}/fixations.json", json.dumps([[[0.0, 0.0]]] * n))


def test_fixation_lengths_ok(tmp_path):
    p = tmp_path / "fix.zip"
    _make_fixation_zip(p, {"3DVA_A380": 510, "SAL3D_alien": 720, "3DVA_jessi": 41})
    with zipfile.ZipFile(p) as z:
        members = {m for m in z.namelist() if not m.endswith("/")}
    errors: list[str] = []
    _validator._check_fixation_frame_counts(p, members, errors)
    assert errors == []


def test_sal3d_file_with_3dva_prefix_length_rejected(tmp_path):
    p = tmp_path / "fix.zip"
    # A 720-frame file under a 3DVA_ prefix is wrong even though 720 is valid elsewhere.
    _make_fixation_zip(p, {"3DVA_A380": 720, "SAL3D_alien": 720, "3DVA_jessi": 41})
    with zipfile.ZipFile(p) as z:
        members = {m for m in z.namelist() if not m.endswith("/")}
    errors: list[str] = []
    _validator._check_fixation_frame_counts(p, members, errors)
    assert any("frame counts not matching dataset prefix" in e for e in errors)


# ── validator: based_on sanity ──────────────────────────────────────────────────

def test_based_on_stale_flagged():
    errors: list[str] = []
    _validator._check_based_on(
        {"based_on": "rc1 with cropped-reset offset-2000 data"}, errors)
    assert errors and "based_on" in errors[0]


def test_based_on_clean_ok():
    errors: list[str] = []
    _validator._check_based_on(
        {"based_on": "rc1 assets with offset0 one_turn_from_start fixations"}, errors)
    assert errors == []


# ── validator: SAL3D inventories ────────────────────────────────────────────────

def _common_models() -> list[str]:
    return [f"model{i:02d}" for i in range(51)]


def _make_smooth_zip(path: Path, models: list[str]) -> None:
    root = "datasets/SAL3D/Smooth_Gaze"
    with zipfile.ZipFile(path, "w") as z:
        for mdl in models:
            z.writestr(f"{root}/{mdl}_neighbors.txt", "0 neighbors\n")


def _make_fixed_zip(path: Path, models: list[str]) -> None:
    root = "datasets/SAL3D_fixed/sal3d_benchmark_pkg"
    with zipfile.ZipFile(path, "w") as z:
        for mdl in models:
            z.writestr(f"{root}/Meshes/{mdl}.obj", "v 0 0 0\n")
            z.writestr(f"{root}/{mdl}_faces.txt", "0\n")
        z.writestr(f"{root}/SHA256SUMS", "x\n")


def test_inventory_clean_passes(tmp_path):
    common = _common_models()
    smooth = common + ["AudiRS5", "bimba"]                 # 53
    fixed = common + ["MaxPlanck", "dog", "flowerpot", "prot"]  # 55
    _make_smooth_zip(tmp_path / "sal3d_smooth_gaze.zip", smooth)
    _make_fixed_zip(tmp_path / "sal3d_fixed_face_gt.zip", fixed)
    archives = {"sal3d_smooth_gaze.zip": {}, "sal3d_fixed_face_gt.zip": {}}
    errors: list[str] = []
    _validator._check_sal3d_inventories(tmp_path, archives, errors)
    assert errors == [], errors


def test_inventory_wrong_count_flagged(tmp_path):
    _make_smooth_zip(tmp_path / "sal3d_smooth_gaze.zip", ["only_one"])
    archives = {"sal3d_smooth_gaze.zip": {}}
    errors: list[str] = []
    _validator._check_sal3d_inventories(tmp_path, archives, errors)
    assert any("Smooth Gaze inventory" in e for e in errors)
