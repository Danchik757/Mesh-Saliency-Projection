#!/usr/bin/env python3
"""
Six-view jet heatmap renderer for SAL3D and MeshMamba.

For each selected model and map type (screen_space / cone / gt) renders six
canonical views (front / back / left / right / top / bottom) with the jet
colormap applied directly to mesh faces, normalises per-map to [0,1] via true
min-max (not percentile), and writes per-view PNGs plus a 2x3 montage.

Outputs: manifest.json, summary.csv, per-PNG images.

Usage — SAL3D (few preview models):

    python visualization/heatmap_six_view/render_six_view_heatmaps.py \\
        --dataset sal3d \\
        --metrics-root /mnt/ssd1/.../outputs/coordinator/rc2_smoke_20260610_122103 \\
        --dataset-root  $SAL3D_DATASET_ROOT \\
        --fixed-gt-dir  /path/to/sal3d_fixed_face_gt \\
        --output-root   /mnt/ssd1/.../outputs/coordinator/heatmaps_6view_20260609 \\
        --limit 3 \\
        --map-types screen_space cone gt

Usage — MeshMamba:

    python visualization/heatmap_six_view/render_six_view_heatmaps.py \\
        --dataset meshmamba \\
        --texture-type non_texture \\
        --metrics-root  /mnt/ssd1/.../outputs/coordinator/full_20260609/MeshMamba \\
        --dataset-root  $MESHMAMBA_NON_TEXTURE_ROOT \\
        --output-root   /mnt/ssd1/.../outputs/coordinator/heatmaps_6view_20260609 \\
        --limit 10 \\
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

# --- Optional imports (PyVista + Matplotlib) guarded for tests / py_compile ---
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
# Constants — must match the batch-runner tags exactly
# ---------------------------------------------------------------------------

SAL3D_SCREEN_TAG = "sigmapx26p3_recenter_rotx90p0_horizontaltovertical_blender_rig"
SAL3D_CONE_TAG   = "recenter_rotx90p0_horizontaltovertical_blender_rig"
MM_SCREEN_TAG    = "sigma0p05_recenter_rotx90p0_horizontaltovertical_blender_rig"
MM_CONE_TAG      = "recenter_rotx90p0_horizontaltovertical_blender_rig"

VALID_MAP_TYPES  = ("screen_space", "cone", "gt")
VALID_DATASETS   = ("sal3d", "meshmamba")
VALID_TEXTURE    = ("non_texture", "rgb_texture")

# Canonical 6 orthographic camera directions
# (camera_direction, up_vector) — camera placed at center + direction * distance
VIEWS_6 = {
    "front":  (( 0.0,  0.0,  1.0), (0.0,  1.0,  0.0)),
    "back":   (( 0.0,  0.0, -1.0), (0.0,  1.0,  0.0)),
    "left":   ((-1.0,  0.0,  0.0), (0.0,  1.0,  0.0)),
    "right":  (( 1.0,  0.0,  0.0), (0.0,  1.0,  0.0)),
    "top":    (( 0.0,  1.0,  0.0), (0.0,  0.0, -1.0)),
    "bottom": (( 0.0, -1.0,  0.0), (0.0,  0.0,  1.0)),
}

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
# Map loading and normalization
# ---------------------------------------------------------------------------

def load_and_prepare_map(
    map_path: Path,
    n_verts: int,
    n_faces: int,
    faces: np.ndarray,
) -> tuple[np.ndarray, float, float, str, bool, str | None]:
    """Load a saliency map, detect domain, convert to face, normalise to [0,1].

    Returns:
        values01        — per-face float32 array normalised to [0, 1]
        input_min       — raw minimum before normalisation
        input_max       — raw maximum before normalisation
        domain          — "face" or "vertex"
        constant_map    — True when all values are identical
        warning         — human-readable warning string or None
    """
    raw = np.loadtxt(map_path, dtype=np.float64)
    # Replace non-finite values with 0 before any computation
    raw = np.where(np.isfinite(raw), raw, 0.0)

    if len(raw) == n_faces:
        face_vals = raw
        domain = "face"
    elif len(raw) == n_verts:
        face_vals = raw[faces].mean(axis=1)
        domain = "vertex"
    else:
        raise ValueError(
            f"Map length {len(raw)} matches neither n_faces={n_faces} "
            f"nor n_verts={n_verts} for {map_path.name}"
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

    return values01.astype(np.float32), input_min, input_max, domain, constant_map, warning


# ---------------------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------------------

def _find_file_casefold(directory: Path, stem: str, suffix: str) -> Path | None:
    """Return the first file in *directory* whose lowercased name matches stem+suffix."""
    if not directory.is_dir():
        return None
    target = (stem + suffix).lower()
    for p in directory.iterdir():
        if p.name.lower() == target:
            return p
    return None


# ---------------------------------------------------------------------------
# Dataset-specific path resolution
# ---------------------------------------------------------------------------

def resolve_obj_path(dataset: str, dataset_root: Path, model: str,
                     texture_type: str | None) -> Path | None:
    """Return Path to the model OBJ (case-insensitive lookup), or None."""
    if dataset == "sal3d":
        mesh_dir = dataset_root / "Meshes"
        exact = mesh_dir / f"{model}.obj"
        if exact.exists():
            return exact
        return _find_file_casefold(mesh_dir, model, ".obj")
    if dataset == "meshmamba":
        assert texture_type is not None
        mesh_dir = dataset_root / "MeshFile" / texture_type
        return _find_file_casefold(mesh_dir, model, ".obj")
    return None


def resolve_map_paths(
    dataset: str,
    metrics_root: Path,
    dataset_root: Path,
    model: str,
    texture_type: str | None,
    fixed_gt_dir: Path | None,
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
                # Case-insensitive fallback for oddly-cased model names
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

    return paths


# ---------------------------------------------------------------------------
# Model discovery
# ---------------------------------------------------------------------------

def discover_models(dataset: str, metrics_root: Path,
                    texture_type: str | None) -> list[str]:
    """Return sorted list of model names that have a screen_space output dir."""
    if dataset == "sal3d":
        ss_root = metrics_root / "baseline_screen_space"
    else:
        assert texture_type is not None
        ss_root = metrics_root / texture_type / "baseline_screen_space"

    if not ss_root.is_dir():
        raise RuntimeError(
            f"baseline_screen_space directory not found: {ss_root}"
        )
    return sorted(p.name for p in ss_root.iterdir() if p.is_dir())


# ---------------------------------------------------------------------------
# PyVista rendering
# ---------------------------------------------------------------------------

def _build_pyvista_mesh(vertices: np.ndarray, faces: np.ndarray,
                         face_vals01: np.ndarray) -> "pv.PolyData":
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
) -> dict[str, Path]:
    """Render 6 canonical views and save individual PNGs.  Returns {view: Path}."""
    if pv is None:
        raise ImportError(f"pyvista is required for rendering: {_pyvista_error}")

    os.environ.setdefault("DISPLAY", "")
    pv.OFF_SCREEN = True

    pv_mesh = _build_pyvista_mesh(vertices, faces, face_vals01)
    center = np.array(pv_mesh.center)
    distance = pv_mesh.length * 0.9

    out_dir.mkdir(parents=True, exist_ok=True)
    image_paths: dict[str, Path] = {}

    for view_name, (cam_dir, up_vec) in VIEWS_6.items():
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
# Montage (2×3 grid)
# ---------------------------------------------------------------------------

def make_montage(
    image_paths: dict[str, Path],
    title: str,
    out_path: Path,
) -> None:
    """Write a 2×3 montage of the six views with labels."""
    if plt is None:
        raise ImportError(f"matplotlib is required for montage: {_mpl_error}")

    view_order = ["front", "back", "left", "right", "top", "bottom"]
    fig, axes = plt.subplots(2, 3, figsize=(15, 10), facecolor="#111111")
    fig.suptitle(title, color="white", fontsize=13, fontweight="bold")

    for idx, view_name in enumerate(view_order):
        row, col = divmod(idx, 3)
        ax = axes[row, col]
        if view_name in image_paths and image_paths[view_name].exists():
            img = plt.imread(str(image_paths[view_name]))
            ax.imshow(img)
        else:
            ax.set_facecolor("#222222")
        ax.set_title(view_name, color="white", fontsize=11, pad=4)
        ax.axis("off")

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(out_path), dpi=150, bbox_inches="tight", facecolor="#111111")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Output path helpers
# ---------------------------------------------------------------------------

def _model_map_dir(output_root: Path, dataset: str, texture_type: str | None,
                   model: str, map_type: str) -> Path:
    subdir = MAP_TYPE_DIR[map_type]
    if dataset == "sal3d":
        return output_root / "SAL3D" / model / subdir
    return output_root / "MeshMamba" / (texture_type or "") / model / subdir


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
    output_root: Path,
    map_types: list[str],
    colormap: str,
    commit_hash: str,
    hostname: str,
) -> list[dict]:
    """Process one model across all requested map types.

    Returns a list of summary rows (one per map type).
    """
    rows: list[dict] = []
    created_at = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"

    # --- Load mesh once ---
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

    # --- Resolve map file paths ---
    map_paths = resolve_map_paths(
        dataset, metrics_root, dataset_root, model, texture_type,
        fixed_gt_dir, map_types,
    )

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
            "front":  "", "back":  "", "left":  "",
            "right":  "", "top":   "", "bottom": "",
            "montage": "",
        }

        # --- Missing map file ---
        if map_path is None or not map_path.exists():
            reason = (
                "GT map requires --fixed-gt-dir" if map_type == "gt" and fixed_gt_dir is None
                else f"map file not found: {map_path}"
            )
            rows.append({**base_row, "status": "skip", "error_message": reason})
            continue

        # --- Load and normalise ---
        try:
            vals01, vmin, vmax, domain, constant_map, warning = load_and_prepare_map(
                map_path, n_verts, n_faces, faces
            )
        except Exception as exc:
            rows.append({**base_row, "status": "error", "error_message": str(exc)})
            continue

        # --- Render six views ---
        try:
            image_paths = render_six_views(vertices, faces, vals01, out_dir, colormap)
        except Exception as exc:
            rows.append({**base_row, "status": "error",
                         "error_message": f"render error: {exc}"})
            continue

        # --- Montage ---
        title = f"{dataset.upper()} | {model} | {map_type}"
        if texture_type:
            title = f"{dataset.upper()} {texture_type} | {model} | {map_type}"
        try:
            make_montage(image_paths, title, montage_path)
        except Exception as exc:
            rows.append({**base_row, "status": "error",
                         "error_message": f"montage error: {exc}"})
            continue

        # --- Manifest entry (returned via row for caller to collect) ---
        manifest_entry = {
            "dataset":               dataset,
            "texture_type":          texture_type,
            "model":                 model,
            "map_type":              map_type,
            "mesh_path":             str(obj_path),
            "map_path":              str(map_path),
            "gt_path":               (str(map_paths.get("gt")) if map_type != "gt"
                                      and map_paths.get("gt") else None),
            "map_domain":            domain,
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

    return rows


def _error_row(dataset, texture_type, model, map_type, message) -> dict:
    return {
        "dataset":      dataset,
        "texture_type": texture_type or "",
        "model":        model,
        "map_type":     map_type,
        "status":       "error",
        "error_message": message,
        "mesh_path": "", "map_path": "",
        "front": "", "back": "", "left": "",
        "right": "", "top": "", "bottom": "",
        "montage": "",
    }


# ---------------------------------------------------------------------------
# I/O helpers for manifest and summary CSV
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
        "front", "back", "left", "right", "top", "bottom",
        "montage",
    ]
    with open(csv_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            clean = {k: row.get(k, "") for k in fieldnames}
            writer.writerow(clean)
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
        description="Render six-view jet heatmaps for SAL3D or MeshMamba."
    )
    ap.add_argument("--dataset", required=True, choices=VALID_DATASETS,
                    help="Dataset: sal3d or meshmamba")
    ap.add_argument("--texture-type", choices=VALID_TEXTURE, default=None,
                    help="MeshMamba texture type (required for meshmamba)")
    ap.add_argument("--metrics-root", type=Path, required=True,
                    help="Root of metric batch output directory")
    ap.add_argument("--dataset-root", type=Path, required=True,
                    help="Dataset root (OBJ files and, for MeshMamba, GT CSVs)")
    ap.add_argument("--fixed-gt-dir", type=Path, default=None,
                    help="SAL3D only: directory with <model>_faces.txt GT files")
    ap.add_argument("--output-root", type=Path, required=True,
                    help="Root directory for rendered output")
    ap.add_argument("--models", nargs="+", default=None,
                    help="Explicit model list (overrides auto-discovery)")
    ap.add_argument("--limit", type=int, default=None,
                    help="Limit number of models processed (for preview)")
    ap.add_argument("--map-types", nargs="+",
                    default=["screen_space", "cone", "gt"],
                    choices=VALID_MAP_TYPES,
                    help="Map types to render (default: screen_space cone gt)")
    ap.add_argument("--colormap", default="jet",
                    help="Matplotlib colormap (default: jet)")
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
        print("[ERROR] --texture-type is required for --dataset meshmamba",
              file=sys.stderr)
        sys.exit(1)

    if not args.metrics_root.is_dir():
        print(f"[ERROR] --metrics-root not found: {args.metrics_root}", file=sys.stderr)
        sys.exit(1)
    if not args.dataset_root.is_dir():
        print(f"[ERROR] --dataset-root not found: {args.dataset_root}", file=sys.stderr)
        sys.exit(1)
    if args.fixed_gt_dir is not None and not args.fixed_gt_dir.is_dir():
        print(f"[ERROR] --fixed-gt-dir not found: {args.fixed_gt_dir}", file=sys.stderr)
        sys.exit(1)

    # --- Model selection ---
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
    hostname = socket.gethostname()
    n_models = len(models)
    map_types = list(args.map_types)

    print(
        f"[INFO] dataset={args.dataset}  texture={args.texture_type or '-'}  "
        f"models={n_models}  map_types={map_types}  colormap={args.colormap}",
        flush=True,
    )
    print(f"[INFO] output_root: {args.output_root}", flush=True)

    all_rows: list[dict] = []
    manifest_entries: list[dict] = []

    for idx, model in enumerate(models, 1):
        print(f"[{idx}/{n_models}] {model} ...", flush=True)
        rows = process_model(
            model=model,
            dataset=args.dataset,
            texture_type=args.texture_type,
            metrics_root=args.metrics_root,
            dataset_root=args.dataset_root,
            fixed_gt_dir=args.fixed_gt_dir,
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
            all_rows.append(row)
            status = row.get("status", "?")
            msg = row.get("error_message", "")
            print(
                f"    {row['map_type']:14s}  {status}"
                + (f"  ({msg})" if msg else ""),
                flush=True,
            )

    manifest_path = write_manifest(manifest_entries, args.output_root)
    csv_path = write_summary_csv(all_rows, args.output_root)

    ok_count = sum(1 for r in all_rows if r.get("status") == "ok")
    skip_count = sum(1 for r in all_rows if r.get("status") == "skip")
    err_count = sum(1 for r in all_rows if r.get("status") == "error")

    print(
        f"\n[DONE] {ok_count} ok  {skip_count} skipped  {err_count} errors"
        f"  →  {manifest_path.name}  {csv_path.name}",
        flush=True,
    )


if __name__ == "__main__":
    main()
