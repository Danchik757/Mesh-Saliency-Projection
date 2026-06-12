"""
Unit tests for video_creation/heatmap_on_mesh_video/render_batch_gt_cone.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from video_creation.heatmap_on_mesh_video.render_batch_gt_cone import (
    _build_renderer_cmd,
    _pick_mesh_obj,
    resolve_paths,
    PLACE,
)
from video_creation.heatmap_on_mesh_video.render_heatmap_video import build_parser


# ---------------------------------------------------------------------------
# _pick_mesh_obj
# ---------------------------------------------------------------------------

class TestPickMeshObj:
    def test_empty_dir_returns_placeholder(self, tmp_path):
        result = _pick_mesh_obj(tmp_path, "MyModel")
        assert result == tmp_path / "MyModel.obj"
        assert not result.exists()

    def test_single_obj_returned(self, tmp_path):
        (tmp_path / "model.obj").touch()
        result = _pick_mesh_obj(tmp_path, "MyModel")
        assert result.name == "model.obj"

    def test_exact_stem_match_preferred(self, tmp_path):
        (tmp_path / "MyModel.obj").touch()
        (tmp_path / "other.obj").touch()
        result = _pick_mesh_obj(tmp_path, "MyModel")
        assert result.name == "MyModel.obj"

    def test_normalised_dash_underscore_match(self, tmp_path):
        (tmp_path / "Starfruit-L3.obj").touch()
        result = _pick_mesh_obj(tmp_path, "Starfruit_L3")
        assert result.name == "Starfruit-L3.obj"

    def test_normalised_underscore_dash_match(self, tmp_path):
        (tmp_path / "Starfruit_L3.obj").touch()
        result = _pick_mesh_obj(tmp_path, "Starfruit-L3")
        assert result.name == "Starfruit_L3.obj"

    def test_ambiguous_candidates_raises_value_error(self, tmp_path):
        (tmp_path / "abc.obj").touch()
        (tmp_path / "def.obj").touch()
        with pytest.raises(ValueError, match="[Aa]mbigu"):
            _pick_mesh_obj(tmp_path, "SomeModel")

    def test_result_is_deterministic(self, tmp_path):
        (tmp_path / "zz.obj").touch()
        result1 = _pick_mesh_obj(tmp_path, "SomeModel")
        result2 = _pick_mesh_obj(tmp_path, "SomeModel")
        assert result1 == result2

    def test_case_insensitive_stem_match(self, tmp_path):
        (tmp_path / "CHAIR.OBJ").touch()
        result = _pick_mesh_obj(tmp_path, "chair")
        assert result is not None

    def test_nonexistent_dir_returns_placeholder(self, tmp_path):
        missing = tmp_path / "nonexistent_subdir"
        result = _pick_mesh_obj(missing, "Model")
        assert result == missing / "Model.obj"


# ---------------------------------------------------------------------------
# resolve_paths — MeshMamba
# ---------------------------------------------------------------------------

class TestResolvePathsMeshMamba:
    def _setup(self, tmp_path, track="non_texture", model="chair"):
        mm_root = tmp_path / "mm_dataset"
        mesh_dir = mm_root / "MeshFile" / track / model
        mesh_dir.mkdir(parents=True)
        (mesh_dir / f"{model}.obj").touch()
        sal_dir = mm_root / "SaliencyMap" / track
        sal_dir.mkdir(parents=True)
        gt_file = f"{model}_gt.csv"
        (sal_dir / gt_file).touch()
        cone_root = tmp_path / "cone_maps"
        cone_root.mkdir()
        return mm_root, cone_root, gt_file

    def test_normal_resolution_returns_expected_keys(self, tmp_path):
        mm_root, cone_root, gt_file = self._setup(tmp_path)
        gt_lookup = {("non_texture", "chair"): gt_file}
        paths = resolve_paths(
            "meshmamba", "non_texture", "chair", cone_root, gt_lookup,
            mm_dataset_root=mm_root, sal3d_dataset_root=tmp_path / "sal3d",
        )
        assert "gt" in paths
        assert "mesh" in paths
        assert "placement" in paths
        assert "cone" in paths
        assert "ds_canon" in paths
        assert paths["ds_canon"] == "MeshMamba"

    def test_gt_path_uses_lookup_filename(self, tmp_path):
        mm_root, cone_root, gt_file = self._setup(tmp_path)
        gt_lookup = {("non_texture", "chair"): gt_file}
        paths = resolve_paths(
            "meshmamba", "non_texture", "chair", cone_root, gt_lookup,
            mm_dataset_root=mm_root, sal3d_dataset_root=tmp_path / "sal3d",
        )
        assert Path(paths["gt"]).name == gt_file

    def test_missing_gt_lookup_raises_runtime_error(self, tmp_path):
        mm_root, cone_root, _ = self._setup(tmp_path)
        with pytest.raises(RuntimeError, match="No GT entry"):
            resolve_paths(
                "meshmamba", "non_texture", "chair", cone_root, {},
                mm_dataset_root=mm_root, sal3d_dataset_root=tmp_path / "sal3d",
            )

    def test_missing_gt_error_mentions_model(self, tmp_path):
        mm_root, cone_root, _ = self._setup(tmp_path)
        with pytest.raises(RuntimeError, match="chair"):
            resolve_paths(
                "meshmamba", "non_texture", "chair", cone_root, {},
                mm_dataset_root=mm_root, sal3d_dataset_root=tmp_path / "sal3d",
            )

    def test_ambiguous_objs_raises_value_error(self, tmp_path):
        mm_root = tmp_path / "mm_dataset"
        mesh_dir = mm_root / "MeshFile" / "non_texture" / "chair"
        mesh_dir.mkdir(parents=True)
        (mesh_dir / "alpha.obj").touch()
        (mesh_dir / "beta.obj").touch()
        cone_root = tmp_path / "cone_maps"
        cone_root.mkdir()
        gt_lookup = {("non_texture", "chair"): "chair_gt.csv"}
        with pytest.raises(ValueError, match="[Aa]mbigu"):
            resolve_paths(
                "meshmamba", "non_texture", "chair", cone_root, gt_lookup,
                mm_dataset_root=mm_root, sal3d_dataset_root=tmp_path / "sal3d",
            )

    def test_rgb_texture_placement_subdir(self, tmp_path):
        mm_root, cone_root, gt_file = self._setup(tmp_path, track="rgb_texture", model="pear")
        gt_lookup = {("rgb_texture", "pear"): gt_file}
        paths = resolve_paths(
            "meshmamba", "rgb_texture", "pear", cone_root, gt_lookup,
            mm_dataset_root=mm_root, sal3d_dataset_root=tmp_path / "sal3d",
        )
        assert "mamba_rgb_jsons" in str(paths["placement"])


# ---------------------------------------------------------------------------
# resolve_paths — SAL3D
# ---------------------------------------------------------------------------

class TestResolvePathsSal3d:
    def _setup(self, tmp_path, model="vase"):
        sal3d_root = tmp_path / "sal3d"
        (sal3d_root / "Meshes").mkdir(parents=True)
        (sal3d_root / "Meshes" / f"{model}.obj").touch()
        (sal3d_root / "sal3d_fixed_face_gt").mkdir(parents=True)
        (sal3d_root / "sal3d_fixed_face_gt" / f"{model}_faces.txt").touch()
        cone_root = tmp_path / "cone_maps"
        cone_root.mkdir()
        return sal3d_root, cone_root

    def test_normal_resolution(self, tmp_path):
        sal3d_root, cone_root = self._setup(tmp_path)
        paths = resolve_paths(
            "sal3d", "sal3d", "vase", cone_root, {},
            mm_dataset_root=tmp_path / "mm", sal3d_dataset_root=sal3d_root,
        )
        assert paths["ds_canon"] == "SAL3D"
        assert Path(paths["mesh"]).name == "vase.obj"
        assert Path(paths["gt"]).name == "vase_faces.txt"

    def test_cone_path_includes_model(self, tmp_path):
        sal3d_root, cone_root = self._setup(tmp_path)
        paths = resolve_paths(
            "sal3d", "sal3d", "vase", cone_root, {},
            mm_dataset_root=tmp_path / "mm", sal3d_dataset_root=sal3d_root,
        )
        assert "vase" in str(paths["cone"])

    def test_placement_uses_sal3d_jsons(self, tmp_path):
        sal3d_root, cone_root = self._setup(tmp_path)
        paths = resolve_paths(
            "sal3d", "sal3d", "vase", cone_root, {},
            mm_dataset_root=tmp_path / "mm", sal3d_dataset_root=sal3d_root,
        )
        assert "sal3d_jsons" in str(paths["placement"])
        assert "Sal3D_vase.json" in str(paths["placement"])


# ---------------------------------------------------------------------------
# _build_renderer_cmd
# ---------------------------------------------------------------------------

class TestBuildRendererCmd:
    def _make_paths(self, tmp_path):
        return {
            "mesh": tmp_path / "model.obj",
            "placement": tmp_path / "placement.json",
            "gt": tmp_path / "gt.txt",
            "cone": tmp_path / "cone.txt",
            "ds_canon": "MeshMamba",
        }

    def test_uses_placement_json_flag(self, tmp_path):
        paths = self._make_paths(tmp_path)
        cmd = _build_renderer_cmd(
            "meshmamba", "non_texture", "chair", "gt",
            paths["gt"], paths, tmp_path / "staging", "rc3_vis_gt",
        )
        assert "--placement-json" in cmd
        assert "--placement" not in cmd

    def test_build_renderer_cmd_parseable(self, tmp_path):
        paths = self._make_paths(tmp_path)
        cmd = _build_renderer_cmd(
            "meshmamba", "non_texture", "chair", "gt",
            paths["gt"], paths, tmp_path / "staging", "rc3_vis_gt",
        )
        cli_args = cmd[2:]
        args = build_parser().parse_args(cli_args)
        assert Path(args.placement_json) == Path(paths["placement"])
        assert args.model == "chair"
        assert args.map_type == "gt"

    def test_sal3d_no_texture_type_flag(self, tmp_path):
        paths = self._make_paths(tmp_path)
        cmd = _build_renderer_cmd(
            "sal3d", "sal3d", "vase", "gt",
            paths["gt"], paths, tmp_path / "staging", "rc3_vis_gt",
        )
        assert "--texture-type" not in cmd

    def test_meshmamba_includes_texture_type(self, tmp_path):
        paths = self._make_paths(tmp_path)
        cmd = _build_renderer_cmd(
            "meshmamba", "rgb_texture", "pear", "cone",
            paths["cone"], paths, tmp_path / "staging", "note",
        )
        assert "--texture-type" in cmd
        idx = cmd.index("--texture-type")
        assert cmd[idx + 1] == "rgb_texture"


# ---------------------------------------------------------------------------
# _pick_mesh_obj — duplicate normalized stems
# ---------------------------------------------------------------------------

class TestPickMeshObjDuplicateNormStems:
    def test_duplicate_normalized_stems_raises(self, tmp_path):
        (tmp_path / "A-B.obj").touch()
        (tmp_path / "A_B.obj").touch()
        with pytest.raises(ValueError, match="[Aa]mbigu"):
            _pick_mesh_obj(tmp_path, "AB")
