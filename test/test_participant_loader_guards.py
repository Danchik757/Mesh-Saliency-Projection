"""
Guard tests for utils/participant_loader.py (Gate 2 hardening):

- _derive_timing_one_turn rejects negative frame_offset / negative window starts
  that would otherwise cause silent negative indexing.
- guard_report_compatible refuses to silently accept an unreadable/corrupt
  existing report (raises ResumeReportUnreadableError).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from utils.participant_loader import (  # noqa: E402
    TIMING_CONTRACT_ONE_TURN,
    TimingValidationError,
    ResumeReportUnreadableError,
    _derive_timing_one_turn,
    guard_report_compatible,
)


def _placement(fps: int = 30, duration_seconds: int = 17,
               rotation_speed_deg_per_sec: float = 24.0) -> dict:
    total = fps * duration_seconds
    frames = []
    for i in range(total):
        angle = rotation_speed_deg_per_sec * duration_seconds * i / (total - 1)
        frames.append({"frame": i + 1, "timestamp": i / fps,
                       "rotation_z_degrees": angle,
                       "rotation_z_radians": math.radians(angle)})
    return {
        "video_info": {"fps": fps, "duration_seconds": duration_seconds,
                       "total_frames": total, "resolution_width": 1920,
                       "resolution_height": 1080, "aspect_ratio": 1920 / 1080},
        "animation": {"rotation_speed_deg_per_sec": rotation_speed_deg_per_sec},
        "frames": frames,
    }


def test_one_turn_baseline_ok():
    timing = _derive_timing_one_turn(_placement(), Path("p.json"), delay_seconds=0.0,
                                     frame_offset=0)
    assert timing["gaze_start"] == 0
    assert timing["placement_start"] == 0
    assert timing["turn_frames"] == 450


def test_negative_frame_offset_rejected():
    with pytest.raises(TimingValidationError) as exc:
        _derive_timing_one_turn(_placement(), Path("p.json"), delay_seconds=0.0,
                                frame_offset=-1)
    assert "frame_offset" in str(exc.value)


def test_negative_window_start_rejected():
    # A large negative delay with frame_offset 0 cannot push the *start* below 0
    # because of max(0, ...), so the negative-start guard is exercised via a
    # negative frame_offset that also drives gaze/placement start negative.
    with pytest.raises(TimingValidationError):
        _derive_timing_one_turn(_placement(), Path("p.json"), delay_seconds=-0.2,
                                frame_offset=-5)


def test_unreadable_report_not_silently_accepted(tmp_path):
    bad = tmp_path / "corrupt_report.json"
    bad.write_text("{ this is not valid json")
    with pytest.raises(ResumeReportUnreadableError):
        guard_report_compatible(bad, timing_contract=TIMING_CONTRACT_ONE_TURN)


def test_report_not_object_rejected(tmp_path):
    arr = tmp_path / "list_report.json"
    arr.write_text(json.dumps([1, 2, 3]))
    with pytest.raises(ResumeReportUnreadableError):
        guard_report_compatible(arr, timing_contract=TIMING_CONTRACT_ONE_TURN)


def test_missing_report_is_noop(tmp_path):
    # Absent report stays a no-op (regression guard for the existing behaviour).
    guard_report_compatible(tmp_path / "nope.json", timing_contract=TIMING_CONTRACT_ONE_TURN)
