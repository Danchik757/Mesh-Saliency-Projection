"""
Unit tests for validation/alignment_preview/check_alignment.py.

Only tests pure-logic functions (no ffmpeg, no server data required).
PIL is used for rasterize_silhouette but is available in the project env.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from validation.alignment_preview.check_alignment import (
    CROP_START,
    CROP_END,
    FPS,
    DATASET_CONFIGS,
    PREVIEW_K_17S,
    PREVIEW_K_24S,
    parse_obj,
    build_projection_matrix_from_fov,
    horizontal_to_vertical_fov_deg,
    resolve_projection_matrix,
    world_to_screen,
    _rotate_z,
    _rotate_x,
    _rotate_y,
    precompute_base_verts,
    apply_frame_transform,
    extract_edge_mask,
    overlay_edge_on_frame,
    estimate_background_rgb,
    extract_video_mask,
    compute_iou,
    _find_file_casefold,
    _normalise_lookup_name,
    _find_obj,
    _model_output_dir,
    write_manifest,
    write_summary_csv,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_obj(path: Path) -> None:
    """4 vertices, 2 triangles, all in Z=0 plane."""
    path.write_text(
        "v 0.0 0.0 0.0\n"
        "v 1.0 0.0 0.0\n"
        "v 0.0 1.0 0.0\n"
        "v 1.0 1.0 0.0\n"
        "f 1 2 3\n"
        "f 2 4 3\n"
    )


def _identity_camera_data(fov_deg: float = 60.0, aspect: float = 16 / 9) -> dict:
    """Minimal placement-JSON camera_data dict with identity view matrix."""
    return {
        "video_info": {
            "width": 1920, "height": 1080,
            "fps": 30.0, "aspect_ratio": aspect,
        },
        "camera_static": {
            "view_matrix": list(np.eye(4).ravel()),
            "projection_matrix": list(np.eye(4).ravel()),
            "fov_degrees": fov_deg,
            "clip_start": 0.1,
            "clip_end": 100.0,
        },
        "model_static": {
            "scale": [1.0, 1.0, 1.0],
            "location": [0.0, 0.0, 0.0],
        },
        "frames": [
            {"frame": i, "timestamp": i / 30.0, "rotation_z_radians": 0.0, "rotation_z_degrees": 0.0}
            for i in range(720)
        ],
    }


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_crop_start(self):
        assert CROP_START == round(1.8 * 30)  # = 54

    def test_crop_end(self):
        assert CROP_END == round(0.2 * 30)  # = 6

    def test_fps(self):
        assert FPS == 30

    def test_preview_k_17s_count(self):
        assert len(PREVIEW_K_17S) == 5

    def test_preview_k_24s_count(self):
        assert len(PREVIEW_K_24S) == 5

    def test_preview_k_17s_placement(self):
        for k in PREVIEW_K_17S:
            assert 0 <= k <= 449, f"k={k} out of [0,449]"

    def test_preview_k_24s_placement(self):
        for k in PREVIEW_K_24S:
            assert 0 <= k <= 659, f"k={k} out of [0,659]"

    def test_dataset_keys(self):
        assert set(DATASET_CONFIGS.keys()) == {"3dva", "meshmamba", "sal3d"}

    def test_dataset_configs_transform_orders(self):
        assert DATASET_CONFIGS["3dva"]["transform_order"] == "3dva"
        assert DATASET_CONFIGS["meshmamba"]["transform_order"] == "blender_rig"
        assert DATASET_CONFIGS["sal3d"]["transform_order"] == "blender_rig"

    def test_meshmamba_sal3d_extra_rx(self):
        assert DATASET_CONFIGS["meshmamba"]["extra_rotate_x_deg"] == 90.0
        assert DATASET_CONFIGS["sal3d"]["extra_rotate_x_deg"] == 90.0

    def test_3dva_no_extra_rx(self):
        assert DATASET_CONFIGS["3dva"]["extra_rotate_x_deg"] == 0.0

    def test_sal3d_uses_24s_frames(self):
        assert DATASET_CONFIGS["sal3d"]["preview_k"] is PREVIEW_K_24S

    def test_17s_datasets_use_17s_frames(self):
        assert DATASET_CONFIGS["3dva"]["preview_k"] is PREVIEW_K_17S
        assert DATASET_CONFIGS["meshmamba"]["preview_k"] is PREVIEW_K_17S


# ---------------------------------------------------------------------------
# parse_obj
# ---------------------------------------------------------------------------

class TestParseObj:
    def test_basic(self, tmp_path):
        obj = tmp_path / "t.obj"
        _minimal_obj(obj)
        verts, faces = parse_obj(obj)
        assert verts.shape == (4, 3)
        assert faces.shape == (2, 3)
        assert verts.dtype == np.float64
        assert faces.dtype == np.int32

    def test_vertex_values(self, tmp_path):
        obj = tmp_path / "t.obj"
        _minimal_obj(obj)
        verts, _ = parse_obj(obj)
        np.testing.assert_allclose(verts[0], [0.0, 0.0, 0.0])
        np.testing.assert_allclose(verts[1], [1.0, 0.0, 0.0])

    def test_face_zero_indexed(self, tmp_path):
        obj = tmp_path / "t.obj"
        _minimal_obj(obj)
        _, faces = parse_obj(obj)
        assert faces[0, 0] == 0   # OBJ 1-based → 0-based
        assert faces[1, 0] == 1

    def test_face_with_slash_notation(self, tmp_path):
        obj = tmp_path / "slash.obj"
        obj.write_text(
            "v 0 0 0\nv 1 0 0\nv 0 1 0\n"
            "f 1/1/1 2/2/2 3/3/3\n"
        )
        _, faces = parse_obj(obj)
        assert faces.shape == (1, 3)
        assert list(faces[0]) == [0, 1, 2]

    def test_ignores_non_geometry_lines(self, tmp_path):
        obj = tmp_path / "extra.obj"
        obj.write_text(
            "# comment\n"
            "mtllib foo.mtl\n"
            "vt 0.0 0.0\n"
            "vn 0.0 0.0 1.0\n"
            "v 0 0 0\nv 1 0 0\nv 0 1 0\n"
            "usemtl mat\n"
            "f 1 2 3\n"
        )
        verts, faces = parse_obj(obj)
        assert verts.shape == (3, 3)
        assert faces.shape == (1, 3)


# ---------------------------------------------------------------------------
# build_projection_matrix_from_fov
# ---------------------------------------------------------------------------

class TestBuildProjectionMatrix:
    def test_shape(self):
        p = build_projection_matrix_from_fov(60.0, 16 / 9, 0.1, 100.0)
        assert p.shape == (4, 4)

    def test_last_row(self):
        p = build_projection_matrix_from_fov(60.0, 16 / 9, 0.1, 100.0)
        np.testing.assert_allclose(p[3], [0, 0, -1, 0])

    def test_f_value(self):
        fov = 60.0
        aspect = 16 / 9
        f = 1.0 / math.tan(math.radians(fov) * 0.5)
        p = build_projection_matrix_from_fov(fov, aspect, 0.1, 100.0)
        assert abs(p[1, 1] - f) < 1e-10
        assert abs(p[0, 0] - f / aspect) < 1e-10

    def test_narrower_fov_larger_f(self):
        p30 = build_projection_matrix_from_fov(30.0, 1.0, 0.1, 100.0)
        p90 = build_projection_matrix_from_fov(90.0, 1.0, 0.1, 100.0)
        assert p30[1, 1] > p90[1, 1]


# ---------------------------------------------------------------------------
# horizontal_to_vertical_fov_deg
# ---------------------------------------------------------------------------

class TestHorizontalToVerticalFov:
    def test_known_value(self):
        # fov_h=60, aspect=16/9  →  ~35.98
        vfov = horizontal_to_vertical_fov_deg(60.0, 16 / 9)
        assert abs(vfov - 35.9836) < 0.001

    def test_square_aspect_equals_input(self):
        vfov = horizontal_to_vertical_fov_deg(60.0, 1.0)
        assert abs(vfov - 60.0) < 1e-10

    def test_wider_aspect_smaller_vfov(self):
        vfov_wide = horizontal_to_vertical_fov_deg(60.0, 16 / 9)
        vfov_narrow = horizontal_to_vertical_fov_deg(60.0, 4 / 3)
        assert vfov_wide < vfov_narrow


# ---------------------------------------------------------------------------
# resolve_projection_matrix
# ---------------------------------------------------------------------------

class TestResolveProjectionMatrix:
    def _camera_data(self, fov_deg=60.0, aspect=16/9):
        return _identity_camera_data(fov_deg, aspect)

    def test_horizontal_to_vertical_returns_matrix(self):
        proj, info = resolve_projection_matrix(self._camera_data(), "horizontal_to_vertical")
        assert proj.shape == (4, 4)
        assert info["fov_mode"] == "horizontal_to_vertical"

    def test_horizontal_to_vertical_records_vfov(self):
        _, info = resolve_projection_matrix(self._camera_data(60.0), "horizontal_to_vertical")
        assert abs(info["effective_vfov_deg"] - 35.98) < 0.01

    def test_json_mode_uses_json_matrix(self):
        data = self._camera_data()
        data["camera_static"]["projection_matrix"] = list(np.eye(4).ravel())
        proj, info = resolve_projection_matrix(data, "json")
        np.testing.assert_allclose(proj, np.eye(4))
        assert info["fov_mode"] == "json"

    def test_unknown_fov_mode_raises(self):
        with pytest.raises(ValueError, match="Unknown fov_mode"):
            resolve_projection_matrix(self._camera_data(), "bad_mode")


# ---------------------------------------------------------------------------
# world_to_screen
# ---------------------------------------------------------------------------

class TestWorldToScreen:
    def _make_matrices(self, fov_deg=60.0, aspect=16/9, clip_start=0.1, clip_end=100.0):
        vfov = horizontal_to_vertical_fov_deg(fov_deg, aspect)
        proj = build_projection_matrix_from_fov(vfov, aspect, clip_start, clip_end)
        view = np.eye(4, dtype=np.float64)  # identity (camera at origin, looking -Z)
        return view, proj

    def test_center_point_at_screen_half(self):
        view, proj = self._make_matrices()
        # Point on camera Z-axis, in front (Z negative in camera space with identity view)
        # With identity view, camera looks down -Z, so point at (0,0,-5) is in front.
        pts = np.array([[0.0, 0.0, -5.0]])
        screen_xy, w_clip = world_to_screen(pts, view, proj)
        assert abs(screen_xy[0, 0] - 0.5) < 1e-6, "center X should be 0.5"
        assert abs(screen_xy[0, 1] - 0.5) < 1e-6, "center Y should be 0.5"

    def test_positive_w_clip_in_front(self):
        view, proj = self._make_matrices()
        pts = np.array([[0.0, 0.0, -1.0]])
        _, w_clip = world_to_screen(pts, view, proj)
        assert w_clip[0] > 0

    def test_negative_w_clip_behind_camera(self):
        view, proj = self._make_matrices()
        # Point behind camera = positive Z with identity view (looking -Z)
        pts = np.array([[0.0, 0.0, 1.0]])
        _, w_clip = world_to_screen(pts, view, proj)
        assert w_clip[0] < 0

    def test_output_shapes(self):
        view, proj = self._make_matrices()
        pts = np.random.rand(10, 3)
        pts[:, 2] -= 2.0  # move in front
        screen_xy, w_clip = world_to_screen(pts, view, proj)
        assert screen_xy.shape == (10, 2)
        assert w_clip.shape == (10,)


# ---------------------------------------------------------------------------
# Rotation functions
# ---------------------------------------------------------------------------

class TestRotations:
    def test_rotate_z_90(self):
        pts = np.array([[1.0, 0.0, 0.0]])
        result = _rotate_z(pts, math.pi / 2)
        np.testing.assert_allclose(result[0], [0.0, 1.0, 0.0], atol=1e-12)

    def test_rotate_z_zero_noop(self):
        pts = np.array([[1.0, 2.0, 3.0]])
        result = _rotate_z(pts, 0.0)
        np.testing.assert_allclose(result, pts)

    def test_rotate_x_90(self):
        pts = np.array([[0.0, 1.0, 0.0]])
        result = _rotate_x(pts, 90.0)
        np.testing.assert_allclose(result[0], [0.0, 0.0, 1.0], atol=1e-12)

    def test_rotate_x_zero_noop(self):
        pts = np.array([[1.0, 2.0, 3.0]])
        result = _rotate_x(pts, 0.0)
        np.testing.assert_allclose(result, pts)

    def test_rotate_y_90(self):
        pts = np.array([[1.0, 0.0, 0.0]])
        result = _rotate_y(pts, 90.0)
        np.testing.assert_allclose(result[0], [0.0, 0.0, -1.0], atol=1e-12)

    def test_rotate_y_zero_noop(self):
        pts = np.array([[1.0, 2.0, 3.0]])
        result = _rotate_y(pts, 0.0)
        np.testing.assert_allclose(result, pts)

    def test_rotate_z_360_identity(self):
        pts = np.array([[1.0, 2.0, 3.0]])
        result = _rotate_z(pts, 2 * math.pi)
        np.testing.assert_allclose(result, pts, atol=1e-12)

    def test_rotate_z_does_not_change_z(self):
        pts = np.array([[1.0, 2.0, 5.0]])
        result = _rotate_z(pts, 1.23)
        np.testing.assert_allclose(result[:, 2], pts[:, 2])


# ---------------------------------------------------------------------------
# precompute_base_verts
# ---------------------------------------------------------------------------

class TestPrecomputeBaseVerts:
    def _simple_verts(self):
        return np.array([
            [0.0, 0.0, 0.0],
            [2.0, 0.0, 0.0],
            [0.0, 2.0, 0.0],
            [2.0, 2.0, 0.0],
        ], dtype=np.float64)

    def test_3dva_recenter(self):
        verts = self._simple_verts()  # bbox center = [1, 1, 0]
        base, bbox_center = precompute_base_verts(verts, recenter=True,
                                                   base_rotate_z_deg=0.0,
                                                   transform_order="3dva")
        np.testing.assert_allclose(bbox_center, [1.0, 1.0, 0.0])
        np.testing.assert_allclose(base.mean(axis=0), [0.0, 0.0, 0.0], atol=1e-12)

    def test_blender_rig_recenter(self):
        verts = self._simple_verts()
        base, bbox_center = precompute_base_verts(verts, recenter=True,
                                                   base_rotate_z_deg=0.0,
                                                   transform_order="blender_rig")
        np.testing.assert_allclose(bbox_center, [1.0, 1.0, 0.0])
        np.testing.assert_allclose(base.mean(axis=0), [0.0, 0.0, 0.0], atol=1e-12)

    def test_no_recenter_preserves_coords(self):
        verts = self._simple_verts()
        base, _ = precompute_base_verts(verts, recenter=False,
                                         base_rotate_z_deg=0.0,
                                         transform_order="blender_rig")
        np.testing.assert_allclose(base, verts)

    def test_unknown_order_raises(self):
        verts = self._simple_verts()
        with pytest.raises(ValueError, match="Unknown transform_order"):
            precompute_base_verts(verts, recenter=True, base_rotate_z_deg=0.0,
                                   transform_order="bad_order")

    def test_bbox_center_returned(self):
        verts = np.array([[0.0, 0.0, 0.0], [4.0, 6.0, 2.0]], dtype=np.float64)
        _, bbox_center = precompute_base_verts(verts, recenter=False,
                                                base_rotate_z_deg=0.0,
                                                transform_order="blender_rig")
        np.testing.assert_allclose(bbox_center, [2.0, 3.0, 1.0])


# ---------------------------------------------------------------------------
# apply_frame_transform
# ---------------------------------------------------------------------------

class TestApplyFrameTransform:
    def _base_verts(self):
        return np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=np.float64)

    def _camera_data(self, scale=1.0, location=(0.0, 0.0, 0.0)):
        return {
            "model_static": {
                "scale": [scale, scale, scale],
                "location": list(location),
            }
        }

    def test_identity_transform_3dva(self):
        v = self._base_verts()
        result = apply_frame_transform(v, self._camera_data(), 0.0, 0.0, 0.0, 0.0, "3dva")
        np.testing.assert_allclose(result, v, atol=1e-12)

    def test_identity_transform_blender_rig(self):
        v = self._base_verts()
        result = apply_frame_transform(v, self._camera_data(), 0.0, 0.0, 0.0, 0.0, "blender_rig")
        np.testing.assert_allclose(result, v, atol=1e-12)

    def test_scale_applied(self):
        v = np.array([[1.0, 0.0, 0.0]], dtype=np.float64)
        result = apply_frame_transform(v, self._camera_data(scale=2.0), 0.0, 0.0, 0.0, 0.0, "blender_rig")
        np.testing.assert_allclose(result[0, 0], 2.0, atol=1e-12)

    def test_translation_applied(self):
        v = np.array([[0.0, 0.0, 0.0]], dtype=np.float64)
        result = apply_frame_transform(v, self._camera_data(location=(3.0, 4.0, 5.0)),
                                        0.0, 0.0, 0.0, 0.0, "blender_rig")
        np.testing.assert_allclose(result[0], [3.0, 4.0, 5.0], atol=1e-12)

    def test_rx_90_blender_rig(self):
        # +Y → +Z under 90° X rotation
        v = np.array([[0.0, 1.0, 0.0]], dtype=np.float64)
        result = apply_frame_transform(v, self._camera_data(), 0.0, 0.0, 90.0, 0.0, "blender_rig")
        np.testing.assert_allclose(result[0], [0.0, 0.0, 1.0], atol=1e-12)

    def test_frame_rz_applied(self):
        v = np.array([[1.0, 0.0, 0.0]], dtype=np.float64)
        result = apply_frame_transform(v, self._camera_data(), math.pi / 2, 0.0, 0.0, 0.0, "3dva")
        np.testing.assert_allclose(result[0, :2], [0.0, 1.0], atol=1e-12)

    def test_unknown_order_raises(self):
        v = self._base_verts()
        with pytest.raises(ValueError, match="Unknown transform_order"):
            apply_frame_transform(v, self._camera_data(), 0.0, 0.0, 0.0, 0.0, "bad")

    def test_3dva_and_blender_rig_identical_for_zero_extra_rx(self):
        """When extra_rx=0 and base_rz=0, both orders must agree."""
        v = np.array([[1.0, 0.5, 0.0]], dtype=np.float64)
        rz = 0.7
        r3dva = apply_frame_transform(v, self._camera_data(), rz, 0.0, 0.0, 0.0, "3dva")
        rblend = apply_frame_transform(v, self._camera_data(), rz, 0.0, 0.0, 0.0, "blender_rig")
        np.testing.assert_allclose(r3dva, rblend, atol=1e-12)


# ---------------------------------------------------------------------------
# extract_edge_mask
# ---------------------------------------------------------------------------

class TestExtractEdgeMask:
    def _filled_rect(self, h, w, x0, y0, x1, y1):
        m = np.zeros((h, w), dtype=bool)
        m[y0:y1, x0:x1] = True
        return m

    def test_edge_contains_boundary(self):
        m = self._filled_rect(50, 50, 10, 10, 40, 40)
        edge = extract_edge_mask(m)
        assert bool(edge[10, 10])
        assert bool(edge[10, 39])

    def test_interior_not_in_edge(self):
        m = self._filled_rect(50, 50, 5, 5, 45, 45)
        edge = extract_edge_mask(m)
        assert not bool(edge[25, 25])

    def test_all_false_mask(self):
        m = np.zeros((20, 20), dtype=bool)
        edge = extract_edge_mask(m)
        assert not edge.any()

    def test_edge_subset_of_silhouette(self):
        m = self._filled_rect(30, 30, 5, 5, 25, 25)
        edge = extract_edge_mask(m)
        assert (edge & ~m).sum() == 0


# ---------------------------------------------------------------------------
# overlay_edge_on_frame
# ---------------------------------------------------------------------------

class TestOverlayEdgeOnFrame:
    def test_edge_pixels_coloured(self):
        frame = np.zeros((10, 10, 3), dtype=np.uint8)
        edge = np.zeros((10, 10), dtype=bool)
        edge[5, 5] = True
        result = overlay_edge_on_frame(frame, edge, color=(0, 255, 0))
        np.testing.assert_array_equal(result[5, 5], [0, 255, 0])

    def test_non_edge_pixels_unchanged(self):
        frame = np.full((10, 10, 3), 128, dtype=np.uint8)
        edge = np.zeros((10, 10), dtype=bool)
        edge[0, 0] = True
        result = overlay_edge_on_frame(frame, edge, color=(255, 0, 0))
        np.testing.assert_array_equal(result[5, 5], [128, 128, 128])

    def test_input_frame_not_mutated(self):
        frame = np.full((10, 10, 3), 50, dtype=np.uint8)
        edge = np.ones((10, 10), dtype=bool)
        _ = overlay_edge_on_frame(frame, edge, color=(1, 2, 3))
        assert frame[5, 5, 0] == 50


# ---------------------------------------------------------------------------
# estimate_background_rgb / extract_video_mask
# ---------------------------------------------------------------------------

class TestBackgroundSubtraction:
    def test_uniform_background_estimated_correctly(self):
        img = np.full((100, 100, 3), 200, dtype=np.uint8)
        bg = estimate_background_rgb(img)
        np.testing.assert_allclose(bg, [200, 200, 200], atol=1.0)

    def test_foreground_mask_excludes_background(self):
        img = np.full((100, 100, 3), 200, dtype=np.uint8)
        # Add a bright object in the centre
        img[30:70, 30:70] = 50
        mask = extract_video_mask(img, threshold=25.0)
        assert mask[50, 50]       # interior of object
        assert not mask[10, 10]   # background corner

    def test_uniform_image_yields_empty_mask(self):
        img = np.full((100, 100, 3), 180, dtype=np.uint8)
        mask = extract_video_mask(img, threshold=25.0)
        assert not mask.any()

    def test_output_is_bool(self):
        img = np.full((40, 40, 3), 100, dtype=np.uint8)
        mask = extract_video_mask(img)
        assert mask.dtype == bool


# ---------------------------------------------------------------------------
# compute_iou
# ---------------------------------------------------------------------------

class TestComputeIou:
    def test_identical_masks_iou_one(self):
        m = np.array([[True, False], [False, True]])
        assert compute_iou(m, m) == 1.0

    def test_disjoint_masks_iou_zero(self):
        a = np.array([[True, False]])
        b = np.array([[False, True]])
        assert compute_iou(a, b) == 0.0

    def test_partial_overlap(self):
        a = np.array([[True, True, False]])
        b = np.array([[False, True, True]])
        iou = compute_iou(a, b)
        assert abs(iou - 1 / 3) < 1e-9

    def test_empty_union_returns_zero(self):
        a = np.zeros((5, 5), dtype=bool)
        b = np.zeros((5, 5), dtype=bool)
        assert compute_iou(a, b) == 0.0

    def test_returns_float(self):
        m = np.ones((3, 3), dtype=bool)
        assert isinstance(compute_iou(m, m), float)


# ---------------------------------------------------------------------------
# _find_file_casefold
# ---------------------------------------------------------------------------

class TestFindFileCasefold:
    def test_exact_match(self, tmp_path):
        (tmp_path / "Bunny.obj").write_text("")
        result = _find_file_casefold(tmp_path, "Bunny", ".obj")
        assert result is not None
        assert result.name == "Bunny.obj"

    def test_lowercase_stem_finds_uppercase_file(self, tmp_path):
        (tmp_path / "BUNNY.OBJ").write_text("")
        result = _find_file_casefold(tmp_path, "bunny", ".obj")
        assert result is not None

    def test_returns_none_for_missing(self, tmp_path):
        result = _find_file_casefold(tmp_path, "missing", ".obj")
        assert result is None

    def test_returns_none_for_missing_dir(self, tmp_path):
        result = _find_file_casefold(tmp_path / "nonexistent", "x", ".obj")
        assert result is None

    def test_wrong_suffix_not_returned(self, tmp_path):
        (tmp_path / "bunny.txt").write_text("")
        result = _find_file_casefold(tmp_path, "bunny", ".obj")
        assert result is None


# ---------------------------------------------------------------------------
# _model_output_dir
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# _normalise_lookup_name
# ---------------------------------------------------------------------------

class TestNormaliseLookupName:
    def test_strips_underscores(self):
        assert _normalise_lookup_name("Starfruit_L3") == "starfruitl3"

    def test_strips_dashes(self):
        assert _normalise_lookup_name("Starfruit-L3") == "starfruitl3"

    def test_lowercases(self):
        assert _normalise_lookup_name("PEAR") == "pear"

    def test_mixed_separators(self):
        assert _normalise_lookup_name("Pear_L3") == _normalise_lookup_name("pear-l3")

    def test_no_separator_unchanged(self):
        assert _normalise_lookup_name("bunny") == "bunny"


# ---------------------------------------------------------------------------
# _find_obj — nested / fuzzy MeshMamba layout
# ---------------------------------------------------------------------------

class TestFindObj:
    def test_exact_flat(self, tmp_path):
        (tmp_path / "bunny.obj").write_text("")
        assert _find_obj(tmp_path, "bunny") == tmp_path / "bunny.obj"

    def test_casefold_flat(self, tmp_path):
        (tmp_path / "BUNNY.OBJ").write_text("")
        result = _find_obj(tmp_path, "bunny")
        assert result is not None and result.name.upper() == "BUNNY.OBJ"

    def test_nested_exact_name(self, tmp_path):
        # Starfruit_L3/Starfruit_L3.obj
        sub = tmp_path / "Starfruit_L3"
        sub.mkdir()
        (sub / "Starfruit_L3.obj").write_text("")
        assert _find_obj(tmp_path, "Starfruit_L3") == sub / "Starfruit_L3.obj"

    def test_nested_dash_variant(self, tmp_path):
        # Starfruit_L3/Starfruit-L3.obj  (dash, not underscore)
        sub = tmp_path / "Starfruit_L3"
        sub.mkdir()
        (sub / "Starfruit-L3.obj").write_text("")
        result = _find_obj(tmp_path, "Starfruit_L3")
        assert result is not None
        assert result.name == "Starfruit-L3.obj"

    def test_nested_short_name(self, tmp_path):
        # Pear_L3/Pear.obj  (stem shorter than model name)
        sub = tmp_path / "Pear_L3"
        sub.mkdir()
        (sub / "Pear.obj").write_text("")
        # "pear" != "pearl3", so it won't match normalised — but it IS the only file
        result = _find_obj(tmp_path, "Pear_L3")
        assert result is not None
        assert result.name == "Pear.obj"

    def test_nested_single_obj_fallback(self, tmp_path):
        # Any single .obj in the subdir is returned if nothing else matches
        sub = tmp_path / "MyModel_v2"
        sub.mkdir()
        (sub / "totally_different_name.obj").write_text("")
        result = _find_obj(tmp_path, "MyModel_v2")
        assert result is not None

    def test_returns_none_for_missing(self, tmp_path):
        assert _find_obj(tmp_path, "ghost") is None

    def test_returns_none_empty_subdir(self, tmp_path):
        (tmp_path / "MyModel").mkdir()
        assert _find_obj(tmp_path, "MyModel") is None


# ---------------------------------------------------------------------------
class TestModelOutputDir:
    def test_with_texture_type(self):
        p = _model_output_dir(Path("/out"), "meshmamba", "non_texture", "Starfruit_L3")
        assert p == Path("/out/MESHMAMBA_non_texture/Starfruit_L3")

    def test_without_texture_type(self):
        p = _model_output_dir(Path("/out"), "3dva", None, "bunny")
        assert p == Path("/out/3DVA/bunny")

    def test_sal3d_path(self):
        p = _model_output_dir(Path("/out"), "sal3d", None, "MaxPlanck")
        assert p == Path("/out/SAL3D/MaxPlanck")


# ---------------------------------------------------------------------------
# write_manifest / write_summary_csv
# ---------------------------------------------------------------------------

class TestWriteOutputs:
    def _sample_rows(self):
        return [
            {"dataset": "3dva", "texture_type": "", "model": "bunny",
             "gaze_k": 0, "placement_idx": 54, "status": "ok",
             "iou": 0.85, "iou_reliable": True, "iou_note": "bg_subtraction",
             "rendered_pixels": 50000},
        ]

    def test_write_manifest_creates_json(self, tmp_path):
        p = write_manifest(self._sample_rows(), tmp_path)
        assert p.exists()
        data = json.loads(p.read_text())
        assert isinstance(data, list)
        assert data[0]["model"] == "bunny"

    def test_write_summary_csv_creates_file(self, tmp_path):
        p = write_summary_csv(self._sample_rows(), tmp_path)
        assert p.exists()
        text = p.read_text()
        assert "dataset" in text
        assert "bunny" in text

    def test_write_manifest_nested_output_dir(self, tmp_path):
        nested = tmp_path / "a" / "b"
        p = write_manifest([], nested)
        assert p.exists()

    def test_write_summary_csv_header(self, tmp_path):
        p = write_summary_csv(self._sample_rows(), tmp_path)
        first_line = p.read_text().splitlines()[0]
        assert "dataset" in first_line
        assert "iou" in first_line


# ---------------------------------------------------------------------------
# rasterize_silhouette (PIL-dependent — guarded)
# ---------------------------------------------------------------------------

try:
    from PIL import Image as _PIL_Image  # type: ignore
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


@pytest.mark.skipif(not _PIL_AVAILABLE, reason="Pillow not installed")
class TestRasterizeSilhouette:
    def test_import_works(self):
        from validation.alignment_preview.check_alignment import rasterize_silhouette
        assert callable(rasterize_silhouette)

    def test_single_front_facing_triangle(self):
        from validation.alignment_preview.check_alignment import rasterize_silhouette
        # A large triangle in front of an identity-view camera
        world_verts = np.array([
            [-0.5, -0.5, -2.0],
            [ 0.5, -0.5, -2.0],
            [ 0.0,  0.5, -2.0],
        ], dtype=np.float64)
        faces = np.array([[0, 1, 2]], dtype=np.int32)
        view = np.eye(4, dtype=np.float64)
        vfov = horizontal_to_vertical_fov_deg(60.0, 16 / 9)
        proj = build_projection_matrix_from_fov(vfov, 16 / 9, 0.1, 100.0)
        mask = rasterize_silhouette(world_verts, faces, view, proj, 1920, 1080)
        assert mask.dtype == bool
        assert mask.shape == (1080, 1920)
        assert mask.any(), "Expected at least some filled pixels"

    def test_behind_camera_yields_empty(self):
        from validation.alignment_preview.check_alignment import rasterize_silhouette
        # Triangle behind camera (positive Z with identity view looking -Z)
        world_verts = np.array([
            [-0.5, -0.5, 2.0],
            [ 0.5, -0.5, 2.0],
            [ 0.0,  0.5, 2.0],
        ], dtype=np.float64)
        faces = np.array([[0, 1, 2]], dtype=np.int32)
        view = np.eye(4, dtype=np.float64)
        vfov = horizontal_to_vertical_fov_deg(60.0, 16 / 9)
        proj = build_projection_matrix_from_fov(vfov, 16 / 9, 0.1, 100.0)
        mask = rasterize_silhouette(world_verts, faces, view, proj, 1920, 1080)
        assert not mask.any(), "Expected empty mask for behind-camera triangle"
