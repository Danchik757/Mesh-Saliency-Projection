"""
Tests for run_sal3d_reference_batch.inventory_models() in fixed-GT mode.

Verifies that the compact SAL3D package (Meshes/ + sal3d_fixed_face_gt/ + manifest,
no Gaze/ directory) drives model discovery correctly.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_spec = importlib.util.spec_from_file_location(
    "run_sal3d_reference_batch",
    REPO_ROOT / "test" / "launch" / "run_sal3d_reference_batch.py",
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["run_sal3d_reference_batch"] = _mod  # must register before exec for @dataclass
_spec.loader.exec_module(_mod)

inventory_models = _mod.inventory_models


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_compact_pkg(
    tmp: Path,
    models: list[str],
    *,
    extra_gt: list[str] | None = None,
) -> tuple[Path, Path, Path]:
    """Build a minimal compact fixed-GT package + fixation roots.

    Returns (dataset_root, fixed_gt_dir, fixation_root).
    extra_gt: models that get a _faces.txt but NOT a fixation JSON.
    """
    dataset_root = tmp / "dataset"
    (dataset_root / "Meshes").mkdir(parents=True)
    fixed_gt_dir = tmp / "sal3d_fixed_face_gt"
    fixed_gt_dir.mkdir()
    fixation_root = tmp / "fixations"

    for model in models:
        (dataset_root / "Meshes" / f"{model}.obj").touch()
        (fixed_gt_dir / f"{model}_faces.txt").touch()
        fix_dir = fixation_root / f"SAL3D_{model}"
        fix_dir.mkdir(parents=True)
        (fix_dir / "fixations.json").touch()

    for model in (extra_gt or []):
        (fixed_gt_dir / f"{model}_faces.txt").touch()
        # No fixation JSON for these

    return dataset_root, fixed_gt_dir, fixation_root


# ---------------------------------------------------------------------------
# Fixed-GT mode tests
# ---------------------------------------------------------------------------

class TestInventoryFixedGtMode:
    def test_compact_package_without_gaze_dir(self, tmp_path, monkeypatch):
        """Compact package without Gaze/ succeeds when --fixed-gt-dir is set."""
        models = ["bunny", "dragon", "turbine"]
        dataset_root, fixed_gt_dir, fixation_root = _make_compact_pkg(tmp_path, models)
        assert not (dataset_root / "Gaze").exists()

        monkeypatch.setattr(_mod, "resolve_dataset_root", lambda: dataset_root)
        monkeypatch.setattr(_mod, "resolve_fixation_root", lambda: fixation_root)

        result = inventory_models(
            None,
            csv_compat=False,
            fixed_gt_dir=fixed_gt_dir,
            sal3d_manifest=None,
        )
        assert set(result) == set(models)

    def test_gorgoile_excluded_when_no_fixation_json(self, tmp_path, monkeypatch):
        """gorgoile is auto-excluded when its fixation JSON is absent."""
        models = ["bunny", "dragon", "turbine"]
        dataset_root, fixed_gt_dir, fixation_root = _make_compact_pkg(
            tmp_path, models, extra_gt=["gorgoile"]
        )
        # gorgoile has a fixed GT file but no fixation JSON
        assert (fixed_gt_dir / "gorgoile_faces.txt").exists()
        assert not (fixation_root / "SAL3D_gorgoile" / "fixations.json").exists()

        monkeypatch.setattr(_mod, "resolve_dataset_root", lambda: dataset_root)
        monkeypatch.setattr(_mod, "resolve_fixation_root", lambda: fixation_root)

        result = inventory_models(
            None,
            csv_compat=False,
            fixed_gt_dir=fixed_gt_dir,
            sal3d_manifest=None,
        )
        assert "gorgoile" not in result
        assert set(result) == set(models)

    def test_missing_obj_excluded(self, tmp_path, monkeypatch):
        """Model with fixed GT file but no OBJ is excluded."""
        models = ["bunny", "dragon"]
        dataset_root, fixed_gt_dir, fixation_root = _make_compact_pkg(tmp_path, models)
        # Add GT + fixation for a model with no OBJ
        (fixed_gt_dir / "orphan_faces.txt").touch()
        fix_dir = fixation_root / "SAL3D_orphan"
        fix_dir.mkdir(parents=True)
        (fix_dir / "fixations.json").touch()

        monkeypatch.setattr(_mod, "resolve_dataset_root", lambda: dataset_root)
        monkeypatch.setattr(_mod, "resolve_fixation_root", lambda: fixation_root)

        result = inventory_models(
            None,
            csv_compat=False,
            fixed_gt_dir=fixed_gt_dir,
            sal3d_manifest=None,
        )
        assert "orphan" not in result
        assert set(result) == set(models)

    def test_manifest_based_discovery(self, tmp_path, monkeypatch):
        """When --sal3d-manifest given, model names come from its 'model' column."""
        models = ["bunny", "dragon"]
        dataset_root, fixed_gt_dir, fixation_root = _make_compact_pkg(tmp_path, models)
        manifest = tmp_path / "sal3d_manifest.csv"
        manifest.write_text("model,n_faces,tier\nbunny,1234,standard\ndragon,5678,standard\n")

        monkeypatch.setattr(_mod, "resolve_dataset_root", lambda: dataset_root)
        monkeypatch.setattr(_mod, "resolve_fixation_root", lambda: fixation_root)

        result = inventory_models(
            None,
            csv_compat=False,
            fixed_gt_dir=fixed_gt_dir,
            sal3d_manifest=manifest,
        )
        assert set(result) == set(models)

    def test_manifest_excludes_unlisted_models(self, tmp_path, monkeypatch):
        """Model in _faces.txt but absent from manifest is not included."""
        models = ["bunny", "dragon"]
        dataset_root, fixed_gt_dir, fixation_root = _make_compact_pkg(tmp_path, models)
        # Add unlisted model
        (fixed_gt_dir / "extra_faces.txt").touch()
        fix_dir = fixation_root / "SAL3D_extra"
        fix_dir.mkdir(parents=True)
        (fix_dir / "fixations.json").touch()
        (dataset_root / "Meshes" / "extra.obj").touch()

        manifest = tmp_path / "sal3d_manifest.csv"
        manifest.write_text("model,n_faces\nbunny,1234\ndragon,5678\n")

        monkeypatch.setattr(_mod, "resolve_dataset_root", lambda: dataset_root)
        monkeypatch.setattr(_mod, "resolve_fixation_root", lambda: fixation_root)

        result = inventory_models(
            None,
            csv_compat=False,
            fixed_gt_dir=fixed_gt_dir,
            sal3d_manifest=manifest,
        )
        assert "extra" not in result
        assert set(result) == set(models)

    def test_explicit_models_bypass_discovery(self, tmp_path, monkeypatch):
        """--models list bypasses inventory entirely."""
        dataset_root, fixed_gt_dir, fixation_root = _make_compact_pkg(tmp_path, [])
        monkeypatch.setattr(_mod, "resolve_dataset_root", lambda: dataset_root)
        monkeypatch.setattr(_mod, "resolve_fixation_root", lambda: fixation_root)

        result = inventory_models(
            ["bunny", "dragon"],
            csv_compat=False,
            fixed_gt_dir=fixed_gt_dir,
            sal3d_manifest=None,
        )
        assert result == ["bunny", "dragon"]

    def test_empty_fixed_gt_dir_returns_empty(self, tmp_path, monkeypatch):
        """Empty sal3d_fixed_face_gt/ returns empty list."""
        dataset_root = tmp_path / "dataset"
        (dataset_root / "Meshes").mkdir(parents=True)
        fixed_gt_dir = tmp_path / "sal3d_fixed_face_gt"
        fixed_gt_dir.mkdir()
        fixation_root = tmp_path / "fixations"
        fixation_root.mkdir()

        monkeypatch.setattr(_mod, "resolve_dataset_root", lambda: dataset_root)
        monkeypatch.setattr(_mod, "resolve_fixation_root", lambda: fixation_root)

        result = inventory_models(
            None,
            csv_compat=False,
            fixed_gt_dir=fixed_gt_dir,
            sal3d_manifest=None,
        )
        assert result == []

    def test_nonexistent_fixed_gt_dir_raises(self, tmp_path, monkeypatch):
        """--fixed-gt-dir pointing to a missing directory raises RuntimeError."""
        missing_dir = tmp_path / "does_not_exist"
        with pytest.raises(RuntimeError, match="does not exist or is not a directory"):
            inventory_models(
                None,
                csv_compat=False,
                fixed_gt_dir=missing_dir,
                sal3d_manifest=None,
            )

    def test_manifest_bom_handled(self, tmp_path, monkeypatch):
        """sal3d_manifest.csv with UTF-8 BOM (Excel export) is parsed correctly."""
        models = ["bunny", "dragon"]
        dataset_root, fixed_gt_dir, fixation_root = _make_compact_pkg(tmp_path, models)

        manifest = tmp_path / "sal3d_manifest.csv"
        # Write with UTF-8 BOM — mimics Excel CSV export
        manifest.write_bytes(
            "﻿model,n_faces\nbunny,1234\ndragon,5678\n".encode("utf-8")
        )

        monkeypatch.setattr(_mod, "resolve_dataset_root", lambda: dataset_root)
        monkeypatch.setattr(_mod, "resolve_fixation_root", lambda: fixation_root)

        result = inventory_models(
            None,
            csv_compat=False,
            fixed_gt_dir=fixed_gt_dir,
            sal3d_manifest=manifest,
        )
        assert set(result) == set(models)


# ---------------------------------------------------------------------------
# Classic mode: ensure old behavior unchanged when fixed_gt_dir is None
# ---------------------------------------------------------------------------

class TestInventoryClassicMode:
    def test_classic_mode_uses_gaze_dir(self, tmp_path, monkeypatch):
        """Without --fixed-gt-dir, Gaze/*.txt drives model discovery."""
        dataset_root = tmp_path / "dataset"
        gaze_dir = dataset_root / "Gaze"
        gaze_dir.mkdir(parents=True)
        fixation_root = tmp_path / "fixations"

        for model in ["bunny", "dragon"]:
            (gaze_dir / f"{model}.txt").touch()
            fix_dir = fixation_root / f"SAL3D_{model}"
            fix_dir.mkdir(parents=True)
            (fix_dir / "fixations.json").touch()

        monkeypatch.setattr(_mod, "resolve_dataset_root", lambda: dataset_root)
        monkeypatch.setattr(_mod, "resolve_fixation_root", lambda: fixation_root)

        result = inventory_models(None, csv_compat=False, fixed_gt_dir=None)
        assert set(result) == {"bunny", "dragon"}

    def test_classic_mode_no_gaze_dir_raises(self, tmp_path, monkeypatch):
        """Without --fixed-gt-dir and without Gaze/, raises RuntimeError."""
        dataset_root = tmp_path / "dataset"
        dataset_root.mkdir()

        monkeypatch.setattr(_mod, "resolve_dataset_root", lambda: dataset_root)

        with pytest.raises(RuntimeError, match="Gaze directory not found"):
            inventory_models(None, csv_compat=False, fixed_gt_dir=None)
