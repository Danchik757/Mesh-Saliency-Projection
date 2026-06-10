"""
Utility for loading per-face fixed GT from the SAL3D benchmark package.

The fixed GT package layout:
    sal3d_fixed_face_gt/<model>_faces.txt  — one float per line, len == n_faces
    sal3d_manifest.csv                     — model metadata (optional)

The fixed GT was produced by the SAL3D data-preparation pipeline:
  raw Gaze → smooth → KDTree-transfer to repaired OBJ vertices → face-average
  → min-max normalise → sal3d_fixed_face_gt/<model>_faces.txt
"""
from __future__ import annotations

from pathlib import Path

import numpy as np


def _candidate_model_names(model: str) -> list[str]:
    raw = model.strip()
    variants = [raw, raw.lower(), raw.upper(),
                raw.replace("_", "-"), raw.replace("-", "_")]
    deduped: list[str] = []
    seen: set[str] = set()
    for v in variants:
        if v.lower() not in seen:
            deduped.append(v)
            seen.add(v.lower())
    return deduped


def load_fixed_face_gt(
    fixed_gt_dir: Path, model: str, n_faces: int
) -> tuple[np.ndarray, Path]:
    """Load per-face fixed GT from sal3d_fixed_face_gt/<model>_faces.txt.

    Args:
        fixed_gt_dir: Directory containing <model>_faces.txt files.
        model:        Model name (case-insensitive lookup tried).
        n_faces:      Expected number of faces; validated against file length.

    Returns:
        (gt, path): gt is (n_faces,) float64 array in [0, 1]; path is the file used.

    Raises:
        FileNotFoundError: if no matching <model>_faces.txt is found.
        ValueError:         if len(gt) != n_faces.
    """
    candidates = _candidate_model_names(model)
    gt_path: Path | None = None
    for name in candidates:
        path = fixed_gt_dir / f"{name}_faces.txt"
        if path.exists():
            gt_path = path
            break
    if gt_path is None:
        raise FileNotFoundError(
            f"Fixed face GT not found for '{model}' in {fixed_gt_dir}"
        )
    gt = np.loadtxt(gt_path)
    if len(gt) != n_faces:
        raise ValueError(
            f"Fixed GT length {len(gt)} != n_faces {n_faces} for model '{model}'"
        )
    return gt, gt_path
