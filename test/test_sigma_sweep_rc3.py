"""
Unit tests for test/launch/run_sigma_sweep_rc3.py — build_command correctness.

Regression guard for the --model vs --models CLI mismatch that caused all 464
vg-iai jobs to fail with "unrecognized arguments: --models <name>".

Smoke command (real, non-dry-run) — copy-paste on a server with data:

    python3 test/launch/run_sigma_sweep_rc3.py \\
        --datasets meshmamba_non_texture \\
        --methods screen_space \\
        --models Starfruit_L3 \\
        --ss-multipliers 1.0 \\
        --workers 1 \\
        --batch-output-dir /tmp/sigma_smoke_test

This runs exactly 1 job and actually invokes the evaluator subprocess,
catching CLI argument errors that --dry-run would miss.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# Import run_sigma_sweep_rc3 without requiring __init__.py in test/launch/
_RUNNER_PATH = REPO_ROOT / "test" / "launch" / "run_sigma_sweep_rc3.py"
_spec = importlib.util.spec_from_file_location("run_sigma_sweep_rc3", _RUNNER_PATH)
_runner = importlib.util.module_from_spec(_spec)
sys.modules["run_sigma_sweep_rc3"] = _runner  # required for @dataclass __module__ lookup
_spec.loader.exec_module(_runner)

SigmaSweepJob = _runner.SigmaSweepJob
build_command = _runner.build_command


def _args(tmp_path: Path) -> argparse.Namespace:
    ns = argparse.Namespace()
    ns.batch_output_dir = tmp_path
    ns.fixation_root = None
    return ns


def _cmd(dataset: str, method: str, model: str, tmp_path: Path, **kw) -> list[str]:
    job = SigmaSweepJob(dataset=dataset, model=model, method=method, **kw)
    return [str(x) for x in build_command(job, _args(tmp_path))]


# ── --model / --models assertion ─────────────────────────────────────────────

class TestModelArgSingular:
    """Every evaluator call must use --model (singular), never --models."""

    def test_meshmamba_cone(self, tmp_path):
        cmd = _cmd("meshmamba_non_texture", "cone", "UFO_v1_L2", tmp_path,
                   sigma_deg=1.0)
        assert "--model" in cmd
        assert "--models" not in cmd
        assert cmd[cmd.index("--model") + 1] == "UFO_v1_L2"

    def test_meshmamba_screen_space(self, tmp_path):
        cmd = _cmd("meshmamba_non_texture", "screen_space", "Starfruit_L3", tmp_path,
                   sigma_multiplier=1.0, sigma_screen_base=0.05,
                   sigma_screen_effective=0.05)
        assert "--model" in cmd
        assert "--models" not in cmd
        assert cmd[cmd.index("--model") + 1] == "Starfruit_L3"

    def test_sal3d_cone(self, tmp_path):
        cmd = _cmd("sal3d", "cone", "bunny", tmp_path, sigma_deg=1.0)
        assert "--model" in cmd
        assert "--models" not in cmd
        assert cmd[cmd.index("--model") + 1] == "bunny"

    def test_sal3d_screen_space(self, tmp_path):
        cmd = _cmd("sal3d", "screen_space", "horse", tmp_path,
                   sigma_multiplier=1.0, sigma_screen_base=0.014,
                   sigma_screen_effective=0.014)
        assert "--model" in cmd
        assert "--models" not in cmd
        assert cmd[cmd.index("--model") + 1] == "horse"

    def test_3dva_cone(self, tmp_path):
        cmd = _cmd("3dva", "cone", "A380", tmp_path, sigma_deg=1.0)
        assert "--model" in cmd
        assert "--models" not in cmd
        assert cmd[cmd.index("--model") + 1] == "A380"

    def test_3dva_screen_space(self, tmp_path):
        cmd = _cmd("3dva", "screen_space", "bunny", tmp_path,
                   sigma_multiplier=1.0, sigma_screen_base=0.025,
                   sigma_screen_effective=0.025)
        assert "--model" in cmd
        assert "--models" not in cmd
        assert cmd[cmd.index("--model") + 1] == "bunny"


# ── sigma argument routing ────────────────────────────────────────────────────

class TestSigmaArgs:
    """Correct sigma flags per dataset/method."""

    def test_meshmamba_screen_space_uses_sigma_screen(self, tmp_path):
        cmd = _cmd("meshmamba_non_texture", "screen_space", "Starfruit_L3", tmp_path,
                   sigma_multiplier=1.0, sigma_screen_base=0.05,
                   sigma_screen_effective=0.05)
        assert "--sigma-screen" in cmd
        assert "--sigma-px" not in cmd

    def test_3dva_screen_space_uses_sigma_px(self, tmp_path):
        cmd = _cmd("3dva", "screen_space", "A380", tmp_path,
                   sigma_multiplier=1.0, sigma_screen_base=0.025,
                   sigma_screen_effective=0.025)
        assert "--sigma-px" in cmd
        assert "--sigma-screen" not in cmd

    def test_sal3d_screen_space_uses_sigma_px(self, tmp_path):
        cmd = _cmd("sal3d", "screen_space", "bunny", tmp_path,
                   sigma_multiplier=1.0, sigma_screen_base=0.014,
                   sigma_screen_effective=0.014)
        assert "--sigma-px" in cmd
        assert "--sigma-screen" not in cmd

    def test_meshmamba_cone_uses_sigma_deg_and_radius(self, tmp_path):
        cmd = _cmd("meshmamba_non_texture", "cone", "Starfruit_L3", tmp_path,
                   sigma_deg=1.25)
        assert "--sigma-deg" in cmd
        assert "--radius-sigma-mult" in cmd

    def test_3dva_cone_uses_sigma_deg_and_radius(self, tmp_path):
        cmd = _cmd("3dva", "cone", "A380", tmp_path, sigma_deg=0.65)
        assert "--sigma-deg" in cmd
        assert "--radius-sigma-mult" in cmd


# ── timing contract args ──────────────────────────────────────────────────────

class TestTimingArgs:
    """Timing contract args must be present in every command."""

    def test_timing_contract_present(self, tmp_path):
        cmd = _cmd("meshmamba_non_texture", "screen_space", "Starfruit_L3", tmp_path,
                   sigma_multiplier=1.0, sigma_screen_base=0.05,
                   sigma_screen_effective=0.05)
        assert "--timing-contract" in cmd
        assert "--delay-seconds" in cmd
        assert "--frame-offset" in cmd

    def test_timing_contract_value(self, tmp_path):
        cmd = _cmd("3dva", "cone", "A380", tmp_path, sigma_deg=1.0)
        tc_idx = cmd.index("--timing-contract")
        assert cmd[tc_idx + 1] == "one_turn_from_start"

    def test_delay_seconds_value(self, tmp_path):
        cmd = _cmd("sal3d", "cone", "bunny", tmp_path, sigma_deg=1.0)
        ds_idx = cmd.index("--delay-seconds")
        assert cmd[ds_idx + 1] == "0.0"

    def test_frame_offset_value(self, tmp_path):
        cmd = _cmd("sal3d", "screen_space", "horse", tmp_path,
                   sigma_multiplier=1.0, sigma_screen_base=0.014,
                   sigma_screen_effective=0.014)
        fo_idx = cmd.index("--frame-offset")
        assert cmd[fo_idx + 1] == "0"


# ── meshmamba texture-type routing ────────────────────────────────────────────

class TestMeshmambaTextureType:
    """texture-type must match the dataset."""

    def test_non_texture_flag(self, tmp_path):
        cmd = _cmd("meshmamba_non_texture", "screen_space", "Starfruit_L3", tmp_path,
                   sigma_multiplier=1.0, sigma_screen_base=0.05,
                   sigma_screen_effective=0.05)
        assert "--texture-type" in cmd
        tt_idx = cmd.index("--texture-type")
        assert cmd[tt_idx + 1] == "non_texture"

    def test_rgb_texture_flag(self, tmp_path):
        cmd = _cmd("meshmamba_rgb_texture", "cone", "Avocado_L3", tmp_path,
                   sigma_deg=1.0)
        assert "--texture-type" in cmd
        tt_idx = cmd.index("--texture-type")
        assert cmd[tt_idx + 1] == "rgb_texture"


# ── output-dir and tag ────────────────────────────────────────────────────────

class TestOutputArgs:
    """--output-dir and --tag must be in every command."""

    def test_output_dir_present(self, tmp_path):
        cmd = _cmd("meshmamba_non_texture", "cone", "Starfruit_L3", tmp_path,
                   sigma_deg=1.0)
        assert "--output-dir" in cmd

    def test_tag_present(self, tmp_path):
        cmd = _cmd("meshmamba_non_texture", "cone", "Starfruit_L3", tmp_path,
                   sigma_deg=1.0)
        assert "--tag" in cmd
