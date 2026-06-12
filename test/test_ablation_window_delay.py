"""
Tests for test/launch/run_ablation_window_delay.py (Gate 2):

- evaluator receives --model (singular), never --models.
- 3DVA screen_space baseline sigma is 49.0 px (not the SAL3D 26.3).
- Infeasible window/delay combinations are detected before launch.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

_PATH = REPO_ROOT / "test" / "launch" / "run_ablation_window_delay.py"
_spec = importlib.util.spec_from_file_location("run_ablation_window_delay", _PATH)
_m = importlib.util.module_from_spec(_spec)
sys.modules["run_ablation_window_delay"] = _m  # for @dataclass __module__ lookup
_spec.loader.exec_module(_m)

AblationJob = _m.AblationJob


class _Args:
    fixation_root = None
    batch_output_dir = "/tmp/ablation_test"


def test_build_command_uses_singular_model():
    job = AblationJob("3dva", "A380", "cone", "cut_tail", 0.0)
    cmd = _m.build_command(job, _Args())
    assert "--model" in cmd
    assert "--models" not in cmd
    # value follows the flag
    assert cmd[cmd.index("--model") + 1] == "A380"


def test_3dva_screen_space_baseline_sigma_is_49():
    assert _m._SIGMA_DEFAULTS["screen_space"]["3dva"] == {"sigma_px": 49.0}
    # SAL3D stays at its own tracker-accuracy baseline.
    assert _m._SIGMA_DEFAULTS["screen_space"]["sal3d"] == {"sigma_px": 26.3}


def test_cut_tail_is_feasible():
    for d in (-0.3, 0.0, 0.3):
        job = AblationJob("sal3d", "alien", "cone", "cut_tail", d)
        feasible, reason = _m.job_feasibility(job)
        assert feasible, reason


def test_cut_head_extreme_positive_delay_infeasible_sal3d():
    # SAL3D: total=720, turn=660, tail=60 → gaze[69:729] exceeds 720.
    job = AblationJob("sal3d", "alien", "cone", "cut_head", 0.3)
    feasible, reason = _m.job_feasibility(job)
    assert not feasible
    assert "exceeds total_frames" in reason


def test_center_default_grid_feasible():
    for d in _m.ALL_DELAYS:
        job = AblationJob("3dva", "A380", "screen_space", "center", d)
        feasible, reason = _m.job_feasibility(job)
        assert feasible, reason
