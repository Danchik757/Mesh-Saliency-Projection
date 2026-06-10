"""
Unit tests for utils/participant_loader.py.

All required tests from Milestone A1 (MACOS_CLAUDE.md):
  - valid 17-second pairing
  - valid 24-second pairing
  - invalid/missing processed file
  - coordinate/frame-count failure
  - rotation-speed/full-turn validation
  - old-CSV compatibility mode isolation
  - out-of-range sample rejection/drop

Tests use synthetic fixture data — no dependency on the 517 MB participant
payload or external dataset paths.
"""

from __future__ import annotations

import csv
import json
import math
import tempfile
from pathlib import Path

import numpy as np
import pytest

import sys
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from utils.participant_loader import (
    CROP_END_SECONDS,
    CROP_START_SECONDS,
    GazeBatch,
    InvalidFixationError,
    LoadedTrack,
    MissingFixationError,
    TimingValidationError,
    load_csv_compat_track,
    load_processed_track,
    resolve_processed_fixation_path,
)


# ── fixture helpers ───────────────────────────────────────────────────────────

def _make_placement_json(
    fps: int = 30,
    duration_seconds: int = 17,
    rotation_speed_deg_per_sec: float = 24.0,
    width: int = 1920,
    height: int = 1080,
) -> dict:
    """Build a minimal but valid placement JSON dict.

    Uses inclusive sampling: the rotation array covers [0, duration_seconds]
    across total_frames entries, matching the real exported placement JSONs.
    Frame[0] = 0°; Frame[total_frames-1] = rotation_speed * duration_seconds.
    """
    total_frames = fps * duration_seconds
    frames = []
    for i in range(total_frames):
        # Inclusive: angle at last frame = rotation_speed * duration_seconds
        angle_deg = rotation_speed_deg_per_sec * duration_seconds * i / (total_frames - 1)
        frames.append({
            "frame": i + 1,
            "timestamp": i / fps,
            "rotation_z_degrees": angle_deg,
            "rotation_z_radians": math.radians(angle_deg),
        })
    return {
        "video_info": {
            "fps": fps,
            "duration_seconds": duration_seconds,
            "total_frames": total_frames,
            "resolution_width": width,
            "resolution_height": height,
            "aspect_ratio": width / height,
        },
        "animation": {
            "start_angle_radians": 0.0,
            "start_angle_degrees": 0.0,
            "rotation_speed_deg_per_sec": rotation_speed_deg_per_sec,
            "rotation_speed_rad_per_sec": math.radians(rotation_speed_deg_per_sec),
            "rotation_axis": "Z",
            "rotation_direction": "counter_clockwise",
        },
        "frames": frames,
        "camera_static": {
            "fov_degrees": 60.0,
        },
    }


def _make_processed_fixations(
    total_frames: int,
    width: int = 1920,
    height: int = 1080,
    points_per_frame: int = 5,
) -> list:
    """Build a list of frames, each with a few valid pixel points."""
    rng = np.random.default_rng(42)
    return [
        [[float(rng.integers(0, width)), float(rng.integers(0, height))]
         for _ in range(points_per_frame)]
        for _ in range(total_frames)
    ]


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data))


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _make_csv_rows(
    fps: int,
    placement_start: int,
    placement_end_exclusive: int,
    width: int = 1920,
    height: int = 1080,
    n_participants: int = 3,
    points_per_frame: int = 4,
    include_out_of_window: bool = False,
) -> list[dict]:
    """Build minimal CSV rows with synthetic gaze data."""
    rows = []
    rng = np.random.default_rng(7)
    for pid in range(1, n_participants + 1):
        ts, xs, ys = [], [], []
        for frame in range(placement_start, placement_end_exclusive):
            t = frame / fps
            for _ in range(points_per_frame):
                ts.append(t)
                xs.append(float(rng.uniform(0.1, 0.9)))
                ys.append(float(rng.uniform(0.1, 0.9)))
        if include_out_of_window:
            # Add samples before and after the approved window.
            for t_out in [0.0, 0.5, (placement_end_exclusive + 10) / fps]:
                ts.append(t_out)
                xs.append(0.5)
                ys.append(0.5)
        rows.append({
            "participation_id": f"p{pid:03d}",
            "video_id": 1,
            "data_gazes": str({"t": ts, "x": xs, "y": ys}),
        })
    return rows


# ── helper: expected timing for standard 17-s and 24-s tracks ─────────────────

def _expected_timing(fps: int, duration_seconds: int) -> dict:
    crop_start = round(CROP_START_SECONDS * fps)
    crop_end = round(CROP_END_SECONDS * fps)
    total = fps * duration_seconds
    return {
        "placement_start": crop_start,
        "placement_end_exclusive": total - crop_end,
        "usable_count": total - crop_end - crop_start,
    }


# ── A1.1: valid 17-second pairing ─────────────────────────────────────────────

def test_load_processed_17s_pairing():
    fps = 30
    duration = 17
    total = fps * duration  # 510
    timing = _expected_timing(fps, duration)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        pj = tmp / "3DVA_TestModel.json"
        fj = tmp / "fixations.json"
        _write_json(pj, _make_placement_json(fps=fps, duration_seconds=duration,
                                              rotation_speed_deg_per_sec=24.0))
        _write_json(fj, _make_processed_fixations(timing["usable_count"]))

        track = load_processed_track(fj, pj, dataset="3DVA", model="TestModel")

    assert isinstance(track, LoadedTrack)
    assert track.input_mode == "processed_json"
    assert track.fps == fps
    assert track.total_frames == total
    assert track.placement_start == timing["placement_start"]           # 54
    assert track.placement_end_exclusive == timing["placement_end_exclusive"]  # 504
    assert track.usable_count == timing["usable_count"]                 # 450
    assert len(track.gaze_batches) == timing["usable_count"]
    # Keys must be absolute placement frame indices
    assert min(track.gaze_batches) == timing["placement_start"]
    assert max(track.gaze_batches) == timing["placement_end_exclusive"] - 1
    # Each batch must have numpy arrays in [0, 1]
    for frame_idx, batch in track.gaze_batches.items():
        assert isinstance(batch, GazeBatch)
        assert batch.x_norm.dtype == np.float64
        assert batch.y_norm.dtype == np.float64
        assert batch.x_norm.shape == batch.y_norm.shape
        assert float(batch.x_norm.min()) >= 0.0
        assert float(batch.x_norm.max()) <= 1.0
        assert float(batch.y_norm.min()) >= 0.0
        assert float(batch.y_norm.max()) <= 1.0


# ── A1.2: valid 24-second SAL3D pairing ───────────────────────────────────────

def test_load_processed_24s_pairing():
    fps = 30
    duration = 24
    total = fps * duration  # 720
    timing = _expected_timing(fps, duration)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        pj = tmp / "Sal3D_horse.json"
        fj = tmp / "fixations.json"
        _write_json(pj, _make_placement_json(fps=fps, duration_seconds=duration,
                                              rotation_speed_deg_per_sec=360.0 / 22.0))
        _write_json(fj, _make_processed_fixations(timing["usable_count"]))

        track = load_processed_track(fj, pj, dataset="SAL3D", model="horse")

    assert track.total_frames == 720
    assert track.usable_count == timing["usable_count"]   # 660
    assert track.placement_start == timing["placement_start"]          # 54
    assert track.placement_end_exclusive == timing["placement_end_exclusive"]  # 714
    assert len(track.gaze_batches) == 660


# ── A1.3: missing processed file ──────────────────────────────────────────────

def test_missing_fixation_raises():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        pj = tmp / "3DVA_gorgoile.json"
        _write_json(pj, _make_placement_json())
        missing = tmp / "no_fixations.json"

        with pytest.raises(MissingFixationError) as exc_info:
            load_processed_track(missing, pj, dataset="3DVA", model="gorgoile",
                                  canonical_name="3DVA_gorgoile")

    assert "gorgoile" in str(exc_info.value)
    assert "fall back" in str(exc_info.value).lower()


def test_processed_fixation_path_case_insensitive_parent_fallback():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        exact = tmp / "3DVA_rockerArm" / "fixations.json"
        actual = tmp / "3DVA_rockerarm" / "fixations.json"
        actual.parent.mkdir()
        actual.write_text("[]", encoding="utf-8")

        assert resolve_processed_fixation_path(exact) == actual


# ── A1.4: wrong frame count (jessi-style) ─────────────────────────────────────

def test_invalid_frame_count_raises():
    fps, duration = 30, 17
    total = fps * duration  # 510

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        pj = tmp / "3DVA_jessi.json"
        fj = tmp / "fixations.json"
        _write_json(pj, _make_placement_json())
        # 41 frames instead of 510 — the real jessi situation
        _write_json(fj, _make_processed_fixations(41))

        with pytest.raises(InvalidFixationError) as exc_info:
            load_processed_track(fj, pj, dataset="3DVA", model="jessi",
                                  canonical_name="3DVA_jessi")

    msg = str(exc_info.value)
    assert "41" in msg
    assert "510" in msg or str(total) in msg
    assert "fall back" in msg.lower()


# ── A1.4b: coordinate validation ──────────────────────────────────────────────

def test_invalid_coordinate_raises():
    fps, duration = 30, 17
    total = fps * duration

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        pj = tmp / "placement.json"
        fj = tmp / "fixations.json"
        _write_json(pj, _make_placement_json())
        bad = _make_processed_fixations(total)
        # Inject a non-finite value
        bad[10][0] = [float("nan"), 500.0]
        _write_json(fj, bad)

        with pytest.raises(InvalidFixationError):
            load_processed_track(fj, pj, dataset="3DVA", model="bad")


# ── A1.4c: out-of-bounds points in processed JSON are a data-contract violation

def test_out_of_bounds_points_raises():
    """An out-of-bounds pixel point in a processed fixation file is a data-contract
    violation (validate_data_contract.py confirms no valid release file has any).
    The loader must raise InvalidFixationError rather than silently dropping."""
    fps, duration = 30, 17
    timing = _expected_timing(fps, duration)
    width, height = 1920, 1080

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        pj = tmp / "placement.json"
        fj = tmp / "fixations.json"
        _write_json(pj, _make_placement_json())
        data = _make_processed_fixations(timing["usable_count"])
        # Inject an out-of-bounds point in usable frame 0 (processed index 0)
        data[0] = [[width + 10, height + 10], [100.0, 100.0]]
        _write_json(fj, data)

        with pytest.raises(InvalidFixationError) as exc_info:
            load_processed_track(fj, pj, dataset="3DVA", model="test")

    assert "out-of-bounds" in str(exc_info.value).lower()


# ── A1.5: rotation-speed / full-turn validation ───────────────────────────────

def test_wrong_rotation_speed_raises():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        pj = tmp / "placement.json"
        fj = tmp / "fixations.json"
        # Speed declared as 24 but actually encodes a different speed
        bad = _make_placement_json(rotation_speed_deg_per_sec=24.0)
        # Corrupt the last frame rotation to make observed ≠ declared
        bad["frames"][-1]["rotation_z_degrees"] = 999.0
        bad["frames"][-1]["rotation_z_radians"] = math.radians(999.0)
        _write_json(pj, bad)
        _write_json(fj, _make_processed_fixations(30 * 17))

        with pytest.raises(TimingValidationError, match="rotation speed"):
            load_processed_track(fj, pj, dataset="3DVA", model="test")


def test_full_turn_not_satisfied_raises():
    fps = 30
    duration = 17
    # Rotation speed that does NOT cover one full turn in the usable window
    bad_speed = 10.0  # far too slow; full turn = 36 s but usable = 15 s
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        pj = tmp / "placement.json"
        fj = tmp / "fixations.json"
        _write_json(pj, _make_placement_json(
            fps=fps, duration_seconds=duration,
            rotation_speed_deg_per_sec=bad_speed))
        _write_json(fj, _make_processed_fixations(fps * duration))

        with pytest.raises(TimingValidationError, match="full turn"):
            load_processed_track(fj, pj, dataset="3DVA", model="test")


# ── A1.6: old-CSV compatibility mode isolation ────────────────────────────────

def test_csv_compat_mode_isolation():
    fps, duration = 30, 17
    total = fps * duration
    timing = _expected_timing(fps, duration)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        pj = tmp / "placement.json"
        cf = tmp / "TestModel.csv"
        _write_json(pj, _make_placement_json())
        rows = _make_csv_rows(
            fps,
            timing["placement_start"],
            timing["placement_end_exclusive"],
        )
        _write_csv(cf, rows, ["participation_id", "video_id", "data_gazes"])

        track = load_csv_compat_track(cf, pj, dataset="3DVA", model="TestModel")

    assert track.input_mode == "csv_compat"
    # Provenance must clearly flag it
    assert track.provenance["input_mode"] == "csv_compat"
    assert track.placement_start == timing["placement_start"]
    assert track.placement_end_exclusive == timing["placement_end_exclusive"]
    assert track.usable_count == timing["usable_count"]
    # Frames with gaze must be within the approved window
    for frame_idx in track.gaze_batches:
        assert timing["placement_start"] <= frame_idx < timing["placement_end_exclusive"]


def test_csv_mode_cannot_silently_stand_in_for_processed():
    # Isolation is by function name and the input_mode provenance tag.
    # The two loaders must produce different input_mode strings so any report
    # that comes from the CSV path is unambiguously marked.
    fps, duration = 30, 17
    total = fps * duration
    timing = _expected_timing(fps, duration)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        pj = tmp / "placement.json"
        fj = tmp / "fixations.json"
        cf = tmp / "model.csv"
        _write_json(pj, _make_placement_json())
        _write_json(fj, _make_processed_fixations(timing["usable_count"]))
        rows = _make_csv_rows(fps, timing["placement_start"], timing["placement_end_exclusive"])
        _write_csv(cf, rows, ["participation_id", "video_id", "data_gazes"])

        t_proc = load_processed_track(fj, pj, dataset="3DVA", model="test")
        t_csv = load_csv_compat_track(cf, pj, dataset="3DVA", model="test")

    # Provenance tags must be distinct
    assert t_proc.input_mode == "processed_json"
    assert t_csv.input_mode == "csv_compat"
    assert t_proc.provenance["input_mode"] == "processed_json"
    assert t_csv.provenance["input_mode"] == "csv_compat"
    # CSV provenance has extra fields not present in processed provenance
    assert "csv_num_rows" in t_csv.provenance
    assert "csv_num_rows" not in t_proc.provenance


# ── A1.7: out-of-range sample rejection in CSV mode ──────────────────────────

def test_csv_out_of_range_dropped_not_clamped():
    fps, duration = 30, 17
    timing = _expected_timing(fps, duration)
    placement_start = timing["placement_start"]
    placement_end = timing["placement_end_exclusive"]

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        pj = tmp / "placement.json"
        cf = tmp / "model.csv"
        _write_json(pj, _make_placement_json())

        # Build rows: include out-of-window samples at t<crop_start and t>crop_end
        rows = _make_csv_rows(
            fps, placement_start, placement_end,
            include_out_of_window=True,
        )
        _write_csv(cf, rows, ["participation_id", "video_id", "data_gazes"])

        track = load_csv_compat_track(cf, pj, dataset="3DVA", model="test")

    # No gaze batch key should be outside the approved window
    for frame_idx in track.gaze_batches:
        assert placement_start <= frame_idx < placement_end, (
            f"Frame {frame_idx} is outside approved window "
            f"[{placement_start}, {placement_end})"
        )

    # The last valid placement frame is placement_end - 1, not total_frames - 1.
    # If clamping occurred, we'd see frame total_frames-1 in the batch dict.
    total_frames = fps * duration
    assert total_frames - 1 not in track.gaze_batches, (
        "Out-of-window sample was clamped to last frame — this is a bug"
    )

    # Provenance must record dropped count
    assert track.provenance["csv_dropped_out_of_window"] > 0


# ── A1.7b: samples exactly at boundary ───────────────────────────────────────

def test_csv_boundary_samples():
    """Samples exactly at placement_start are included; frame < placement_start dropped."""
    fps, duration = 30, 17
    timing = _expected_timing(fps, duration)
    placement_start = timing["placement_start"]
    placement_end = timing["placement_end_exclusive"]

    # Boundary timestamps: one sample just inside, one just outside
    t_inside = placement_start / fps          # exactly at start → frame == placement_start
    t_before = (placement_start - 1) / fps   # one frame before → dropped

    gaze_row = {
        "participation_id": "p001",
        "video_id": 1,
        "data_gazes": str({"t": [t_inside, t_before], "x": [0.5, 0.5], "y": [0.5, 0.5]}),
    }

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        pj = tmp / "placement.json"
        cf = tmp / "model.csv"
        _write_json(pj, _make_placement_json())
        _write_csv(cf, [gaze_row], ["participation_id", "video_id", "data_gazes"])

        track = load_csv_compat_track(cf, pj, dataset="3DVA", model="test")

    assert placement_start in track.gaze_batches, "In-window sample must be included"
    assert (placement_start - 1) not in track.gaze_batches, (
        "Out-of-window sample must not appear"
    )
    assert track.provenance["csv_dropped_out_of_window"] == 1


# ── A1 provenance completeness ────────────────────────────────────────────────

def test_provenance_fields_present():
    fps, duration = 30, 17
    timing = _expected_timing(fps, duration)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        pj = tmp / "placement.json"
        fj = tmp / "fixations.json"
        _write_json(pj, _make_placement_json())
        _write_json(fj, _make_processed_fixations(timing["usable_count"]))

        track = load_processed_track(
            fj, pj, dataset="3DVA", model="TestModel",
            canonical_name="3DVA_TestModel",
        )

    required = [
        "input_mode", "canonical_name", "dataset", "model",
        "fixation_source", "placement_source",
        "fixation_format", "fixation_start_index",
        "fps", "total_frames", "video_duration_seconds", "resolution",
        "crop_start_seconds", "crop_end_seconds",
        "crop_start_frames", "crop_end_frames",
        "placement_start_frame", "placement_end_frame_exclusive",
        "usable_count",
        "rotation_speed_deg_per_sec", "full_turn_seconds",
    ]
    for key in required:
        assert key in track.provenance, f"Missing provenance key: {key}"

    assert track.provenance["crop_start_seconds"] == CROP_START_SECONDS
    assert track.provenance["crop_end_seconds"] == CROP_END_SECONDS
    assert track.provenance["input_mode"] == "processed_json"
    assert track.provenance["canonical_name"] == "3DVA_TestModel"


# ── pairing correctness: frame index math ─────────────────────────────────────

def test_frame_pairing_index_math():
    """processed_gaze[k] must map to placement frame placement_start + k."""
    fps, duration = 30, 17
    timing = _expected_timing(fps, duration)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        pj = tmp / "placement.json"
        fj = tmp / "fixations.json"
        _write_json(pj, _make_placement_json())
        data = _make_processed_fixations(timing["usable_count"])
        _write_json(fj, data)

        track = load_processed_track(fj, pj, dataset="3DVA", model="test")

    placement_start = track.placement_start
    # For each gaze index k, key must be placement_start + k
    for k in range(track.usable_count):
        expected_key = placement_start + k
        assert expected_key in track.gaze_batches, (
            f"Missing gaze_batches key for k={k}, expected frame {expected_key}"
        )

    # No keys outside the window
    assert all(
        track.placement_start <= f < track.placement_end_exclusive
        for f in track.gaze_batches
    )
