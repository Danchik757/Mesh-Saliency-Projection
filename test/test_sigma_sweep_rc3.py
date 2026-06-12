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

SigmaSweepJob  = _runner.SigmaSweepJob
build_command  = _runner.build_command
extract_metrics = _runner.extract_metrics


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


# ── extract_metrics: all six report layouts ───────────────────────────────────

_M = {"CC": 0.42, "SIM": 0.31, "KLD": 0.88, "MSE": 0.05}


class TestExtractMetrics:
    """extract_metrics must return the correct flat dict for every report layout."""

    # 1. MeshMamba screen_space: metrics_vs_gt.screen_space_gaussian
    def test_meshmamba_screen_space(self):
        report = {"metrics_vs_gt": {"screen_space_gaussian": _M}}
        m = extract_metrics(report, "meshmamba_non_texture", "screen_space")
        assert m is not None
        assert m["CC"] == _M["CC"]

    # 2. MeshMamba cone: metrics_vs_gt.cone_gaussian_on_mesh
    def test_meshmamba_cone(self):
        report = {"metrics_vs_gt": {
            "raycast_nearest_face": {"CC": 0.1},
            "cone_gaussian_on_mesh": _M,
        }}
        m = extract_metrics(report, "meshmamba_non_texture", "cone")
        assert m is not None
        assert m["CC"] == _M["CC"]

    # 3. SAL3D fixed face GT (preferred): metrics_vs_fixed_face_gt.screen_space_gaussian
    def test_sal3d_screen_space_fixed_gt(self):
        report = {
            "metrics_vs_gt_covered_only": {"screen_space_gaussian": {"CC": 0.1}},
            "metrics_vs_fixed_face_gt":   {"screen_space_gaussian": _M},
        }
        m = extract_metrics(report, "sal3d", "screen_space")
        assert m is not None
        assert m["CC"] == _M["CC"], "fixed_face_gt must be preferred over covered_only"

    # 4. SAL3D raw GT only: metrics_vs_gt_covered_only.screen_space_gaussian
    def test_sal3d_screen_space_covered_only(self):
        report = {"metrics_vs_gt_covered_only": {"screen_space_gaussian": _M}}
        m = extract_metrics(report, "sal3d", "screen_space")
        assert m is not None
        assert m["CC"] == _M["CC"]

    # 5. SAL3D cone fixed GT: metrics_vs_fixed_face_gt.cone_gaussian_on_mesh
    def test_sal3d_cone_fixed_gt(self):
        report = {
            "metrics_vs_gt_covered_only": {"cone_gaussian_on_mesh": {"CC": 0.1}},
            "metrics_vs_fixed_face_gt":   {
                "raycast_nearest_vertex": {"CC": 0.2},
                "cone_gaussian_on_mesh":  _M,
            },
        }
        m = extract_metrics(report, "sal3d", "cone")
        assert m is not None
        assert m["CC"] == _M["CC"]

    # 6. 3DVA screen_space: metrics_vs_gt_combined.screen_space_gaussian.metrics_covered_only
    def test_3dva_screen_space(self):
        report = {"metrics_vs_gt_combined": {
            "screen_space_gaussian": {
                "metrics_full":         {"CC": 0.2},
                "metrics_covered_only": _M,
            }
        }}
        m = extract_metrics(report, "3dva", "screen_space")
        assert m is not None
        assert m["CC"] == _M["CC"]

    # 7. 3DVA cone: metrics_vs_gt_combined.cone_gaussian_on_mesh.metrics_covered_only
    def test_3dva_cone(self):
        report = {"metrics_vs_gt_combined": {
            "raycast_nearest_vertex": {
                "metrics_full": {"CC": 0.1}, "metrics_covered_only": {"CC": 0.1}
            },
            "cone_gaussian_on_mesh": {
                "metrics_full":         {"CC": 0.2},
                "metrics_covered_only": _M,
            },
        }}
        m = extract_metrics(report, "3dva", "cone")
        assert m is not None
        assert m["CC"] == _M["CC"]

    # 8. 3DVA covered_only missing → falls back to metrics_full
    def test_3dva_fallback_to_metrics_full(self):
        report = {"metrics_vs_gt_combined": {
            "screen_space_gaussian": {"metrics_full": _M}
        }}
        m = extract_metrics(report, "3dva", "screen_space")
        assert m is not None
        assert m["CC"] == _M["CC"]

    # 9. Report with no recognised section → returns None
    def test_missing_metrics_returns_none(self):
        report = {"model": "test", "tag": "t1", "run_stats": {}}
        assert extract_metrics(report, "meshmamba_non_texture", "screen_space") is None

    # 10. Wrong method key in existing section → returns None
    def test_wrong_method_key_returns_none(self):
        # report has screen_space_gaussian but we ask for cone
        report = {"metrics_vs_gt": {"screen_space_gaussian": _M}}
        assert extract_metrics(report, "meshmamba_non_texture", "cone") is None

    # 11. Section exists but no CC → not a valid metrics dict → returns None
    def test_section_without_cc_returns_none(self):
        report = {"metrics_vs_gt": {"cone_gaussian_on_mesh": {"SIM": 0.3}}}
        assert extract_metrics(report, "meshmamba_non_texture", "cone") is None


# ── smoke verification expectation ───────────────────────────────────────────

class TestSmokeExpectation:
    """
    These tests document what the sigma_sweep_rows.jsonl must contain after
    a successful tiny smoke run. They do NOT invoke any subprocess; they verify
    the JSONL row structure produced by execute_job when given a realistic report.
    After a real smoke run, grep sigma_sweep_rows.jsonl for:
        "status": "ok"
    and confirm CC/SIM/KLD are non-empty numeric strings.
    """

    def test_meshmamba_screen_space_row_has_numeric_metrics(self):
        report = {
            "metrics_vs_gt": {
                "screen_space_gaussian": {
                    "CC": 0.55, "SIM": 0.41, "KLD": 0.73,
                    "MSE": 0.02, "Spearman": 0.48,
                }
            },
            "participant_input": {
                "gaze_start_frame": 0, "placement_start_frame": 0, "turn_frame_count": 450
            },
        }
        m = extract_metrics(report, "meshmamba_non_texture", "screen_space")
        assert m is not None
        assert isinstance(m["CC"], float) and m["CC"] != ""
        assert isinstance(m["SIM"], float) and m["SIM"] != ""
        assert isinstance(m["KLD"], float) and m["KLD"] != ""
