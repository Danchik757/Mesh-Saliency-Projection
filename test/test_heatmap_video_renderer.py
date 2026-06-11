"""
Unit tests for video_creation/heatmap_on_mesh_video/render_heatmap_video.py.

Only tests pure-logic functions (no pyvista, PIL, or ffmpeg required).
"""
from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path

import numpy as np
import pytest

import csv as _csv

from video_creation.heatmap_on_mesh_video.render_heatmap_video import (
    CROP_END_S,
    CROP_START_S,
    TURN_FRAMES,
    _CPU_FALLBACK_MAX_FRAMES,
    _CPU_RENDERER_PATTERNS,
    apply_frame_rotation,
    camera_from_placement,
    compute_rgb_colors,
    load_map,
    parse_obj,
    precompute_base_transform,
    probe_gpu_backend,
    resolve_frame_window,
    select_preview_indices,
    write_manifest,
    write_manifest_csv,
    _rotate_x,
    _rotate_z,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_placement(
    *,
    fps: int = 30,
    duration_s: int = 17,
    scale: float = 0.7,
    location: list = None,
    fov_degrees: float = 60.0,
    view_matrix: list = None,
) -> dict:
    total = fps * duration_s
    if location is None:
        location = [0.0, 0.0, 0.0]
    if view_matrix is None:
        # Identity (camera at origin, no rotation)
        view_matrix = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    frames = [
        {
            "frame": i + 1,
            "timestamp": i / fps,
            "rotation_z_radians": i * 0.01,
            "rotation_z_degrees": math.degrees(i * 0.01),
        }
        for i in range(total)
    ]
    return {
        "model_name": "test_model",
        "video_info": {
            "fps": fps,
            "duration_seconds": duration_s,
            "total_frames": total,
            "resolution_width": 1920,
            "resolution_height": 1080,
            "aspect_ratio": 1920 / 1080,
        },
        "camera_static": {
            "location": [0.0, -1.5, 0.7],
            "fov_degrees": fov_degrees,
            "view_matrix": view_matrix,
        },
        "model_static": {
            "location": location,
            "scale": [scale, scale, scale],
            "bbox_max_dimensions": {"width": 0.8, "depth": 0.8, "height": 0.7},
        },
        "animation": {
            "rotation_axis": "Z",
            "rotation_direction": "counter_clockwise",
        },
        "frames": frames,
    }


# ── crop window ───────────────────────────────────────────────────────────────

class TestCropWindow:
    def test_meshmamba_start(self):
        # 1.8 * 30 = 54
        assert round(CROP_START_S * 30) == 54

    def test_meshmamba_end(self):
        # 510 - round(0.2 * 30) = 510 - 6 = 504
        total = 510
        end = total - round(CROP_END_S * 30)
        assert end == 504

    def test_meshmamba_n_frames(self):
        start = round(CROP_START_S * 30)
        end = 510 - round(CROP_END_S * 30)
        assert end - start == 450

    def test_sal3d_start(self):
        assert round(CROP_START_S * 30) == 54

    def test_sal3d_end(self):
        total = 720
        end = total - round(CROP_END_S * 30)
        assert end == 714

    def test_sal3d_n_frames(self):
        start = round(CROP_START_S * 30)
        end = 720 - round(CROP_END_S * 30)
        assert end - start == 660

    def test_max_frames_truncates_end(self):
        start = round(CROP_START_S * 30)
        end = min(504, start + 120)
        assert end == start + 120


# ── rotation helpers ───────────────────────────────────────────────────────────

class TestRotateZ:
    def test_zero_rotation_is_identity(self):
        v = np.array([[1.0, 2.0, 3.0]])
        np.testing.assert_array_almost_equal(_rotate_z(v, 0.0), v)

    def test_90_degree_rotation(self):
        v = np.array([[1.0, 0.0, 0.0]])
        result = _rotate_z(v, math.pi / 2)
        np.testing.assert_array_almost_equal(result, [[0.0, 1.0, 0.0]], decimal=10)

    def test_180_degree_rotation(self):
        v = np.array([[1.0, 0.0, 0.0]])
        result = _rotate_z(v, math.pi)
        np.testing.assert_array_almost_equal(result, [[-1.0, 0.0, 0.0]], decimal=10)

    def test_z_coordinate_unchanged(self):
        v = np.array([[1.0, 2.0, 5.0]])
        result = _rotate_z(v, 1.23)
        assert result[0, 2] == pytest.approx(5.0)

    def test_does_not_modify_input(self):
        v = np.array([[1.0, 2.0, 3.0]])
        original = v.copy()
        _rotate_z(v, 0.5)
        np.testing.assert_array_equal(v, original)


class TestRotateX:
    def test_90_degree_rotation(self):
        # Rotate Y-axis to Z-axis
        v = np.array([[0.0, 1.0, 0.0]])
        result = _rotate_x(v, 90.0)
        np.testing.assert_array_almost_equal(result, [[0.0, 0.0, 1.0]], decimal=10)

    def test_x_coordinate_unchanged(self):
        v = np.array([[5.0, 1.0, 2.0]])
        result = _rotate_x(v, 45.0)
        assert result[0, 0] == pytest.approx(5.0)


class TestApplyFrameRotation:
    def test_zero_returns_identity(self):
        v = np.array([[1.0, 2.0, 3.0]])
        result = apply_frame_rotation(v, 0.0)
        np.testing.assert_array_almost_equal(result, v)

    def test_small_rotation_applied(self):
        v = np.array([[1.0, 0.0, 0.0]])
        result = apply_frame_rotation(v, math.pi / 4)
        expected_x = math.cos(math.pi / 4)
        assert result[0, 0] == pytest.approx(expected_x, abs=1e-10)


# ── precompute_base_transform ──────────────────────────────────────────────────

class TestPrecomputeBaseTransform:
    def test_recenter_removes_offset(self):
        # A cube offset by [10, 10, 10] should be centered at origin
        v = np.array([
            [9.0, 9.0, 9.0],
            [11.0, 9.0, 9.0],
            [9.0, 11.0, 9.0],
            [9.0, 9.0, 11.0],
            [11.0, 11.0, 11.0],
        ])
        placement = _make_placement(scale=1.0)
        result = precompute_base_transform(v, placement, recenter=True, extra_rotate_x_deg=0.0)
        center = 0.5 * (result.min(axis=0) + result.max(axis=0))
        # After recenter + zero location, center should be [0,0,0]
        np.testing.assert_array_almost_equal(center, [0, 0, 0], decimal=10)

    def test_scale_applied(self):
        v = np.array([[1.0, 0.0, 0.0], [-1.0, 0.0, 0.0]])
        placement = _make_placement(scale=0.5)
        result = precompute_base_transform(v, placement, recenter=False, extra_rotate_x_deg=0.0)
        assert result[0, 0] == pytest.approx(0.5)

    def test_location_not_included(self):
        # model_static.location must NOT be applied by precompute_base_transform;
        # it is added after per-frame rotation to match evaluator blender_rig order.
        v = np.array([[0.0, 0.0, 0.0]])
        placement = _make_placement(scale=1.0, location=[1.0, 2.0, 3.0])
        result = precompute_base_transform(v, placement, recenter=False, extra_rotate_x_deg=0.0)
        # Result should be at origin, not shifted by location
        np.testing.assert_array_almost_equal(result[0], [0.0, 0.0, 0.0])

    def test_full_transform_location_after_rotation(self):
        # Verify evaluator order: base → frame_rotation → +location
        v = np.array([[1.0, 0.0, 0.0]])
        placement = _make_placement(scale=1.0, location=[0.0, 0.0, 5.0])
        base = precompute_base_transform(v, placement, recenter=False, extra_rotate_x_deg=0.0)
        rotated = apply_frame_rotation(base, math.pi / 2)
        loc = np.array([0.0, 0.0, 5.0])
        final = rotated + loc
        # After 90° Z rotation: [1,0,0] → [0,1,0]; then +[0,0,5] → [0,1,5]
        np.testing.assert_array_almost_equal(final[0], [0.0, 1.0, 5.0], decimal=10)

    def test_extra_rotate_x_90_applied(self):
        # Y-axis point [0,1,0] → after 90° X rotation → [0,0,1]
        v = np.array([[0.0, 1.0, 0.0]])
        placement = _make_placement(scale=1.0, location=[0.0, 0.0, 0.0])
        result = precompute_base_transform(v, placement, recenter=False, extra_rotate_x_deg=90.0)
        np.testing.assert_array_almost_equal(result, [[0.0, 0.0, 1.0]], decimal=10)

    def test_no_extra_rotate_when_zero(self):
        v = np.array([[1.0, 2.0, 3.0]])
        placement = _make_placement(scale=1.0)
        result = precompute_base_transform(v, placement, recenter=False, extra_rotate_x_deg=0.0)
        np.testing.assert_array_almost_equal(result, [[1.0, 2.0, 3.0]])


# ── camera_from_placement ──────────────────────────────────────────────────────

class TestCameraFromPlacement:
    def _starfruit_view_matrix(self):
        return [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 0.42288540178106404, 0.9061831485706976, -9.052534735029626e-08],
            [0.0, -0.9061831485706976, 0.42288540178106404, -1.6552944990616043],
            [0.0, 0.0, 0.0, 1.0],
        ]

    def test_camera_position_matches_json_location(self):
        # For Starfruit, view_matrix should decode to camera at [0, -1.5, 0.7]
        placement = _make_placement(
            view_matrix=self._starfruit_view_matrix(),
            fov_degrees=60.0,
        )
        pos, fp, up, vfov = camera_from_placement(placement)
        np.testing.assert_array_almost_equal(pos, [0.0, -1.5, 0.7], decimal=5)

    def test_vertical_fov_less_than_horizontal(self):
        placement = _make_placement(
            view_matrix=self._starfruit_view_matrix(),
            fov_degrees=60.0,
        )
        _, _, _, vfov = camera_from_placement(placement)
        # For 16:9 aspect, vertical FOV < horizontal FOV (60°)
        assert vfov < 60.0
        assert vfov > 0.0

    def test_vertical_fov_approx_36_degrees(self):
        # At 1920×1080 aspect (16/9) and horizontal FOV 60°:
        # vfov = 2*atan(tan(30°) / (16/9)) ≈ 35.98°
        placement = _make_placement(
            view_matrix=self._starfruit_view_matrix(),
            fov_degrees=60.0,
        )
        _, _, _, vfov = camera_from_placement(placement)
        assert vfov == pytest.approx(35.98, abs=0.1)

    def test_focal_point_is_model_location(self):
        placement = _make_placement(
            view_matrix=self._starfruit_view_matrix(),
            location=[0.0, 0.0, 0.0],
        )
        _, fp, _, _ = camera_from_placement(placement)
        np.testing.assert_array_almost_equal(fp, [0.0, 0.0, 0.0])

    def test_up_vector_normalized(self):
        placement = _make_placement(view_matrix=self._starfruit_view_matrix())
        _, _, up, _ = camera_from_placement(placement)
        assert np.linalg.norm(up) == pytest.approx(1.0, abs=1e-6)


# ── load_map ──────────────────────────────────────────────────────────────────

class TestLoadMap:
    def _write_txt(self, values: np.ndarray, path: Path) -> None:
        np.savetxt(str(path), values, fmt="%.10f")

    def test_per_face_detected(self, tmp_path):
        n_faces = 100
        values = np.random.rand(n_faces)
        p = tmp_path / "map.txt"
        self._write_txt(values, p)
        loaded, domain = load_map(p, n_vertices=50, n_faces=n_faces)
        assert domain == "face"
        assert len(loaded) == n_faces

    def test_per_vertex_detected(self, tmp_path):
        n_vertices = 80
        values = np.random.rand(n_vertices)
        p = tmp_path / "map.txt"
        self._write_txt(values, p)
        loaded, domain = load_map(p, n_vertices=n_vertices, n_faces=60)
        assert domain == "vertex"
        assert len(loaded) == n_vertices

    def test_mismatch_raises_clear_error(self, tmp_path):
        values = np.random.rand(999)
        p = tmp_path / "map.txt"
        self._write_txt(values, p)
        with pytest.raises(ValueError, match="999"):
            load_map(p, n_vertices=100, n_faces=200)

    def test_multi_column_uses_gt_column(self, tmp_path):
        data = np.random.rand(50, 8)
        p = tmp_path / "gt.txt"
        np.savetxt(str(p), data, fmt="%.10f")
        loaded, domain = load_map(p, n_vertices=50, n_faces=30, gt_column=7)
        np.testing.assert_array_almost_equal(loaded, data[:, 7], decimal=5)
        assert domain == "vertex"

    def test_multi_column_default_gt_column_7(self, tmp_path):
        data = np.random.rand(50, 8)
        p = tmp_path / "gt.txt"
        np.savetxt(str(p), data, fmt="%.10f")
        loaded, _ = load_map(p, n_vertices=50, n_faces=30, gt_column=None)
        np.testing.assert_array_almost_equal(loaded, data[:, 7], decimal=5)

    def test_values_preserved(self, tmp_path):
        values = np.array([0.1, 0.5, 0.9, 0.3])
        p = tmp_path / "map.txt"
        self._write_txt(values, p)
        loaded, _ = load_map(p, n_vertices=4, n_faces=10)
        np.testing.assert_array_almost_equal(loaded, values, decimal=5)


# ── parse_obj ─────────────────────────────────────────────────────────────────

class TestParseObj:
    def test_simple_triangle(self, tmp_path):
        obj_text = (
            "v 0.0 0.0 0.0\n"
            "v 1.0 0.0 0.0\n"
            "v 0.0 1.0 0.0\n"
            "f 1 2 3\n"
        )
        p = tmp_path / "tri.obj"
        p.write_text(obj_text)
        verts, faces = parse_obj(p)
        assert verts.shape == (3, 3)
        assert faces.shape == (1, 3)
        np.testing.assert_array_equal(faces[0], [0, 1, 2])

    def test_face_indices_are_zero_based(self, tmp_path):
        obj_text = (
            "v 0.0 0.0 0.0\n"
            "v 1.0 0.0 0.0\n"
            "v 0.5 1.0 0.0\n"
            "f 3 2 1\n"
        )
        p = tmp_path / "tri.obj"
        p.write_text(obj_text)
        _, faces = parse_obj(p)
        np.testing.assert_array_equal(faces[0], [2, 1, 0])

    def test_slash_face_syntax(self, tmp_path):
        # f v/vt/vn syntax
        obj_text = (
            "v 0.0 0.0 0.0\n"
            "v 1.0 0.0 0.0\n"
            "v 0.0 1.0 0.0\n"
            "f 1/1/1 2/2/2 3/3/3\n"
        )
        p = tmp_path / "tri.obj"
        p.write_text(obj_text)
        _, faces = parse_obj(p)
        np.testing.assert_array_equal(faces[0], [0, 1, 2])

    def test_vertex_count(self, tmp_path):
        lines = ["v %f %f %f\n" % (i, i, i) for i in range(10)]
        lines += ["f 1 2 3\n"]
        p = tmp_path / "mesh.obj"
        p.write_text("".join(lines))
        verts, _ = parse_obj(p)
        assert len(verts) == 10


# ── write_manifest ────────────────────────────────────────────────────────────

class TestWriteManifest:
    def test_roundtrip(self, tmp_path):
        data = {"dataset": "MeshMamba", "n_frames": 120, "fps": 30}
        p = tmp_path / "manifest.json"
        write_manifest(p, data)
        loaded = json.loads(p.read_text())
        assert loaded == data

    def test_creates_parent_dirs(self, tmp_path):
        data = {"ok": True}
        p = tmp_path / "a" / "b" / "manifest.json"
        p.parent.mkdir(parents=True)
        write_manifest(p, data)
        assert p.exists()


# ── rc3 frame window ───────────────────────────────────────────────────────────

class TestRc3FrameWindow:
    def test_3dva_start_zero_end_450(self):
        start, end = resolve_frame_window("3dva", fps=30, total_frames=510,
                                          timing_contract="rc3_one_turn")
        assert start == 0
        assert end == 450

    def test_meshmamba_start_zero_end_450(self):
        start, end = resolve_frame_window("meshmamba", fps=30, total_frames=510,
                                          timing_contract="rc3_one_turn")
        assert start == 0
        assert end == 450

    def test_sal3d_start_zero_end_660(self):
        start, end = resolve_frame_window("sal3d", fps=30, total_frames=720,
                                          timing_contract="rc3_one_turn")
        assert start == 0
        assert end == 660

    def test_max_frames_truncates_end(self):
        start, end = resolve_frame_window("3dva", fps=30, total_frames=510,
                                          timing_contract="rc3_one_turn", max_frames=120)
        assert start == 0
        assert end == 120

    def test_short_total_frames_clamped(self):
        # total_frames < TURN_FRAMES → end capped at total_frames
        start, end = resolve_frame_window("3dva", fps=30, total_frames=100,
                                          timing_contract="rc3_one_turn")
        assert end == 100

    def test_dataset_case_insensitive(self):
        start, end = resolve_frame_window("MeshMamba", fps=30, total_frames=510,
                                          timing_contract="rc3_one_turn")
        assert end == 450

    def test_rc2_compat_start_54(self):
        start, end = resolve_frame_window("3dva", fps=30, total_frames=510,
                                          timing_contract="rc2_cropped")
        assert start == round(CROP_START_S * 30)  # 54

    def test_rc2_meshmamba_n_frames_450(self):
        start, end = resolve_frame_window("meshmamba", fps=30, total_frames=510,
                                          timing_contract="rc2_cropped")
        assert end - start == 450

    def test_rc2_sal3d_n_frames_660(self):
        start, end = resolve_frame_window("sal3d", fps=30, total_frames=720,
                                          timing_contract="rc2_cropped")
        assert end - start == 660

    def test_unknown_dataset_raises(self):
        with pytest.raises(ValueError, match="Unknown dataset"):
            resolve_frame_window("bogus", fps=30, total_frames=510,
                                 timing_contract="rc3_one_turn")

    def test_unknown_contract_raises(self):
        with pytest.raises(ValueError, match="Unknown timing_contract"):
            resolve_frame_window("3dva", fps=30, total_frames=510,
                                 timing_contract="not_a_contract")

    def test_turn_frames_constant_keys(self):
        for ds in ("3dva", "meshmamba", "sal3d"):
            assert ds in TURN_FRAMES

    def test_turn_frames_values(self):
        assert TURN_FRAMES["3dva"] == 450
        assert TURN_FRAMES["meshmamba"] == 450
        assert TURN_FRAMES["sal3d"] == 660


# ── minmax normalization ───────────────────────────────────────────────────────

class TestMinMaxNormalization:
    def test_normal_range_full_spectrum(self):
        values = np.linspace(0.0, 1.0, 256)
        rgb, pv_domain, stats = compute_rgb_colors(values, "face", colormap="jet", alpha=1.0)
        assert rgb.shape == (256, 3)
        assert rgb.dtype == np.uint8
        assert pv_domain == "cell"

    def test_vertex_domain_returns_point(self):
        values = np.array([0.0, 0.5, 1.0])
        _, pv_domain, _ = compute_rgb_colors(values, "vertex")
        assert pv_domain == "point"

    def test_constant_map_does_not_raise(self):
        values = np.ones(50) * 0.5
        rgb, _, _ = compute_rgb_colors(values, "face")
        assert rgb.shape == (50, 3)

    def test_alpha_zero_gives_gray(self):
        values = np.array([0.0, 1.0])
        rgb, _, _ = compute_rgb_colors(values, "face", alpha=0.0)
        # alpha=0 → pure gray (128, 128, 128)
        assert np.allclose(rgb, 128, atol=1)

    def test_output_clipped_uint8(self):
        values = np.array([0.0, 0.5, 1.0])
        rgb, _, _ = compute_rgb_colors(values, "face", alpha=1.0)
        assert rgb.min() >= 0
        assert rgb.max() <= 255

    def test_norm_stats_keys(self):
        values = np.linspace(2.0, 5.0, 100)
        _, _, stats = compute_rgb_colors(values, "face")
        assert "input_min" in stats
        assert "input_max" in stats
        assert "display_normalization" in stats

    def test_norm_stats_input_min_max(self):
        values = np.linspace(2.0, 5.0, 100)
        _, _, stats = compute_rgb_colors(values, "face")
        assert stats["input_min"] == pytest.approx(2.0)
        assert stats["input_max"] == pytest.approx(5.0)

    def test_norm_stats_display_normalization_value(self):
        values = np.linspace(0.0, 1.0, 50)
        _, _, stats = compute_rgb_colors(values, "face")
        assert stats["display_normalization"] == "minmax_per_map"

    def test_norm_stats_do_not_modify_input_values(self):
        values = np.array([1.0, 3.0, 5.0])
        orig = values.copy()
        compute_rgb_colors(values, "face")
        np.testing.assert_array_equal(values, orig)


# ── select_preview_indices ────────────────────────────────────────────────────

class TestSelectPreviewIndices:
    def test_100_frames_five_points(self):
        idxs = select_preview_indices(100)
        assert idxs[0] == 0
        assert idxs[-1] == 99
        assert len(idxs) == 5

    def test_one_frame(self):
        assert select_preview_indices(1) == [0]

    def test_two_frames_no_duplicates(self):
        idxs = select_preview_indices(2)
        assert len(idxs) == len(set(idxs))
        assert 0 in idxs
        assert 1 in idxs

    def test_zero_frames_empty(self):
        assert select_preview_indices(0) == []

    def test_sorted(self):
        idxs = select_preview_indices(200)
        assert idxs == sorted(idxs)

    def test_450_frames_covers_boundaries(self):
        idxs = select_preview_indices(450)
        assert idxs[0] == 0
        assert idxs[-1] == 449


# ── write_manifest_csv ────────────────────────────────────────────────────────

class TestWriteManifestCsv:
    def test_flat_fields_present(self, tmp_path):
        manifest = {"dataset": "3DVA", "model": "A380", "map_type": "gt"}
        p = tmp_path / "manifest.csv"
        write_manifest_csv(p, manifest)
        with p.open() as fh:
            row = next(_csv.DictReader(fh))
        assert row["dataset"] == "3DVA"
        assert row["model"] == "A380"

    def test_nested_dict_flattened_with_dot(self, tmp_path):
        manifest = {"render": {"fps": 30, "n_rendered_frames": 450}}
        p = tmp_path / "m.csv"
        write_manifest_csv(p, manifest)
        with p.open() as fh:
            row = next(_csv.DictReader(fh))
        assert row["render.fps"] == "30"
        assert row["render.n_rendered_frames"] == "450"

    def test_timing_contract_fields(self, tmp_path):
        manifest = {
            "timing_contract": {
                "name": "rc3_one_turn",
                "start_frame_idx": 0,
                "end_frame_idx": 450,
            }
        }
        p = tmp_path / "m.csv"
        write_manifest_csv(p, manifest)
        with p.open() as fh:
            row = next(_csv.DictReader(fh))
        assert row["timing_contract.name"] == "rc3_one_turn"
        assert row["timing_contract.start_frame_idx"] == "0"
        assert row["timing_contract.end_frame_idx"] == "450"

    def test_creates_file(self, tmp_path):
        p = tmp_path / "sub" / "manifest.csv"
        p.parent.mkdir()
        write_manifest_csv(p, {"x": 1})
        assert p.exists()


# ── GPU preflight ─────────────────────────────────────────────────────────────

class TestGpuPreflight:
    """Tests for probe_gpu_backend() and related constants.

    probe_gpu_backend() may attempt real nvidia-smi and VTK calls, so these
    tests only check the shape/contract of the result, not specific values.
    """

    def test_returns_required_keys(self):
        result = probe_gpu_backend()
        required = {
            "gpu_available", "gpu_name",
            "opengl_renderer", "opengl_vendor", "opengl_version",
            "pyvista_version", "vtk_version",
            "pyvista_backend", "offscreen_backend",
            "used_cpu_fallback",
        }
        assert required.issubset(result.keys())

    def test_gpu_available_is_bool(self):
        result = probe_gpu_backend()
        assert isinstance(result["gpu_available"], bool)

    def test_used_cpu_fallback_is_bool(self):
        result = probe_gpu_backend()
        assert isinstance(result["used_cpu_fallback"], bool)

    def test_opengl_renderer_is_str(self):
        result = probe_gpu_backend()
        assert isinstance(result["opengl_renderer"], str)
        assert len(result["opengl_renderer"]) > 0

    def test_cpu_fallback_set_when_llvmpipe(self):
        # Simulate result with llvmpipe renderer
        import unittest.mock as mock
        with mock.patch(
            "video_creation.heatmap_on_mesh_video.render_heatmap_video.subprocess.run",
            return_value=mock.Mock(returncode=1, stdout=""),
        ):
            with mock.patch(
                "video_creation.heatmap_on_mesh_video.render_heatmap_video.probe_gpu_backend",
                return_value={
                    "gpu_available": False, "gpu_name": "",
                    "opengl_renderer": "llvmpipe (LLVM 20.0, 256 bits)",
                    "opengl_vendor": "Mesa", "opengl_version": "4.5",
                    "pyvista_version": "0.48.4", "vtk_version": "9.6.2",
                    "pyvista_backend": "cpu_software",
                    "offscreen_backend": "vtk_offscreen",
                    "used_cpu_fallback": True,
                },
            ):
                from video_creation.heatmap_on_mesh_video.render_heatmap_video import probe_gpu_backend as pg
                r = pg()
                assert r["used_cpu_fallback"] is True
                assert r["pyvista_backend"] == "cpu_software"

    def test_cpu_renderer_patterns_include_llvmpipe(self):
        assert any("llvmpipe" in p for p in _CPU_RENDERER_PATTERNS)

    def test_cpu_renderer_patterns_include_softpipe(self):
        assert any("softpipe" in p for p in _CPU_RENDERER_PATTERNS)

    def test_cpu_fallback_max_frames_is_30(self):
        assert _CPU_FALLBACK_MAX_FRAMES == 30
