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
    _find_obj_nested,
    _normalise_lookup_name,
    _rel,
    discover_models,
    load_and_prepare_map,
    make_compare_collage,
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

    def test_display_percentile_clips_outlier(self, tmp_path):
        """display_percentile<100 clips above-ceiling values to 1; input_max is true max."""
        n_f = 10
        # 9 values in [0,1], one outlier at 100
        vals = np.array([0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 100.0])
        p = tmp_path / "map.txt"
        _write_float_file(p, vals)
        faces = np.zeros((n_f, 3), dtype=np.int32)
        vals01, vmin, vmax, _, _, _, _ = load_and_prepare_map(
            p, n_verts=15, n_faces=n_f, faces=faces, display_percentile=90.0
        )
        # true max still returned
        assert vmax == pytest.approx(100.0)
        # outlier face is clamped to 1.0
        assert float(vals01[-1]) == pytest.approx(1.0)
        # a mid-range face is strictly < 1.0
        assert float(vals01[4]) < 1.0

    def test_display_percentile_100_equals_minmax(self, tmp_path):
        """display_percentile=100 (default) preserves original minmax behaviour."""
        n_f = 5
        vals = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
        p = tmp_path / "map.txt"
        _write_float_file(p, vals)
        faces = np.zeros((n_f, 3), dtype=np.int32)
        vals01, _, _, _, _, _, _ = load_and_prepare_map(
            p, n_verts=10, n_faces=n_f, faces=faces, display_percentile=100.0
        )
        assert float(vals01.max()) == pytest.approx(1.0)
        assert float(vals01.min()) == pytest.approx(0.0)


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

    def test_meshmamba_gt_alias_lookup(self, tmp_path):
        """gt_lookup resolves alias mismatches like Jukebox_L1 → Textured.csv."""
        model = "Jukebox_bubbler_style_V2_L1"
        actual_csv = "Jukebox_bubbler_style_V2_Textured.csv"
        tt = "rgb_texture"
        dataset_root = tmp_path / "ds"
        gt_dir = dataset_root / "SaliencyMap" / tt
        gt_dir.mkdir(parents=True)
        (gt_dir / actual_csv).touch()

        metrics_root = tmp_path / "mr"
        # Without lookup: casefold search finds nothing (stem mismatch)
        paths_no_lookup = resolve_map_paths(
            "meshmamba", metrics_root, dataset_root, model, tt, None, None, ["gt"]
        )
        assert paths_no_lookup["gt"] is None

        # With lookup: resolves to actual file
        lookup = {(tt, model): actual_csv}
        paths_with_lookup = resolve_map_paths(
            "meshmamba", metrics_root, dataset_root, model, tt, None, None, ["gt"],
            gt_lookup=lookup,
        )
        assert paths_with_lookup["gt"] is not None
        assert paths_with_lookup["gt"].name == actual_csv

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


# ---------------------------------------------------------------------------
# make_compare_collage — colorbar display range
# ---------------------------------------------------------------------------

class TestCompareCollageColorbar:
    def test_manifest_preserves_raw_input_range(self, tmp_path):
        """write_manifest stores raw input_min/input_max, not the [0,1] display range."""
        entry = {
            "model": "alien2",
            "map_type": "screen_space",
            "input_min": 1.23e-6,
            "input_max": 4.56e-5,
            "display_normalization": "minmax_per_map",
            "status": "ok",
        }
        manifest_path = write_manifest([entry], tmp_path)
        loaded = json.loads(manifest_path.read_text())
        assert loaded[0]["input_min"] == pytest.approx(1.23e-6)
        assert loaded[0]["input_max"] == pytest.approx(4.56e-5)
        assert loaded[0]["display_normalization"] == "minmax_per_map"

    def test_collage_colorbar_uses_display_range(self, tmp_path):
        """make_compare_collage colorbar is always [0,1] regardless of raw map scale."""
        matplotlib = pytest.importorskip("matplotlib")
        matplotlib.use("Agg")
        import matplotlib.pyplot as mplt

        # Create 6 minimal dummy PNGs for one map type
        for view_name in ["front", "back", "left", "right", "top", "bottom"]:
            fig, ax = mplt.subplots(figsize=(1, 1))
            ax.axis("off")
            fig.savefig(str(tmp_path / f"{view_name}.png"), dpi=10)
            mplt.close(fig)

        img_paths = {v: tmp_path / f"{v}.png"
                     for v in ["front", "back", "left", "right", "top", "bottom"]}
        # Raw screen_space range is far from [0,1]; collage must not use it
        per_type_image_paths = {"screen_space": img_paths}
        out_path = tmp_path / "collage.png"

        colorbar_ranges = make_compare_collage(
            per_type_image_paths, "Test Title", out_path
        )

        assert out_path.exists()
        assert colorbar_ranges == [(0.0, 1.0)]

    def test_collage_returns_one_range_per_row(self, tmp_path):
        """make_compare_collage returns exactly one (0,1) entry per rendered row."""
        matplotlib = pytest.importorskip("matplotlib")
        matplotlib.use("Agg")
        import matplotlib.pyplot as mplt

        for view_name in ["front", "back", "left", "right", "top", "bottom"]:
            fig, ax = mplt.subplots(figsize=(1, 1))
            ax.axis("off")
            fig.savefig(str(tmp_path / f"{view_name}.png"), dpi=10)
            mplt.close(fig)

        img_paths = {v: tmp_path / f"{v}.png"
                     for v in ["front", "back", "left", "right", "top", "bottom"]}
        per_type_image_paths = {
            "gt": img_paths,
            "screen_space": img_paths,
            "cone": img_paths,
        }
        out_path = tmp_path / "collage3.png"

        colorbar_ranges = make_compare_collage(
            per_type_image_paths, "Three rows", out_path
        )

        assert len(colorbar_ranges) == 3
        assert all(r == (0.0, 1.0) for r in colorbar_ranges)


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

    def test_underscore_and_dash_equivalent(self):
        assert _normalise_lookup_name("Pear_L3") == _normalise_lookup_name("Pear-L3")


# ---------------------------------------------------------------------------
# _find_obj_nested — H1 regression tests
# ---------------------------------------------------------------------------

class TestFindObjNested:
    def test_flat_exact(self, tmp_path):
        (tmp_path / "bunny.obj").touch()
        assert _find_obj_nested(tmp_path, "bunny") == tmp_path / "bunny.obj"

    def test_flat_casefold(self, tmp_path):
        (tmp_path / "BUNNY.OBJ").touch()
        result = _find_obj_nested(tmp_path, "bunny")
        assert result is not None

    def test_nested_exact_name(self, tmp_path):
        sub = tmp_path / "chair"
        sub.mkdir()
        (sub / "chair.obj").touch()
        assert _find_obj_nested(tmp_path, "chair") == sub / "chair.obj"

    def test_nested_case_insensitive_subdir(self, tmp_path):
        sub = tmp_path / "Chair"
        sub.mkdir()
        (sub / "Chair.obj").touch()
        result = _find_obj_nested(tmp_path, "chair")
        assert result is not None

    def test_nested_dash_variant(self, tmp_path):
        sub = tmp_path / "Starfruit_L3"
        sub.mkdir()
        (sub / "Starfruit-L3.obj").touch()
        result = _find_obj_nested(tmp_path, "Starfruit_L3")
        assert result is not None
        assert result.name == "Starfruit-L3.obj"

    def test_nested_single_obj_fallback(self, tmp_path):
        sub = tmp_path / "MyModel"
        sub.mkdir()
        (sub / "totally_different.obj").touch()
        result = _find_obj_nested(tmp_path, "MyModel")
        assert result is not None

    def test_nested_multiple_objs_no_match_returns_none(self, tmp_path):
        sub = tmp_path / "MyModel"
        sub.mkdir()
        (sub / "alpha.obj").touch()
        (sub / "beta.obj").touch()
        result = _find_obj_nested(tmp_path, "MyModel")
        assert result is None

    def test_missing_returns_none(self, tmp_path):
        assert _find_obj_nested(tmp_path, "ghost") is None

    def test_empty_subdir_returns_none(self, tmp_path):
        (tmp_path / "MyModel").mkdir()
        assert _find_obj_nested(tmp_path, "MyModel") is None


# ---------------------------------------------------------------------------
# resolve_obj_path — MeshMamba nested layout (H1 regression)
# ---------------------------------------------------------------------------

class TestResolveObjPathMeshMambaNested:
    def test_nested_obj_found(self, tmp_path):
        dataset_root = tmp_path / "ds"
        model_dir = dataset_root / "MeshFile" / "non_texture" / "chair"
        model_dir.mkdir(parents=True)
        (model_dir / "chair.obj").touch()
        result = resolve_obj_path("meshmamba", dataset_root, "chair", "non_texture")
        assert result is not None
        assert result.name == "chair.obj"

    def test_nested_dash_stem_variant(self, tmp_path):
        dataset_root = tmp_path / "ds"
        model_dir = dataset_root / "MeshFile" / "non_texture" / "Starfruit_L3"
        model_dir.mkdir(parents=True)
        (model_dir / "Starfruit-L3.obj").touch()
        result = resolve_obj_path("meshmamba", dataset_root, "Starfruit_L3", "non_texture")
        assert result is not None
        assert result.name == "Starfruit-L3.obj"

    def test_flat_obj_still_found(self, tmp_path):
        dataset_root = tmp_path / "ds"
        mesh_dir = dataset_root / "MeshFile" / "rgb_texture"
        mesh_dir.mkdir(parents=True)
        (mesh_dir / "sofa.obj").touch()
        result = resolve_obj_path("meshmamba", dataset_root, "sofa", "rgb_texture")
        assert result is not None
        assert result.name == "sofa.obj"

    def test_missing_returns_none(self, tmp_path):
        dataset_root = tmp_path / "ds"
        (dataset_root / "MeshFile" / "non_texture").mkdir(parents=True)
        result = resolve_obj_path("meshmamba", dataset_root, "ghost", "non_texture")
        assert result is None


# ---------------------------------------------------------------------------
# _find_obj_nested — dash-named directory (Gate 2b regression)
# ---------------------------------------------------------------------------

class TestFindObjNestedDashNamedDir:
    """Exact reproduction of Gate 2b failure: directory Starfruit-L3/ with model Starfruit_L3."""

    def test_dir_dash_model_underscore(self, tmp_path):
        sub = tmp_path / "Starfruit-L3"
        sub.mkdir()
        (sub / "Starfruit-L3.obj").touch()
        result = _find_obj_nested(tmp_path, "Starfruit_L3")
        assert result is not None and result.name == "Starfruit-L3.obj"

    def test_dir_underscore_model_dash(self, tmp_path):
        sub = tmp_path / "Starfruit_L3"
        sub.mkdir()
        (sub / "Starfruit_L3.obj").touch()
        result = _find_obj_nested(tmp_path, "Starfruit-L3")
        assert result is not None

    def test_dir_mixed_case_dash(self, tmp_path):
        sub = tmp_path / "Apple-Red-v1-L3"
        sub.mkdir()
        (sub / "Apple_Red_v1_L3.obj").touch()
        result = _find_obj_nested(tmp_path, "Apple_Red_v1_L3")
        assert result is not None

    def test_resolve_obj_path_dash_dir(self, tmp_path):
        """resolve_obj_path with directory named Starfruit-L3, model Starfruit_L3."""
        dataset_root = tmp_path / "ds"
        model_dir = dataset_root / "MeshFile" / "non_texture" / "Starfruit-L3"
        model_dir.mkdir(parents=True)
        (model_dir / "Starfruit-L3.obj").touch()
        result = resolve_obj_path("meshmamba", dataset_root, "Starfruit_L3", "non_texture")
        assert result is not None and result.name == "Starfruit-L3.obj"


# ---------------------------------------------------------------------------
# _find_obj_nested — ambiguity (Gate 2c)
# ---------------------------------------------------------------------------

class TestFindObjNestedAmbig:
    """Multiple normalized matches must raise ValueError, never silently pick one."""

    def test_two_dirs_same_norm_raises(self, tmp_path):
        (tmp_path / "Starfruit-L3").mkdir()
        (tmp_path / "Starfruit_L3").mkdir()
        (tmp_path / "Starfruit-L3" / "Starfruit-L3.obj").touch()
        (tmp_path / "Starfruit_L3" / "Starfruit_L3.obj").touch()
        with pytest.raises(ValueError, match="[Aa]mbigu"):
            _find_obj_nested(tmp_path, "Starfruit_L3")

    def test_two_files_same_norm_stem_raises(self, tmp_path):
        sub = tmp_path / "AB"
        sub.mkdir()
        (sub / "A-B.obj").touch()
        (sub / "A_B.obj").touch()
        with pytest.raises(ValueError, match="[Aa]mbigu"):
            _find_obj_nested(tmp_path, "AB")
