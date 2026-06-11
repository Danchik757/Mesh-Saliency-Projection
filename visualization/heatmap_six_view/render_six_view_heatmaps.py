#!/usr/bin/env python3
"""
Six-view jet heatmap renderer — SAL3D, MeshMamba, and 3DVA.

For each selected model and map type (screen_space / cone / gt) renders six
canonical views (front / back / left / right / top / bottom) with the jet
colormap applied to mesh faces, normalises per-map to [0,1] via true min-max,
and writes per-view PNGs, a 2×3 per-map montage, and a 3×6 compare collage
(rows: gt / screen_space / cone;  cols: front…bottom).

Outputs per model: manifest.json entry, summary.csv row, per-view PNGs,
montage.png, compare_collage.png.

Map domain detection (hard error on mismatch):
  len(map) == n_faces   → face domain, use directly
  len(map) == n_verts   → vertex domain, convert to face by mean over face vertices
  otherwise             → ValueError

Manifest fields include: map_domain, n_map_elements, n_mesh_vertices,
n_mesh_faces, input_min, input_max, display_normalization, colormap,
mesh_path, map_path.

Usage — SAL3D smoke (alien2):

    python visualization/heatmap_six_view/render_six_view_heatmaps.py \\
        --dataset sal3d \\
        --models alien2 \\
        --metrics-root /mnt/ssd1/29d_kon/acm_2026/outputs/coordinator/rc3_full_metrics_20260611_004003/sal3d \\
        --dataset-root  $SAL3D_DATASET_ROOT \\
        --fixed-gt-dir  $SAL3D_FIXED_GT_DIR \\
        --output-root   /mnt/ssd1/29d_kon/acm_2026/outputs/heatmap_6view_smoke_20260611 \\
        --map-types screen_space cone gt

Usage — MeshMamba non_texture (Starfruit_L3):

    python visualization/heatmap_six_view/render_six_view_heatmaps.py \\
        --dataset meshmamba \\
        --texture-type non_texture \\
        --models Starfruit_L3 \\
        --metrics-root /mnt/ssd1/29d_kon/acm_2026/outputs/coordinator/rc3_full_metrics_20260611_004003/meshmamba \\
        --dataset-root  $MESHMAMBA_NON_TEXTURE_ROOT \\
        --output-root   /mnt/ssd1/29d_kon/acm_2026/outputs/heatmap_6view_smoke_20260611 \\
        --map-types screen_space cone gt

Usage — 3DVA (A380):

    python visualization/heatmap_six_view/render_six_view_heatmaps.py \\
        --dataset 3dva \\
        --models A380 \\
        --metrics-root /mnt/ssd1/29d_kon/acm_2026/outputs/coordinator/rc3_full_metrics_20260611_004003/3dva \\
        --dataset-root  $VISUAL_ATTENTION_3D_SHAPES_ROOT \\
        --combined-gt-dir $THREE_DVA_COMBINED_GT_DIR \\
        --output-root   /mnt/ssd1/29d_kon/acm_2026/outputs/heatmap_6view_smoke_20260611 \\
        --map-types screen_space cone gt
"""
from __future__ import annotations

import argparse
import csv
import datetime
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import numpy as np

# --- Optional imports guarded for tests / py_compile ---
_pyvista_error: Exception | None = None
_mpl_error: Exception | None = None
try:
    import pyvista as pv
except ImportError as _e:
    _pyvista_error = _e
    pv = None  # type: ignore[assignment]

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError as _e:
    _mpl_error = _e
    plt = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Constants — tag strings must match the batch-runner output directories
# ---------------------------------------------------------------------------

SAL3D_SCREEN_TAG   = "sigmapx26p3_recenter_rotx90p0_horizontaltovertical_blender_rig"
SAL3D_CONE_TAG     = "recenter_rotx90p0_horizontaltovertical_blender_rig"
MM_SCREEN_TAG      = "sigma0p05_recenter_rotx90p0_horizontaltovertical_blender_rig"
MM_CONE_TAG        = "recenter_rotx90p0_horizontaltovertical_blender_rig"
THREE_DVA_SCREEN_TAG = "sigpx49p0_recenter_fovh2v_combined"
THREE_DVA_CONE_TAG   = "recenter_fovh2v_combined"

VALID_MAP_TYPES = ("screen_space", "cone", "gt")
VALID_DATASETS  = ("sal3d", "meshmamba", "3dva")
VALID_TEXTURE   = ("non_texture", "rgb_texture")

# Canonical 6 orthographic camera directions: (cam_dir, up_vec)
# Y-up coordinate system (SAL3D, MeshMamba)
VIEWS_6 = {
    "front":  (( 0.0,  0.0,  1.0), (0.0,  1.0,  0.0)),
    "back":   (( 0.0,  0.0, -1.0), (0.0,  1.0,  0.0)),
    "left":   ((-1.0,  0.0,  0.0), (0.0,  1.0,  0.0)),
    "right":  (( 1.0,  0.0,  0.0), (0.0,  1.0,  0.0)),
    "top":    (( 0.0,  1.0,  0.0), (0.0,  0.0, -1.0)),
    "bottom": (( 0.0, -1.0,  0.0), (0.0,  0.0,  1.0)),
}

# Z-up coordinate system (3DVA — Blender native; Y = forward/depth, Z = up/height)
# Camera comes from -Y (in front of the object) for "front"; Z is the vertical axis.
VIEWS_6_Z_UP = {
    "front":  (( 0.0, -1.0,  0.0), (0.0,  0.0,  1.0)),
    "back":   (( 0.0,  1.0,  0.0), (0.0,  0.0,  1.0)),
    "left":   ((-1.0,  0.0,  0.0), (0.0,  0.0,  1.0)),
    "right":  (( 1.0,  0.0,  0.0), (0.0,  0.0,  1.0)),
    "top":    (( 0.0,  0.0,  1.0), (0.0, -1.0,  0.0)),
    "bottom": (( 0.0,  0.0, -1.0), (0.0, -1.0,  0.0)),
}

VIEW_ORDER = ["front", "back", "left", "right", "top", "bottom"]

# Datasets whose OBJ files use Blender Z-up coordinate convention
DATASETS_Z_UP = {"3dva"}

MAP_TYPE_DIR = {"screen_space": "screen_space", "cone": "cone", "gt": "gt"}


# ---------------------------------------------------------------------------
# OBJ parsing
# ---------------------------------------------------------------------------

def parse_obj(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Return (vertices [N,3], faces [M,3]) from a triangulated OBJ file."""
    vertices: list[list[float]] = []
    faces: list[list[int]] = []
    with open(path) as fh:
        for line in fh:
            if line.startswith("v "):
                parts = line.split()
                vertices.append([float(parts[1]), float(parts[2]), float(parts[3])])
            elif line.startswith("f "):
                parts = line.split()
                tri = [int(t.split("/")[0]) - 1 for t in parts[1:4]]
                if len(tri) == 3:
                    faces.append(tri)
    return np.array(vertices, dtype=np.float64), np.array(faces, dtype=np.int32)


# ---------------------------------------------------------------------------
# Map loading and normalisation
# ---------------------------------------------------------------------------

def load_and_prepare_map(
    map_path: Path,
    n_verts: int,
    n_faces: int,
    faces: np.ndarray,
) -> tuple[np.ndarray, float, float, str, int, bool, str | None]:
    """Load a saliency map file; detect domain; convert to face; normalise [0,1].

    Returns:
        values01        — per-face float32 normalised to [0, 1]
        input_min       — raw min before normalisation
        input_max       — raw max before normalisation
        domain          — "face" or "vertex"
        n_map_elements  — raw length of the loaded vector
        constant_map    — True when all values are identical
        warning         — human-readable warning or None
    """
    raw = np.loadtxt(map_path, dtype=np.float64)
    raw = np.where(np.isfinite(raw), raw, 0.0)
    n_map_elements = len(raw)

    if n_map_elements == n_faces:
        face_vals = raw
        domain = "face"
    elif n_map_elements == n_verts:
        face_vals = raw[faces].mean(axis=1)
        domain = "vertex"
    else:
        raise ValueError(
            f"Map length {n_map_elements} matches neither "
            f"n_faces={n_faces} nor n_verts={n_verts} for {map_path.name}"
        )

    input_min = float(np.min(face_vals))
    input_max = float(np.max(face_vals))

    if input_max > input_min:
        values01 = (face_vals - input_min) / (input_max - input_min)
        constant_map = False
        warning: str | None = None
    else:
        values01 = np.zeros(n_faces, dtype=np.float64)
        constant_map = True
        warning = f"Constant map (all values = {input_min:.6g}); rendered as all-zero/blue"

    return values01.astype(np.float32), input_min, input_max, domain, n_map_elements, constant_map, warning


# ---------------------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------------------

def _find_file_casefold(directory: Path, stem: str, suffix: str) -> Path | None:
    """Return the first file in *directory* whose lowercased name matches
    stem+suffix, with dash/underscore normalisation."""
    if not directory.is_dir():
        return None
    target_exact = (stem + suffix).lower()
    target_norm  = target_exact.replace("_", "-")
    for p in directory.iterdir():
        low = p.name.lower()
        if low == target_exact or low == target_norm:
            return p
    return None


# ---------------------------------------------------------------------------
# Dataset-specific path resolution
# ---------------------------------------------------------------------------

def resolve_obj_path(
    dataset: str,
    dataset_root: Path,
    model: str,
    texture_type: str | None,
) -> Path | None:
    """Return Path to the model OBJ, or None."""
    if dataset == "sal3d":
        mesh_dir = dataset_root / "Meshes"
        exact = mesh_dir / f"{model}.obj"
        if exact.exists():
            return exact
        return _find_file_casefold(mesh_dir, model, ".obj")
    if dataset == "meshmamba":
        assert texture_type is not None
        # OBJ lives inside a per-model subdirectory; the filename may differ
        # (e.g. Starfruit_L3/ contains Starfruit-L3.obj)
        model_subdir = dataset_root / "MeshFile" / texture_type / model
        if model_subdir.is_dir():
            objs = [p for p in model_subdir.iterdir() if p.suffix.lower() == ".obj"]
            return objs[0] if objs else None
        # flat fallback (shouldn't be needed)
        return _find_file_casefold(dataset_root / "MeshFile" / texture_type, model, ".obj")
    if dataset == "3dva":
        mesh_dir = dataset_root / "3DModels-Simplif-up"
        exact = mesh_dir / f"{model}.obj"
        if exact.exists():
            return exact
        return _find_file_casefold(mesh_dir, model, ".obj")
    return None


def resolve_map_paths(
    dataset: str,
    metrics_root: Path,
    dataset_root: Path,
    model: str,
    texture_type: str | None,
    fixed_gt_dir: Path | None,
    combined_gt_dir: Path | None,
    map_types: list[str],
) -> dict[str, Path | None]:
    """Return {map_type: Path | None} for the requested map types."""
    paths: dict[str, Path | None] = {}

    if dataset == "sal3d":
        if "screen_space" in map_types:
            p = (metrics_root / "baseline_screen_space" / model
                 / SAL3D_SCREEN_TAG / f"{model}_screen_space_vertices.txt")
            paths["screen_space"] = p if p.exists() else None
        if "cone" in map_types:
            p = (metrics_root / "baseline_cone" / model
                 / SAL3D_CONE_TAG / f"{model}_cone_vertices.txt")
            paths["cone"] = p if p.exists() else None
        if "gt" in map_types:
            if fixed_gt_dir is not None:
                p = fixed_gt_dir / f"{model}_faces.txt"
                if not p.exists():
                    p = _find_file_casefold(fixed_gt_dir, model, "_faces.txt") or p
                paths["gt"] = p if p.exists() else None
            else:
                paths["gt"] = None

    elif dataset == "meshmamba":
        assert texture_type is not None
        tt = texture_type
        if "screen_space" in map_types:
            p = (metrics_root / tt / "baseline_screen_space" / model
                 / MM_SCREEN_TAG / f"{model}_screen_space_faces.txt")
            paths["screen_space"] = p if p.exists() else None
        if "cone" in map_types:
            p = (metrics_root / tt / "baseline_cone" / model
                 / MM_CONE_TAG / f"{model}_cone_faces.txt")
            paths["cone"] = p if p.exists() else None
        if "gt" in map_types:
            gt_dir = dataset_root / "SaliencyMap" / tt
            paths["gt"] = _find_file_casefold(gt_dir, model, ".csv")

    elif dataset == "3dva":
        if "screen_space" in map_types:
            p = (metrics_root / "baseline_screen_space" / model
                 / THREE_DVA_SCREEN_TAG
                 / f"{model}_screen_space_combined_vertices.txt")
            paths["screen_space"] = p if p.exists() else None
        if "cone" in map_types:
            p = (metrics_root / "baseline_cone" / model
                 / THREE_DVA_CONE_TAG / f"{model}_cone_norm.txt")
            paths["cone"] = p if p.exists() else None
        if "gt" in map_types:
            if combined_gt_dir is not None:
                p = combined_gt_dir / f"{model}_combined_gt.txt"
                if not p.exists():
                    p = _find_file_casefold(combined_gt_dir, model, "_combined_gt.txt") or p
                paths["gt"] = p if p.exists() else None
            else:
                paths["gt"] = None

    return paths


# ---------------------------------------------------------------------------
# Model discovery
# ---------------------------------------------------------------------------

def discover_models(
    dataset: str,
    metrics_root: Path,
    texture_type: str | None,
) -> list[str]:
    """Return sorted list of model names that have a screen_space output dir."""
    if dataset == "sal3d":
        ss_root = metrics_root / "baseline_screen_space"
    elif dataset == "meshmamba":
        assert texture_type is not None
        ss_root = metrics_root / texture_type / "baseline_screen_space"
    else:  # 3dva
        ss_root = metrics_root / "baseline_screen_space"

    if not ss_root.is_dir():
        raise RuntimeError(f"baseline_screen_space not found: {ss_root}")
    return sorted(p.name for p in ss_root.iterdir() if p.is_dir())


# ---------------------------------------------------------------------------
# PyVista rendering
# ---------------------------------------------------------------------------

def _build_pyvista_mesh(
    vertices: np.ndarray,
    faces: np.ndarray,
    face_vals01: np.ndarray,
) -> "pv.PolyData":
    pv_faces = np.hstack(
        [np.full((len(faces), 1), 3, dtype=np.int32), faces]
    )
    mesh = pv.PolyData(vertices.astype(np.float32), pv_faces.ravel())
    mesh.cell_data["saliency"] = face_vals01.astype(np.float32)
    return mesh


def render_six_views(
    vertices: np.ndarray,
    faces: np.ndarray,
    face_vals01: np.ndarray,
    out_dir: Path,
    colormap: str = "jet",
    views: dict | None = None,
) -> dict[str, Path]:
    """Render 6 canonical views, save PNGs.  Returns {view_name: Path}.

    views: camera dict to use; defaults to VIEWS_6 (Y-up).
           Pass VIEWS_6_Z_UP for Blender Z-up datasets (e.g. 3DVA).
    """
    if pv is None:
        raise ImportError(f"pyvista required for rendering: {_pyvista_error}")

    os.environ.setdefault("DISPLAY", "")
    pv.OFF_SCREEN = True

    active_views = views if views is not None else VIEWS_6
    pv_mesh = _build_pyvista_mesh(vertices, faces, face_vals01)
    center   = np.array(pv_mesh.center)
    distance = pv_mesh.length * 0.9

    out_dir.mkdir(parents=True, exist_ok=True)
    image_paths: dict[str, Path] = {}

    for view_name, (cam_dir, up_vec) in active_views.items():
        pl = pv.Plotter(off_screen=True, window_size=(800, 800))
        pl.set_background("white")
        pl.add_mesh(
            pv_mesh,
            scalars="saliency",
            cmap=colormap,
            clim=[0.0, 1.0],
            show_scalar_bar=False,
            smooth_shading=False,
        )
        pl.camera.position = (center + np.array(cam_dir) * distance).tolist()
        pl.camera.focal_point = center.tolist()
        pl.camera.up = up_vec
        pl.reset_camera()

        png_path = out_dir / f"{view_name}.png"
        pl.screenshot(str(png_path))
        pl.close()
        image_paths[view_name] = png_path

    return image_paths


# ---------------------------------------------------------------------------
# Montage and compare collage
# ---------------------------------------------------------------------------

def make_montage(
    image_paths: dict[str, Path],
    title: str,
    out_path: Path,
) -> None:
    """Write a 2×3 montage of the six views with labels."""
    if plt is None:
        raise ImportError(f"matplotlib required: {_mpl_error}")

    fig, axes = plt.subplots(2, 3, figsize=(15, 10), facecolor="#111111")
    fig.suptitle(title, color="white", fontsize=13, fontweight="bold")

    for idx, view_name in enumerate(VIEW_ORDER):
        row, col = divmod(idx, 3)
        ax = axes[row, col]
        if view_name in image_paths and image_paths[view_name].exists():
            ax.imshow(plt.imread(str(image_paths[view_name])))
        else:
            ax.set_facecolor("#222222")
        ax.set_title(view_name, color="white", fontsize=11, pad=4)
        ax.axis("off")

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(out_path), dpi=150, bbox_inches="tight", facecolor="#111111")
    plt.close(fig)


_ROW_LABELS = {
    "gt":           "Ground\nTruth",
    "screen_space": "Screen\nSpace",
    "cone":         "Cone",
}


def _cbar_fmt(vmin: float, vmax: float) -> str:
    """Pick a printf-style format string based on value span."""
    span = abs(vmax - vmin) if vmax != vmin else 1e-10
    if span < 0.001:
        return "{:.2e}"
    if span < 0.1:
        return "{:.4f}"
    if span < 10:
        return "{:.3f}"
    if span < 1000:
        return "{:.1f}"
    return "{:.0f}"


def make_compare_collage(
    per_type_image_paths: dict[str, dict[str, Path]],
    per_type_ranges: dict[str, tuple[float, float]],
    title: str,
    out_path: Path,
) -> None:
    """Write a 3×6 compare collage with method labels (left) and colorbars (right).

    per_type_image_paths : {map_type: {view_name: Path}}
    per_type_ranges      : {map_type: (input_min, input_max)}
    Rows: gt / screen_space / cone (whichever are present).
    Cols: front / back / left / right / top / bottom.
    """
    if plt is None:
        raise ImportError(f"matplotlib required: {_mpl_error}")

    import matplotlib.gridspec as gridspec
    import matplotlib.cm as cm
    import matplotlib.colors as mcolors

    row_order = [mt for mt in ("gt", "screen_space", "cone")
                 if mt in per_type_image_paths]
    if not row_order:
        return

    n_rows = len(row_order)
    n_cols = len(VIEW_ORDER)

    # Layout: [label | img×6 | colorbar]
    label_w = 0.55
    img_w   = 1.0
    cbar_w  = 0.18

    fig = plt.figure(
        figsize=((label_w + n_cols * img_w + cbar_w) * 2.8, n_rows * 3.0 + 0.55),
        facecolor="#111111",
    )
    fig.suptitle(title, color="white", fontsize=12, fontweight="bold", y=0.99)

    gs = gridspec.GridSpec(
        n_rows, n_cols + 2,
        width_ratios=[label_w] + [img_w] * n_cols + [cbar_w],
        hspace=0.04, wspace=0.04,
        left=0.01, right=0.99, top=0.94, bottom=0.02,
    )

    for r, map_type in enumerate(row_order):
        # left label
        lax = fig.add_subplot(gs[r, 0])
        lax.set_facecolor("#111111")
        lax.axis("off")
        lax.text(
            0.5, 0.5, _ROW_LABELS.get(map_type, map_type),
            color="white", fontsize=11, fontweight="bold",
            ha="center", va="center", rotation=90,
            transform=lax.transAxes,
        )

        # image cells
        img_paths = per_type_image_paths[map_type]
        for c, view_name in enumerate(VIEW_ORDER):
            ax = fig.add_subplot(gs[r, c + 1])
            p = img_paths.get(view_name)
            if p is not None and p.exists():
                ax.imshow(plt.imread(str(p)))
            else:
                ax.set_facecolor("#222222")
            if r == 0:
                ax.set_title(view_name, color="white", fontsize=9, pad=3)
            ax.axis("off")

        # right colorbar
        vmin, vmax = per_type_ranges.get(map_type, (0.0, 1.0))
        cbar_ax = fig.add_subplot(gs[r, n_cols + 1])
        sm = cm.ScalarMappable(
            cmap="jet",
            norm=mcolors.Normalize(vmin=vmin, vmax=vmax),
        )
        sm.set_array([])
        cb = fig.colorbar(sm, cax=cbar_ax)
        cb.ax.yaxis.set_tick_params(color="white", labelcolor="white", labelsize=7)
        for spine in cb.ax.spines.values():
            spine.set_edgecolor("#888888")
        fmt = _cbar_fmt(vmin, vmax)
        ticks = np.linspace(vmin, vmax, 5)
        cb.set_ticks(ticks)
        cb.set_ticklabels([fmt.format(t) for t in ticks])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(out_path), dpi=150, bbox_inches="tight", facecolor="#111111")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Output path helpers
# ---------------------------------------------------------------------------

def _model_map_dir(
    output_root: Path,
    dataset: str,
    texture_type: str | None,
    model: str,
    map_type: str,
) -> Path:
    subdir = MAP_TYPE_DIR[map_type]
    if dataset == "sal3d":
        return output_root / "SAL3D" / model / subdir
    if dataset == "3dva":
        return output_root / "3DVA" / model / subdir
    return output_root / "MeshMamba" / (texture_type or "") / model / subdir


def _model_compare_dir(
    output_root: Path,
    dataset: str,
    texture_type: str | None,
    model: str,
) -> Path:
    if dataset == "sal3d":
        return output_root / "SAL3D" / model
    if dataset == "3dva":
        return output_root / "3DVA" / model
    return output_root / "MeshMamba" / (texture_type or "") / model


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


# ---------------------------------------------------------------------------
# Per-model processing
# ---------------------------------------------------------------------------

def process_model(
    model: str,
    dataset: str,
    texture_type: str | None,
    metrics_root: Path,
    dataset_root: Path,
    fixed_gt_dir: Path | None,
    combined_gt_dir: Path | None,
    output_root: Path,
    map_types: list[str],
    colormap: str,
    commit_hash: str,
    hostname: str,
) -> list[dict]:
    """Process one model across all requested map types.

    Returns list of summary rows (one per map type) plus a special
    "_compare_collage" row if the compare collage was written.
    """
    rows: list[dict] = []
    created_at = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"

    obj_path = resolve_obj_path(dataset, dataset_root, model, texture_type)
    if obj_path is None or not obj_path.exists():
        for mt in map_types:
            rows.append(_error_row(dataset, texture_type, model, mt,
                                   f"OBJ not found for model '{model}'"))
        return rows

    try:
        vertices, faces = parse_obj(obj_path)
    except Exception as exc:
        for mt in map_types:
            rows.append(_error_row(dataset, texture_type, model, mt,
                                   f"OBJ parse error: {exc}"))
        return rows

    n_verts = len(vertices)
    n_faces = len(faces)

    map_paths = resolve_map_paths(
        dataset, metrics_root, dataset_root, model, texture_type,
        fixed_gt_dir, combined_gt_dir, map_types,
    )

    views_dict = VIEWS_6_Z_UP if dataset in DATASETS_Z_UP else VIEWS_6
    per_type_image_paths: dict[str, dict[str, Path]] = {}
    per_type_ranges:      dict[str, tuple[float, float]] = {}

    for map_type in map_types:
        map_path = map_paths.get(map_type)
        out_dir = _model_map_dir(output_root, dataset, texture_type, model, map_type)
        montage_path = out_dir / "montage.png"

        base_row: dict = {
            "dataset":         dataset,
            "texture_type":    texture_type or "",
            "model":           model,
            "map_type":        map_type,
            "mesh_path":       str(obj_path),
            "map_path":        str(map_path) if map_path else "",
            **{v: "" for v in VIEW_ORDER},
            "montage": "",
        }

        if map_path is None or not map_path.exists():
            reason = (
                "GT map requires --fixed-gt-dir" if map_type == "gt" and fixed_gt_dir is None and dataset == "sal3d"
                else "GT map requires --combined-gt-dir" if map_type == "gt" and combined_gt_dir is None and dataset == "3dva"
                else f"map file not found: {map_path}"
            )
            rows.append({**base_row, "status": "skip", "error_message": reason})
            continue

        try:
            vals01, vmin, vmax, domain, n_map_elements, constant_map, warning = \
                load_and_prepare_map(map_path, n_verts, n_faces, faces)
        except Exception as exc:
            rows.append({**base_row, "status": "error", "error_message": str(exc)})
            continue

        try:
            image_paths = render_six_views(vertices, faces, vals01, out_dir,
                                           colormap, views=views_dict)
        except Exception as exc:
            rows.append({**base_row, "status": "error",
                         "error_message": f"render error: {exc}"})
            continue

        title = f"{dataset.upper()}"
        if texture_type:
            title += f" {texture_type}"
        title += f" | {model} | {map_type}"
        try:
            make_montage(image_paths, title, montage_path)
        except Exception as exc:
            rows.append({**base_row, "status": "error",
                         "error_message": f"montage error: {exc}"})
            continue

        per_type_image_paths[map_type] = image_paths
        per_type_ranges[map_type]      = (vmin, vmax)

        manifest_entry = {
            "dataset":               dataset,
            "texture_type":          texture_type,
            "model":                 model,
            "map_type":              map_type,
            "mesh_path":             str(obj_path),
            "map_path":              str(map_path),
            "map_domain":            domain,
            "n_map_elements":        n_map_elements,
            "n_mesh_vertices":       n_verts,
            "n_mesh_faces":          n_faces,
            "input_min":             vmin,
            "input_max":             vmax,
            "display_normalization": "minmax_per_map",
            "colormap":              colormap,
            "constant_map":          constant_map,
            "constant_map_warning":  warning,
            "views":                 {k: _rel(v, output_root)
                                      for k, v in image_paths.items()},
            "montage":               _rel(montage_path, output_root),
            "status":                "ok",
            "commit_hash":           commit_hash,
            "server_hostname":       hostname,
            "created_at":            created_at,
        }

        row = {
            **base_row,
            "status":        "ok",
            "error_message": warning or "",
            "montage":       _rel(montage_path, output_root),
        }
        for view_name, vpath in image_paths.items():
            row[view_name] = _rel(vpath, output_root)
        row["_manifest_entry"] = manifest_entry
        rows.append(row)

    # --- Compare collage across map types ---
    if per_type_image_paths:
        compare_dir = _model_compare_dir(output_root, dataset, texture_type, model)
        compare_path = compare_dir / "compare_collage.png"
        collage_title = f"{dataset.upper()}"
        if texture_type:
            collage_title += f" {texture_type}"
        collage_title += f" | {model} | gt / screen_space / cone"
        try:
            make_compare_collage(per_type_image_paths, per_type_ranges,
                                 collage_title, compare_path)
            rows.append({
                "dataset": dataset, "texture_type": texture_type or "",
                "model": model, "map_type": "_compare_collage",
                "status": "ok", "error_message": "",
                "mesh_path": str(obj_path), "map_path": "",
                **{v: "" for v in VIEW_ORDER},
                "montage": _rel(compare_path, output_root),
                "_compare_collage_path": str(compare_path),
            })
        except Exception as exc:
            rows.append({
                "dataset": dataset, "texture_type": texture_type or "",
                "model": model, "map_type": "_compare_collage",
                "status": "error", "error_message": f"collage error: {exc}",
                "mesh_path": "", "map_path": "",
                **{v: "" for v in VIEW_ORDER},
                "montage": "",
            })

    return rows


def _error_row(dataset, texture_type, model, map_type, message) -> dict:
    return {
        "dataset":       dataset,
        "texture_type":  texture_type or "",
        "model":         model,
        "map_type":      map_type,
        "status":        "error",
        "error_message": message,
        "mesh_path": "", "map_path": "",
        **{v: "" for v in VIEW_ORDER},
        "montage": "",
    }


# ---------------------------------------------------------------------------
# Manifest and summary CSV
# ---------------------------------------------------------------------------

def write_manifest(entries: list[dict], output_root: Path) -> Path:
    manifest_path = output_root / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w") as fh:
        json.dump(entries, fh, indent=2)
    return manifest_path


def write_summary_csv(rows: list[dict], output_root: Path) -> Path:
    csv_path = output_root / "summary.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "dataset", "texture_type", "model", "map_type",
        "status", "error_message",
        "mesh_path", "map_path",
        *VIEW_ORDER,
        "montage",
    ]
    with open(csv_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})
    return csv_path


# ---------------------------------------------------------------------------
# Git commit hash
# ---------------------------------------------------------------------------

def _git_commit_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description="Render six-view jet heatmaps for SAL3D, MeshMamba, or 3DVA."
    )
    ap.add_argument("--dataset", required=True, choices=VALID_DATASETS)
    ap.add_argument("--texture-type", choices=VALID_TEXTURE, default=None,
                    help="Required for --dataset meshmamba")
    ap.add_argument("--metrics-root", type=Path, required=True,
                    help="Dataset-level metrics root "
                         "(e.g. .../rc3_full_metrics/sal3d  or .../meshmamba  or .../3dva)")
    ap.add_argument("--dataset-root", type=Path, required=True,
                    help="Dataset root (OBJs + MeshMamba GT CSVs + 3DVA model subdirs)")
    ap.add_argument("--fixed-gt-dir", type=Path, default=None,
                    help="SAL3D: dir with <model>_faces.txt fixed-face GT files")
    ap.add_argument("--combined-gt-dir", type=Path, default=None,
                    help="3DVA: dir with <model>_combined_gt.txt GT files")
    ap.add_argument("--output-root", type=Path, required=True)
    ap.add_argument("--models", nargs="+", default=None,
                    help="Explicit model list (skips auto-discovery)")
    ap.add_argument("--limit", type=int, default=None,
                    help="Limit number of models (for preview)")
    ap.add_argument("--map-types", nargs="+",
                    default=["screen_space", "cone", "gt"],
                    choices=VALID_MAP_TYPES)
    ap.add_argument("--colormap", default="jet")
    return ap.parse_args(argv)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv=None):
    if _pyvista_error is not None:
        print(f"[ERROR] pyvista not available: {_pyvista_error}", file=sys.stderr)
        sys.exit(1)
    if _mpl_error is not None:
        print(f"[ERROR] matplotlib not available: {_mpl_error}", file=sys.stderr)
        sys.exit(1)

    args = parse_args(argv)

    if args.dataset == "meshmamba" and args.texture_type is None:
        print("[ERROR] --texture-type required for --dataset meshmamba", file=sys.stderr)
        sys.exit(1)

    for flag, path in [("--metrics-root", args.metrics_root),
                       ("--dataset-root",  args.dataset_root)]:
        if not path.is_dir():
            print(f"[ERROR] {flag} not found: {path}", file=sys.stderr)
            sys.exit(1)
    if args.fixed_gt_dir is not None and not args.fixed_gt_dir.is_dir():
        print(f"[ERROR] --fixed-gt-dir not found: {args.fixed_gt_dir}", file=sys.stderr)
        sys.exit(1)
    if args.combined_gt_dir is not None and not args.combined_gt_dir.is_dir():
        print(f"[ERROR] --combined-gt-dir not found: {args.combined_gt_dir}", file=sys.stderr)
        sys.exit(1)

    if args.models:
        models = list(args.models)
    else:
        models = discover_models(args.dataset, args.metrics_root, args.texture_type)
    if args.limit is not None:
        models = models[: args.limit]
    if not models:
        print("[WARN] No models to process.", file=sys.stderr)
        return

    commit_hash = _git_commit_hash()
    hostname    = socket.gethostname()
    map_types   = list(args.map_types)

    print(
        f"[INFO] dataset={args.dataset}  texture={args.texture_type or '-'}  "
        f"models={len(models)}  map_types={map_types}  colormap={args.colormap}",
        flush=True,
    )
    print(f"[INFO] output_root: {args.output_root}", flush=True)

    all_rows: list[dict] = []
    manifest_entries: list[dict] = []
    collage_paths: list[str] = []

    for idx, model in enumerate(models, 1):
        print(f"[{idx}/{len(models)}] {model} ...", flush=True)
        rows = process_model(
            model=model,
            dataset=args.dataset,
            texture_type=args.texture_type,
            metrics_root=args.metrics_root,
            dataset_root=args.dataset_root,
            fixed_gt_dir=args.fixed_gt_dir,
            combined_gt_dir=args.combined_gt_dir,
            output_root=args.output_root,
            map_types=map_types,
            colormap=args.colormap,
            commit_hash=commit_hash,
            hostname=hostname,
        )
        for row in rows:
            entry = row.pop("_manifest_entry", None)
            if entry is not None:
                manifest_entries.append(entry)
            collage = row.pop("_compare_collage_path", None)
            if collage:
                collage_paths.append(collage)
            all_rows.append(row)
            status = row.get("status", "?")
            msg    = row.get("error_message", "")
            print(
                f"    {row['map_type']:18s}  {status}"
                + (f"  ({msg})" if msg else ""),
                flush=True,
            )

    manifest_path = write_manifest(manifest_entries, args.output_root)
    csv_path      = write_summary_csv(all_rows, args.output_root)

    ok_count   = sum(1 for r in all_rows if r.get("status") == "ok")
    skip_count = sum(1 for r in all_rows if r.get("status") == "skip")
    err_count  = sum(1 for r in all_rows if r.get("status") == "error")

    print(
        f"\n[DONE] {ok_count} ok  {skip_count} skipped  {err_count} errors"
        f"  →  {manifest_path.name}  {csv_path.name}",
        flush=True,
    )
    if collage_paths:
        print("[DONE] compare collages:", flush=True)
        for cp in collage_paths:
            print(f"  {cp}", flush=True)


if __name__ == "__main__":
    main()
