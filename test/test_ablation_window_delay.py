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


# ── valid evaluator flags for every dataset/method ──────────────────────────────

def _valid_option_strings(eval_path: Path) -> set[str]:
    """Extract argparse option strings (\"--flag\") from an evaluator source file."""
    import re
    text = eval_path.read_text()
    return set(re.findall(r'"(--[a-z0-9-]+)"', text))


def test_build_command_uses_only_flags_the_evaluator_accepts():
    for ds in ("3dva", "meshmamba_non_texture", "meshmamba_rgb_texture", "sal3d"):
        for meth in ("cone", "screen_space"):
            job = AblationJob(ds, "M", meth, "cut_tail", 0.0)
            cmd = _m.build_command(job, _Args())
            valid = _valid_option_strings(_m._EVAL[ds][meth])
            used = [tok for tok in cmd if tok.startswith("--")]
            unknown = [f for f in used if f not in valid]
            assert unknown == [], f"{ds}/{meth} passes flags the evaluator rejects: {unknown}"
            assert "--obj-root" not in cmd and "--gt-root" not in cmd
            assert "--fixation-data-tag" in cmd


# ── canonical nested metric extraction (reviewer reproduction) ──────────────────

def test_extract_metrics_descends_fixed_face_gt():
    report = {"metrics_vs_fixed_face_gt": {"cone_gaussian_on_mesh": {"CC": 0.55, "SIM": 0.6}}}
    metrics = _m.extract_metrics(report, "sal3d", "cone")
    assert metrics is not None and metrics["CC"] == 0.55


def test_extract_metrics_screen_space_leaf():
    report = {"metrics_vs_gt_covered_only": {"screen_space_gaussian": {"CC": 0.31}}}
    metrics = _m.extract_metrics(report, "sal3d", "screen_space")
    assert metrics["CC"] == 0.31


# ── job identity embeds the contract ────────────────────────────────────────────

def test_job_key_embeds_release_timing_frame_offset():
    job = AblationJob("sal3d", "M", "cone", "cut_head", 0.0)
    assert _m.RELEASE_TAG in job.key
    assert _m.TIMING_CONTRACT in job.key
    assert f"fo{job.frame_offset}" in job.key
    assert job.frame_offset == 60  # SAL3D tail = 720 - 660


# ── strict provenance (missing fields = mismatch) ───────────────────────────────

def test_provenance_missing_fields_flagged():
    out = _m._provenance_mismatches({}, frame_offset=0, delay_seconds=0.0)
    assert out == ["participant_input missing or not an object"]
    good = {"participant_input": {"timing_contract": "one_turn_from_start",
                                  "frame_offset": 60, "fixation_data_tag":
                                  "processed_fixations_offset0_full_cleaned",
                                  "delay_frames": 0, "fps": 30.0}}
    assert _m._provenance_mismatches(good, frame_offset=60, delay_seconds=0.0) == []
