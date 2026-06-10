"""
Tests for SAL3D fixed per-face GT loading (utils/sal3d_fixed_gt.py).

Covers load_fixed_face_gt():
- Correct length → (gt_array, gt_path) returned
- Wrong length  → ValueError with informative message
- Missing file  → FileNotFoundError
- Problem models (MaxPlanck/meca/sofa/turbine): small synthetic fixtures succeed
- Documents the known vertex-count mismatches that make old Gaze path unsafe
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from utils.sal3d_fixed_gt import load_fixed_face_gt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_gt(directory: Path, model: str, values: np.ndarray) -> Path:
    path = directory / f"{model}_faces.txt"
    np.savetxt(path, values, fmt="%.10f")
    return path


# ---------------------------------------------------------------------------
# Core loading behaviour
# ---------------------------------------------------------------------------

class TestLoadFixedFaceGt:
    def test_correct_length(self, tmp_path):
        gt_dir = tmp_path / "sal3d_fixed_face_gt"
        gt_dir.mkdir()
        expected = np.linspace(0.0, 1.0, 12)
        _write_gt(gt_dir, "bunny", expected)
        gt, path = load_fixed_face_gt(gt_dir, "bunny", n_faces=12)
        np.testing.assert_allclose(gt, expected, atol=1e-9)
        assert path.name == "bunny_faces.txt"

    def test_wrong_length_raises(self, tmp_path):
        gt_dir = tmp_path / "sal3d_fixed_face_gt"
        gt_dir.mkdir()
        _write_gt(gt_dir, "bunny", np.ones(10))
        with pytest.raises(ValueError, match="Fixed GT length 10 != n_faces 5"):
            load_fixed_face_gt(gt_dir, "bunny", n_faces=5)

    def test_missing_file_raises(self, tmp_path):
        gt_dir = tmp_path / "sal3d_fixed_face_gt"
        gt_dir.mkdir()
        with pytest.raises(FileNotFoundError, match="Fixed face GT not found"):
            load_fixed_face_gt(gt_dir, "nonexistent_model", n_faces=100)

    def test_values_preserved(self, tmp_path):
        gt_dir = tmp_path / "sal3d_fixed_face_gt"
        gt_dir.mkdir()
        vals = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
        _write_gt(gt_dir, "dragon", vals)
        gt, _ = load_fixed_face_gt(gt_dir, "dragon", n_faces=5)
        np.testing.assert_allclose(gt, vals, atol=1e-9)

    def test_returned_path_is_file(self, tmp_path):
        gt_dir = tmp_path / "sal3d_fixed_face_gt"
        gt_dir.mkdir()
        _write_gt(gt_dir, "A380", np.zeros(6))
        _, path = load_fixed_face_gt(gt_dir, "A380", n_faces=6)
        assert path.is_file()


# ---------------------------------------------------------------------------
# Problem models: small synthetic fixtures must succeed with correct length
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("model", ["MaxPlanck", "meca", "sofa", "turbine"])
def test_problem_models_succeed_with_correct_length(tmp_path, model):
    """Models whose raw Gaze vertex count mismatches OBJ succeed via fixed-face GT."""
    gt_dir = tmp_path / "sal3d_fixed_face_gt"
    gt_dir.mkdir()
    n_faces = 80
    gt_vals = np.random.default_rng(42).random(n_faces)
    _write_gt(gt_dir, model, gt_vals)
    gt, path = load_fixed_face_gt(gt_dir, model, n_faces=n_faces)
    assert len(gt) == n_faces
    assert path.name == f"{model}_faces.txt"


@pytest.mark.parametrize("model", ["MaxPlanck", "meca", "sofa", "turbine"])
def test_problem_models_length_mismatch_raises(tmp_path, model):
    gt_dir = tmp_path / "sal3d_fixed_face_gt"
    gt_dir.mkdir()
    _write_gt(gt_dir, model, np.ones(50))
    with pytest.raises(ValueError, match="Fixed GT length 50 != n_faces"):
        load_fixed_face_gt(gt_dir, model, n_faces=99)


# ---------------------------------------------------------------------------
# Document known vertex-count mismatches (no files needed)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("model,n_gaze_rows,n_obj_verts", [
    ("MaxPlanck", 20000, 19999),
    ("meca",      20000, 15000),
    ("sofa",      20000, 15125),
])
def test_known_gaze_vert_mismatches(model, n_gaze_rows, n_obj_verts):
    """These models have n_gaze > n_verts, which load_gt_aligned_to_obj() rejects.
    They require load_fixed_face_gt() via --fixed-gt-dir."""
    assert n_gaze_rows > n_obj_verts, (
        f"{model}: n_gaze_rows={n_gaze_rows} should exceed n_obj_verts={n_obj_verts}"
    )
