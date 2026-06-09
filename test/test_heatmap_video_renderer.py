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

from video_creation.heatmap_on_mesh_video.render_heatmap_video import (
    CROP_END_S,
    CROP_START_S,
    apply_frame_rotation,
    camera_from_placement,
    load_map,
    parse_obj,
    precompute_base_transform,
    write_manifest,
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
    def test_zero_returns_same_object(self):
        v = np.array([[1.0, 2.0, 3.0]])
        result = apply_frame_rotation(v, 0.0)
        assert result is v

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

    def test_model_location_added(self):
        v = np.array([[0.0, 0.0, 0.0]])
        placement = _make_placement(scale=1.0, location=[1.0, 2.0, 3.0])
        result = precompute_base_transform(v, placement, recenter=False, extra_rotate_x_deg=0.0)
        np.testing.assert_array_almost_equal(result[0], [1.0, 2.0, 3.0])

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
