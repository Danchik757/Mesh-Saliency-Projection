"""
Unit tests for video_creation/gaze_heatmap_overlays/render_fixation_overlay.py.

All tests are pure logic — no ffmpeg, no real video files, no scipy/PIL required
beyond what's already in the environment.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

from video_creation.gaze_heatmap_overlays.render_fixation_overlay import (
    DEFAULT_EXCLUDED,
    FIXATION_RESOLUTION,
    MODES,
    TURN_FRAMES,
    FixationJsonFrameGenerator,
    detect_dataset,
    load_fixation_json,
    n_frames_for_mode,
    parse_model_key,
)


# ── parse_model_key ────────────────────────────────────────────────────────────

class TestParseModelKey:
    def test_3dva(self):
        r = parse_model_key("3DVA_A380")
        assert r == {"dataset": "3DVA", "track": "", "model": "A380"}

    def test_3dva_multiword(self):
        r = parse_model_key("3DVA_Max-Planck")
        assert r["dataset"] == "3DVA"
        assert r["model"] == "Max-Planck"
        assert r["track"] == ""

    def test_sal3d(self):
        r = parse_model_key("SAL3D_bunny")
        assert r == {"dataset": "SAL3D", "track": "", "model": "bunny"}

    def test_meshmamba_non_texture(self):
        r = parse_model_key("MeshMamba_non_texture_Starfruit_L3")
        assert r["dataset"] == "MeshMamba"
        assert r["track"] == "non_texture"
        assert r["model"] == "Starfruit_L3"

    def test_meshmamba_rgb_texture(self):
        r = parse_model_key("MeshMamba_rgb_texture_Pear_L3")
        assert r["dataset"] == "MeshMamba"
        assert r["track"] == "rgb_texture"
        assert r["model"] == "Pear_L3"

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Cannot parse dataset"):
            parse_model_key("Unknown_something")

    def test_jessi_3dva(self):
        r = parse_model_key("3DVA_jessi")
        assert r["dataset"] == "3DVA"
        assert r["model"] == "jessi"

    def test_jessi_sal3d(self):
        r = parse_model_key("SAL3D_jessi")
        assert r["dataset"] == "SAL3D"


# ── detect_dataset ─────────────────────────────────────────────────────────────

class TestDetectDataset:
    def test_3dva(self):
        assert detect_dataset("3DVA_A380") == "3DVA"

    def test_sal3d(self):
        assert detect_dataset("SAL3D_alien") == "SAL3D"

    def test_meshmamba(self):
        assert detect_dataset("MeshMamba_non_texture_Cat_v1_L3") == "MeshMamba"


# ── TURN_FRAMES ────────────────────────────────────────────────────────────────

class TestTurnFrames:
    def test_3dva_450(self):
        assert TURN_FRAMES["3DVA"] == 450

    def test_meshmamba_450(self):
        assert TURN_FRAMES["MeshMamba"] == 450

    def test_sal3d_660(self):
        assert TURN_FRAMES["SAL3D"] == 660

    def test_all_datasets_present(self):
        for ds in ("3DVA", "MeshMamba", "SAL3D"):
            assert ds in TURN_FRAMES


# ── DEFAULT_EXCLUDED ───────────────────────────────────────────────────────────

class TestDefaultExcluded:
    def test_jessi_excluded(self):
        assert "3DVA_jessi" in DEFAULT_EXCLUDED

    def test_sal3d_jessi_not_excluded(self):
        assert "SAL3D_jessi" not in DEFAULT_EXCLUDED

    def test_is_frozenset(self):
        assert isinstance(DEFAULT_EXCLUDED, frozenset)


# ── n_frames_for_mode ─────────────────────────────────────────────────────────

class TestNFramesForMode:
    def test_full_returns_json_count(self):
        assert n_frames_for_mode("full_video_overlay", "3DVA", 510) == 510

    def test_full_sal3d(self):
        assert n_frames_for_mode("full_video_overlay", "SAL3D", 720) == 720

    def test_benchmark_3dva(self):
        assert n_frames_for_mode("benchmark_one_turn_overlay", "3DVA", 510) == 450

    def test_benchmark_meshmamba(self):
        assert n_frames_for_mode("benchmark_one_turn_overlay", "MeshMamba", 510) == 450

    def test_benchmark_sal3d(self):
        assert n_frames_for_mode("benchmark_one_turn_overlay", "SAL3D", 720) == 660

    def test_benchmark_clamps_to_json_length(self):
        # jessi: only 41 frames — min(450, 41) = 41
        assert n_frames_for_mode("benchmark_one_turn_overlay", "3DVA", 41) == 41

    def test_benchmark_does_not_exceed_json_length(self):
        # Hypothetical short file
        assert n_frames_for_mode("benchmark_one_turn_overlay", "SAL3D", 100) == 100


# ── load_fixation_json ─────────────────────────────────────────────────────────

class TestLoadFixationJson:
    def test_loads_list(self, tmp_path):
        frames = [[[100, 200], [300, 400]], [[500, 600]]]
        p = tmp_path / "fixations.json"
        p.write_text(json.dumps(frames))
        result = load_fixation_json(p)
        assert result == frames

    def test_empty_frames_ok(self, tmp_path):
        p = tmp_path / "fixations.json"
        p.write_text(json.dumps([[], []]))
        result = load_fixation_json(p)
        assert result == [[], []]

    def test_non_list_raises(self, tmp_path):
        p = tmp_path / "fixations.json"
        p.write_text(json.dumps({"frames": []}))
        with pytest.raises(ValueError, match="Expected list"):
            load_fixation_json(p)


# ── FixationJsonFrameGenerator ─────────────────────────────────────────────────

class TestFixationJsonFrameGenerator:
    def _make(self, frames, height=54, width=96, sigma_ref_px=40.0,
              fixation_resolution=(1920, 1080)):
        return FixationJsonFrameGenerator(
            frames=frames,
            height=height,
            width=width,
            sigma_ref_px=sigma_ref_px,
            fixation_resolution=fixation_resolution,
        )

    def test_sigma_scales_with_width(self):
        gen960 = self._make([], width=960)
        gen1920 = self._make([], width=1920)
        assert abs(gen960.sigma - 20.0) < 1e-9    # 40 * 960/1920
        assert abs(gen1920.sigma - 40.0) < 1e-9

    def test_empty_frame_returns_zeros(self):
        gen = self._make([[]])
        sm = gen.get_frame_impulse(0)
        assert sm.shape == (54, 96)
        assert sm.sum() == 0.0

    def test_out_of_bounds_frame_returns_zeros(self):
        gen = self._make([[]])
        sm = gen.get_frame_impulse(999)
        assert sm.sum() == 0.0

    def test_single_point_deposited(self):
        # Pixel (960, 540) in 1920x1080 space maps to center of 96x54 map
        frames = [[[960, 540]]]
        gen = self._make(frames, height=54, width=96)
        sm = gen.get_frame_impulse(0)
        assert sm.sum() > 0.0
        i, j = np.unravel_index(sm.argmax(), sm.shape)
        # x=960 → j=48 (960/1920*96=48); y=540 → i=27 (540/1080*54=27)
        assert j == 48
        assert i == 27

    def test_multiple_points_sum_to_one(self):
        frames = [[[0, 0], [1920, 1080], [960, 540]]]
        gen = self._make(frames, height=54, width=96)
        sm = gen.get_frame_impulse(0)
        assert abs(float(sm.sum()) - 1.0) < 1e-5

    def test_out_of_range_coords_clipped(self):
        frames = [[[-100, -200], [9999, 9999]]]
        gen = self._make(frames)
        sm = gen.get_frame_impulse(0)
        assert np.isfinite(sm).all()
        assert sm.sum() > 0.0

    def test_origin_clipped_to_top_left(self):
        frames = [[[0, 0]]]
        gen = self._make(frames, height=54, width=96)
        sm = gen.get_frame_impulse(0)
        assert sm[0, 0] > 0.0

    def test_max_coord_clipped_to_bottom_right(self):
        frames = [[[1919, 1079]]]
        gen = self._make(frames, height=54, width=96)
        sm = gen.get_frame_impulse(0)
        assert sm[-1, -1] > 0.0

    def test_shape_matches_constructor(self):
        gen = self._make([[]], height=108, width=192)
        sm = gen.get_frame_impulse(0)
        assert sm.shape == (108, 192)

    def test_output_dtype_float32(self):
        gen = self._make([[[100, 100]]])
        sm = gen.get_frame_impulse(0)
        assert sm.dtype == np.float32

    def test_second_frame_independent(self):
        frames = [[[0, 0]], [[1919, 1079]]]
        gen = self._make(frames, height=54, width=96)
        sm0 = gen.get_frame_impulse(0)
        sm1 = gen.get_frame_impulse(1)
        assert sm0[0, 0] > 0.0
        assert sm1[-1, -1] > 0.0
        assert sm0[-1, -1] == 0.0
        assert sm1[0, 0] == 0.0

    def test_all_points_same_location(self):
        frames = [[[960, 540], [960, 540], [960, 540]]]
        gen = self._make(frames, height=54, width=96)
        sm = gen.get_frame_impulse(0)
        # All points at same location; weight sums to 1.0
        assert abs(float(sm.sum()) - 1.0) < 1e-5

    def test_fixation_resolution_override(self):
        # With fixation_resolution=(96, 54), coords are already in map space
        frames = [[[48, 27]]]
        gen = self._make(frames, height=54, width=96, fixation_resolution=(96, 54))
        sm = gen.get_frame_impulse(0)
        assert sm[27, 48] > 0.0


# ── MODES constant ─────────────────────────────────────────────────────────────

class TestModes:
    def test_full_video_overlay_present(self):
        assert "full_video_overlay" in MODES

    def test_benchmark_one_turn_overlay_present(self):
        assert "benchmark_one_turn_overlay" in MODES

    def test_exactly_two_modes(self):
        assert len(MODES) == 2


# ── FIXATION_RESOLUTION constant ──────────────────────────────────────────────

class TestFixationResolution:
    def test_is_1920x1080(self):
        assert FIXATION_RESOLUTION == (1920, 1080)
