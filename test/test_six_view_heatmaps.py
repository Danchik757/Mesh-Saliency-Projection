"""
Unit tests for visualization/heatmap_six_view/render_six_view_heatmaps.py.

Only tests pure-logic functions (no pyvista or rendering required).
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from visualization.heatmap_six_view.render_six_view_heatmaps import (
    _error_row,
    _find_file_casefold,
    _rel,
    discover_models,
    load_and_prepare_map,
    parse_obj,
    resolve_map_paths,
    resolve_obj_path,
    write_manifest,
    write_summary_csv,
    SAL3D_SCREEN_TAG,
    SAL3D_CONE_TAG,
    MM_SCREEN_TAG,
    MM_CONE_TAG,
    THREE_DVA_SCREEN_TAG,
    THREE_DVA_CONE_TAG,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _write_float_file(path: Path, values: np.ndarray) -> None:
    np.savetxt(path, values, fmt="%.10f")


def _minimal_obj(path: Path) -> None:
    """Write a minimal two-triangle OBJ with 4 vertices."""
    path.write_text(
        "v 0.0 0.0 0.0\n"
        "v 1.0 0.0 0.0\n"
        "v 0.0 1.0 0.0\n"
        "v 1.0 1.0 0.0\n"
        "f 1 2 3\n"
        "f 2 4 3\n"
    )


# ---------------------------------------------------------------------------
# parse_obj
# ---------------------------------------------------------------------------

class TestParseObj:
    def test_vertices_and_faces(self, tmp_path):
        p = tmp_path / "cube.obj"
        _minimal_obj(p)
        verts, faces = parse_obj(p)
        assert verts.shape == (4, 3)
        assert faces.shape == (2, 3)

    def test_vertex_indices_zero_based(self, tmp_path):
        p = tmp_path / "tri.obj"
        p.write_text("v 1.0 0.0 0.0\nv 0.0 1.0 0.0\nv 0.0 0.0 1.0\nf 1 2 3\n")
        _, faces = parse_obj(p)
        assert list(faces[0]) == [0, 1, 2]

    def test_slash_notation(self, tmp_path):
        """f v/vt/vn notation should parse correctly."""
        p = tmp_path / "slash.obj"
        p.write_text(
            "v 0 0 0\nv 1 0 0\nv 0 1 0\n"
            "f 1/1/1 2/2/2 3/3/3\n"
        )
        _, faces = parse_obj(p)
        assert list(faces[0]) == [0, 1, 2]

    def test_dtypes(self, tmp_path):
        p = tmp_path / "dt.obj"
        _minimal_obj(p)
        verts, faces = parse_obj(p)
        assert verts.dtype == np.float64
        assert faces.dtype == np.int32


# ---------------------------------------------------------------------------
# load_and_prepare_map
# ---------------------------------------------------------------------------

class TestLoadAndPrepareMap:
    def _simple_faces(self, tmp_path, n_faces):
        """Write and return path to a n_faces per-face map [0, n_faces)."""
        p = tmp_path / "map.txt"
        _write_float_file(p, np.arange(n_faces, dtype=float))
        return p

    def test_face_domain_detected(self, tmp_path):
        n_f = 6
        p = self._simple_faces(tmp_path, n_f)
        faces = np.zeros((n_f, 3), dtype=np.int32)
        _, _, _, domain, _, _, _ = load_and_prepare_map(p, n_verts=10, n_faces=n_f,
                                                         faces=faces)
        assert domain == "face"

    def test_vertex_domain_detected(self, tmp_path):
        n_v = 8
        n_f = 4
        p = tmp_path / "map.txt"
        _write_float_file(p, np.ones(n_v))
        faces = np.zeros((n_f, 3), dtype=np.int32)
        _, _, _, domain, _, _, _ = load_and_prepare_map(p, n_verts=n_v, n_faces=n_f,
                                                         faces=faces)
        assert domain == "vertex"

    def test_length_mismatch_raises(self, tmp_path):
        p = tmp_path / "map.txt"
        _write_float_file(p, np.ones(7))
        faces = np.zeros((4, 3), dtype=np.int32)
        with pytest.raises(ValueError, match="matches neither"):
            load_and_prepare_map(p, n_verts=8, n_faces=6, faces=faces)

    def test_normalised_range_01(self, tmp_path):
        n_f = 5
        vals = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
        p = tmp_path / "map.txt"
        _write_float_file(p, vals)
        faces = np.zeros((n_f, 3), dtype=np.int32)
        vals01, vmin, vmax, _, _, _, _ = load_and_prepare_map(
            p, n_verts=10, n_faces=n_f, faces=faces
        )
        assert float(vals01.min()) == pytest.approx(0.0)
        assert float(vals01.max()) == pytest.approx(1.0)
        assert vmin == pytest.approx(0.0)
        assert vmax == pytest.approx(1.0)

    def test_n_map_elements_face_domain(self, tmp_path):
        n_f = 5
        p = self._simple_faces(tmp_path, n_f)
        faces = np.zeros((n_f, 3), dtype=np.int32)
        _, _, _, domain, n_map_elements, _, _ = load_and_prepare_map(
            p, n_verts=10, n_faces=n_f, faces=faces
        )
        assert domain == "face"
        assert n_map_elements == n_f

    def test_n_map_elements_vertex_domain(self, tmp_path):
        n_v = 8
        n_f = 4
        p = tmp_path / "map.txt"
        _write_float_file(p, np.ones(n_v))
        faces = np.zeros((n_f, 3), dtype=np.int32)
        _, _, _, domain, n_map_elements, _, _ = load_and_prepare_map(
            p, n_verts=n_v, n_faces=n_f, faces=faces
        )
        assert domain == "vertex"
        assert n_map_elements == n_v

    def test_constant_map_all_zero(self, tmp_path):
        n_f = 4
        p = tmp_path / "map.txt"
        _write_float_file(p, np.full(n_f, 0.5))
        faces = np.zeros((n_f, 3), dtype=np.int32)
        vals01, _, _, _, _, constant_map, warning = load_and_prepare_map(
            p, n_verts=10, n_faces=n_f, faces=faces
        )
        assert constant_map is True
        assert np.all(vals01 == 0.0)
        assert warning is not None and "Constant" in warning

    def test_nan_replaced_with_zero(self, tmp_path):
        n_f = 3
        p = tmp_path / "map.txt"
        np.savetxt(p, [float("nan"), 0.5, 1.0], fmt="%.10f")
        faces = np.zeros((n_f, 3), dtype=np.int32)
        vals01, _, _, _, _, _, _ = load_and_prepare_map(
            p, n_verts=10, n_faces=n_f, faces=faces
        )
        assert np.all(np.isfinite(vals01))

    def test_vertex_to_face_mean(self, tmp_path):
        """Per-vertex values averaged over each face's three vertices."""
        # Two-triangle mesh sharing no vertices between faces
        verts_vals = np.array([0.0, 1.0, 0.0, 0.0, 1.0, 0.0])
        faces = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int32)
        p = tmp_path / "vmap.txt"
        _write_float_file(p, verts_vals)
        # Face 0: mean(0, 1, 0) = 1/3; Face 1: mean(0, 1, 0) = 1/3
        vals01, vmin, vmax, domain, _, _, _ = load_and_prepare_map(
            p, n_verts=6, n_faces=2, faces=faces
        )
        assert domain == "vertex"
        # Both faces have the same mean → constant map
        assert vmin == pytest.approx(vmax, abs=1e-9)

    def test_output_dtype_float32(self, tmp_path):
        n_f = 3
        p = tmp_path / "map.txt"
        _write_float_file(p, np.array([0.1, 0.5, 0.9]))
        faces = np.zeros((n_f, 3), dtype=np.int32)
        vals01, _, _, _, _, _, _ = load_and_prepare_map(
            p, n_verts=10, n_faces=n_f, faces=faces
        )
        assert vals01.dtype == np.float32


# ---------------------------------------------------------------------------
# _find_file_casefold
# ---------------------------------------------------------------------------

class TestFindFileCasefold:
    def test_exact_match(self, tmp_path):
        (tmp_path / "bunny.obj").touch()
        result = _find_file_casefold(tmp_path, "bunny", ".obj")
        assert result is not None and result.name == "bunny.obj"

    def test_case_insensitive(self, tmp_path):
        (tmp_path / "Bunny.OBJ").touch()
        result = _find_file_casefold(tmp_path, "bunny", ".obj")
        assert result is not None

    def test_dash_underscore_normalisation(self, tmp_path):
        """Stem stored with dash should be found when searching with underscore."""
        (tmp_path / "Starfruit-L3.csv").touch()
        result = _find_file_casefold(tmp_path, "Starfruit_L3", ".csv")
        assert result is not None and result.name == "Starfruit-L3.csv"

    def test_missing_returns_none(self, tmp_path):
        result = _find_file_casefold(tmp_path, "nonexistent", ".obj")
        assert result is None

    def test_missing_dir_returns_none(self, tmp_path):
        result = _find_file_casefold(tmp_path / "no_such_dir", "x", ".txt")
        assert result is None


# ---------------------------------------------------------------------------
# discover_models
# ---------------------------------------------------------------------------

class TestDiscoverModels:
    def _make_sal3d_metrics(self, root: Path, models: list[str]) -> Path:
        ss_root = root / "baseline_screen_space"
        for m in models:
            (ss_root / m / SAL3D_SCREEN_TAG).mkdir(parents=True)
        return root

    def _make_mm_metrics(self, root: Path, tt: str, models: list[str]) -> Path:
        ss_root = root / tt / "baseline_screen_space"
        for m in models:
            (ss_root / m / MM_SCREEN_TAG).mkdir(parents=True)
        return root

    def test_sal3d_discovers_models(self, tmp_path):
        models = ["bunny", "dragon", "turbine"]
        metrics_root = self._make_sal3d_metrics(tmp_path / "mr", models)
        result = discover_models("sal3d", metrics_root, None)
        assert set(result) == set(models)

    def test_sal3d_sorted(self, tmp_path):
        models = ["zz", "aa", "mm"]
        metrics_root = self._make_sal3d_metrics(tmp_path / "mr", models)
        result = discover_models("sal3d", metrics_root, None)
        assert result == sorted(models)

    def test_meshmamba_discovers_with_texture_type(self, tmp_path):
        models = ["sofa", "chair"]
        metrics_root = self._make_mm_metrics(tmp_path / "mr", "non_texture", models)
        result = discover_models("meshmamba", metrics_root, "non_texture")
        assert set(result) == set(models)

    def _make_3dva_metrics(self, root: Path, models: list[str]) -> Path:
        ss_root = root / "baseline_screen_space"
        for m in models:
            (ss_root / m / THREE_DVA_SCREEN_TAG).mkdir(parents=True)
        return root

    def test_3dva_discovers_models(self, tmp_path):
        models = ["A380", "Eiffel", "Sphinx"]
        metrics_root = self._make_3dva_metrics(tmp_path / "mr", models)
        result = discover_models("3dva", metrics_root, None)
        assert set(result) == set(models)

    def test_missing_ss_root_raises(self, tmp_path):
        metrics_root = tmp_path / "mr"
        metrics_root.mkdir()
        with pytest.raises(RuntimeError, match="baseline_screen_space"):
            discover_models("sal3d", metrics_root, None)


# ---------------------------------------------------------------------------
# resolve_obj_path
# ---------------------------------------------------------------------------

class TestResolveObjPath:
    def test_sal3d_obj(self, tmp_path):
        dataset_root = tmp_path / "ds"
        (dataset_root / "Meshes").mkdir(parents=True)
        obj = dataset_root / "Meshes" / "bunny.obj"
        obj.touch()
        result = resolve_obj_path("sal3d", dataset_root, "bunny", None)
        assert result == obj

    def test_meshmamba_obj(self, tmp_path):
        dataset_root = tmp_path / "ds"
        model_dir = dataset_root / "MeshFile" / "non_texture" / "chair"
        model_dir.mkdir(parents=True)
        # actual OBJ filename may differ from model name (as on server)
        obj = model_dir / "chair-v1.obj"
        obj.touch()
        result = resolve_obj_path("meshmamba", dataset_root, "chair", "non_texture")
        assert result == obj

    def test_3dva_obj(self, tmp_path):
        dataset_root = tmp_path / "ds"
        mesh_dir = dataset_root / "3DModels-Simplif-up"
        mesh_dir.mkdir(parents=True)
        obj = mesh_dir / "A380.obj"
        obj.touch()
        result = resolve_obj_path("3dva", dataset_root, "A380", None)
        assert result == obj

    def test_missing_returns_none(self, tmp_path):
        dataset_root = tmp_path / "ds"
        (dataset_root / "Meshes").mkdir(parents=True)
        result = resolve_obj_path("sal3d", dataset_root, "ghost", None)
        assert result is None


# ---------------------------------------------------------------------------
# resolve_map_paths
# ---------------------------------------------------------------------------

class TestResolveMapPaths:
    def _sal3d_setup(self, tmp_path, model, *, with_gt=True):
        metrics_root = tmp_path / "metrics"
        ss_dir = metrics_root / "baseline_screen_space" / model / SAL3D_SCREEN_TAG
        ss_dir.mkdir(parents=True)
        ss_file = ss_dir / f"{model}_screen_space_vertices.txt"
        ss_file.touch()

        cone_dir = metrics_root / "baseline_cone" / model / SAL3D_CONE_TAG
        cone_dir.mkdir(parents=True)
        cone_file = cone_dir / f"{model}_cone_vertices.txt"
        cone_file.touch()

        fixed_gt_dir = tmp_path / "sal3d_fixed_face_gt"
        fixed_gt_dir.mkdir(exist_ok=True)
        gt_file = None
        if with_gt:
            gt_file = fixed_gt_dir / f"{model}_faces.txt"
            gt_file.touch()

        dataset_root = tmp_path / "ds"
        return metrics_root, dataset_root, fixed_gt_dir, ss_file, cone_file, gt_file

    def test_sal3d_screen_space_path(self, tmp_path):
        mr, dr, gt_dir, ss_file, _, _ = self._sal3d_setup(tmp_path, "bunny")
        paths = resolve_map_paths("sal3d", mr, dr, "bunny", None, gt_dir, None,
                                  ["screen_space"])
        assert paths["screen_space"] == ss_file

    def test_sal3d_cone_path(self, tmp_path):
        mr, dr, gt_dir, _, cone_file, _ = self._sal3d_setup(tmp_path, "dragon")
        paths = resolve_map_paths("sal3d", mr, dr, "dragon", None, gt_dir, None,
                                  ["cone"])
        assert paths["cone"] == cone_file

    def test_sal3d_gt_path(self, tmp_path):
        mr, dr, gt_dir, _, _, gt_file = self._sal3d_setup(tmp_path, "turbine")
        paths = resolve_map_paths("sal3d", mr, dr, "turbine", None, gt_dir, None,
                                  ["gt"])
        assert paths["gt"] == gt_file

    def test_sal3d_gt_none_when_no_fixed_gt_dir(self, tmp_path):
        mr, dr, gt_dir, _, _, _ = self._sal3d_setup(tmp_path, "bunny")
        paths = resolve_map_paths("sal3d", mr, dr, "bunny", None, None, None,
                                  ["gt"])
        assert paths["gt"] is None

    def test_sal3d_missing_file_returns_none(self, tmp_path):
        mr, dr, gt_dir, _, _, _ = self._sal3d_setup(tmp_path, "bunny")
        resolve_map_paths("sal3d", mr, dr, "bunny", None, gt_dir, None,
                          ["screen_space", "cone"])
        paths2 = resolve_map_paths("sal3d", mr, dr, "ghost", None, gt_dir, None,
                                   ["screen_space"])
        assert paths2["screen_space"] is None

    def test_meshmamba_screen_space_path(self, tmp_path):
        model = "sofa"
        tt = "non_texture"
        metrics_root = tmp_path / "mr"
        ss_dir = metrics_root / tt / "baseline_screen_space" / model / MM_SCREEN_TAG
        ss_dir.mkdir(parents=True)
        ss_file = ss_dir / f"{model}_screen_space_faces.txt"
        ss_file.touch()
        dataset_root = tmp_path / "ds"
        paths = resolve_map_paths("meshmamba", metrics_root, dataset_root, model,
                                  tt, None, None, ["screen_space"])
        assert paths["screen_space"] == ss_file

    def test_meshmamba_cone_path(self, tmp_path):
        model = "chair"
        tt = "rgb_texture"
        metrics_root = tmp_path / "mr"
        cone_dir = metrics_root / tt / "baseline_cone" / model / MM_CONE_TAG
        cone_dir.mkdir(parents=True)
        cone_file = cone_dir / f"{model}_cone_faces.txt"
        cone_file.touch()
        dataset_root = tmp_path / "ds"
        paths = resolve_map_paths("meshmamba", metrics_root, dataset_root, model,
                                  tt, None, None, ["cone"])
        assert paths["cone"] == cone_file

    def test_3dva_screen_space_path(self, tmp_path):
        model = "A380"
        metrics_root = tmp_path / "mr"
        ss_dir = metrics_root / "baseline_screen_space" / model / THREE_DVA_SCREEN_TAG
        ss_dir.mkdir(parents=True)
        ss_file = ss_dir / f"{model}_screen_space_combined_vertices.txt"
        ss_file.touch()
        dataset_root = tmp_path / "ds"
        paths = resolve_map_paths("3dva", metrics_root, dataset_root, model,
                                  None, None, None, ["screen_space"])
        assert paths["screen_space"] == ss_file

    def test_3dva_cone_path(self, tmp_path):
        model = "A380"
        metrics_root = tmp_path / "mr"
        cone_dir = metrics_root / "baseline_cone" / model / THREE_DVA_CONE_TAG
        cone_dir.mkdir(parents=True)
        cone_file = cone_dir / f"{model}_cone_norm.txt"
        cone_file.touch()
        dataset_root = tmp_path / "ds"
        paths = resolve_map_paths("3dva", metrics_root, dataset_root, model,
                                  None, None, None, ["cone"])
        assert paths["cone"] == cone_file

    def test_3dva_gt_path(self, tmp_path):
        model = "A380"
        metrics_root = tmp_path / "mr"
        combined_gt_dir = tmp_path / "CombinedGT"
        combined_gt_dir.mkdir()
        gt_file = combined_gt_dir / f"{model}_combined_gt.txt"
        gt_file.touch()
        dataset_root = tmp_path / "ds"
        paths = resolve_map_paths("3dva", metrics_root, dataset_root, model,
                                  None, None, combined_gt_dir, ["gt"])
        assert paths["gt"] == gt_file

    def test_3dva_gt_none_when_no_combined_gt_dir(self, tmp_path):
        model = "A380"
        metrics_root = tmp_path / "mr"
        dataset_root = tmp_path / "ds"
        paths = resolve_map_paths("3dva", metrics_root, dataset_root, model,
                                  None, None, None, ["gt"])
        assert paths["gt"] is None


# ---------------------------------------------------------------------------
# write_manifest / write_summary_csv
# ---------------------------------------------------------------------------

class TestWriteOutputs:
    def test_write_manifest(self, tmp_path):
        entries = [{"model": "bunny", "map_type": "screen_space", "status": "ok"}]
        manifest_path = write_manifest(entries, tmp_path)
        assert manifest_path.exists()
        loaded = json.loads(manifest_path.read_text())
        assert loaded[0]["model"] == "bunny"

    def test_write_summary_csv_columns(self, tmp_path):
        rows = [{
            "dataset": "sal3d", "texture_type": "", "model": "bunny",
            "map_type": "screen_space", "status": "ok", "error_message": "",
            "mesh_path": "/a.obj", "map_path": "/b.txt",
            "front": "f.png", "back": "b.png", "left": "l.png",
            "right": "r.png", "top": "t.png", "bottom": "bt.png",
            "montage": "m.png",
        }]
        csv_path = write_summary_csv(rows, tmp_path)
        assert csv_path.exists()
        with open(csv_path) as fh:
            reader = csv.DictReader(fh)
            header = reader.fieldnames
            assert "dataset" in header
            assert "model" in header
            assert "montage" in header

    def test_write_summary_csv_error_row(self, tmp_path):
        row = _error_row("sal3d", None, "ghost", "cone", "OBJ not found")
        csv_path = write_summary_csv([row], tmp_path)
        with open(csv_path) as fh:
            rows_read = list(csv.DictReader(fh))
        assert rows_read[0]["status"] == "error"
        assert "OBJ not found" in rows_read[0]["error_message"]


# ---------------------------------------------------------------------------
# _rel
# ---------------------------------------------------------------------------

class TestRel:
    def test_relative_under_root(self, tmp_path):
        p = tmp_path / "SAL3D" / "bunny" / "front.png"
        assert _rel(p, tmp_path) == "SAL3D/bunny/front.png"

    def test_outside_root_returns_str(self, tmp_path):
        p = Path("/completely/different/path.png")
        result = _rel(p, tmp_path)
        assert "/completely/different/path.png" in result
