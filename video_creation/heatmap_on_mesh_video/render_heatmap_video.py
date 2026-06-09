#!/usr/bin/env python3
"""
Render per-frame heatmap-on-mesh video using object-placement JSON pose.

Produces:
  {output-dir}/{dataset}/{track}/{model}/{map-type}/heatmap_video.mp4
  {output-dir}/{dataset}/{track}/{model}/{map-type}/manifest.json

Transform contract (blender_rig, canonical):
  recenter → scale → rotate_x(90°) → rotate_z(per-frame)

Timing contract:
  crop_start = 1.8 s, crop_end = 0.2 s (one full object revolution)

Usage:
  python render_heatmap_video.py \\
    --dataset MeshMamba --track non_texture --model Starfruit_L3 \\
    --map-type screen_space \\
    --map-file /path/to/Starfruit_L3_screen_space_faces.txt \\
    --mesh /path/to/Starfruit_L3.obj \\
    --placement-json jsons/object_placement/mamba_non_jsons/MeshMamba_non_texture_Starfruit_L3.json \\
    --output-dir /tmp/heatmap_videos \\
    --fps 30 --alpha 0.8 --colormap jet --max-frames 120
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

# Rendering deps — imported lazily so py_compile and pure-logic tests work without them.
_import_error: Exception | None = None
try:
    import pyvista as pv
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.cm import get_cmap
    from PIL import Image
except ImportError as _exc:
    _import_error = _exc

CROP_START_S = 1.8
CROP_END_S   = 0.2


# ── OBJ ──────────────────────────────────────────────────────────────────────

def parse_obj(path: Path) -> tuple[np.ndarray, np.ndarray]:
    vertices: list[list[float]] = []
    faces: list[list[int]] = []
    with open(path) as fh:
        for line in fh:
            if line.startswith("v "):
                p = line.split()
                vertices.append([float(p[1]), float(p[2]), float(p[3])])
            elif line.startswith("f "):
                p = line.split()
                faces.append([int(t.split("/")[0]) - 1 for t in p[1:4]])
    return np.array(vertices, dtype=np.float64), np.array(faces, dtype=np.int32)


# ── map loading ───────────────────────────────────────────────────────────────

def load_map(
    path: Path,
    n_vertices: int,
    n_faces: int,
    gt_column: int | None = None,
) -> tuple[np.ndarray, str]:
    """Load saliency map; auto-detect domain.

    Returns (values, domain) where domain is 'vertex' or 'face'.
    For multi-column files (e.g. SAL3D Gaze .txt) use gt_column (default 7).
    """
    raw = np.loadtxt(str(path), dtype=np.float64)
    if raw.ndim == 2:
        col = gt_column if gt_column is not None else 7
        raw = raw[:, col]
    n = len(raw)
    if n == n_faces:
        return raw, "face"
    if n == n_vertices:
        return raw, "vertex"
    raise ValueError(
        f"Map length {n} matches neither n_faces={n_faces} nor n_vertices={n_vertices}. "
        f"File: {path}"
    )


# ── transforms ────────────────────────────────────────────────────────────────

def _rotate_x(v: np.ndarray, deg: float) -> np.ndarray:
    rad = math.radians(deg)
    c, s = math.cos(rad), math.sin(rad)
    out = v.copy()
    out[:, 1] = c * v[:, 1] - s * v[:, 2]
    out[:, 2] = s * v[:, 1] + c * v[:, 2]
    return out


def _rotate_z(v: np.ndarray, rad: float) -> np.ndarray:
    c, s = math.cos(rad), math.sin(rad)
    out = v.copy()
    out[:, 0] = c * v[:, 0] - s * v[:, 1]
    out[:, 1] = s * v[:, 0] + c * v[:, 1]
    return out


def precompute_base_transform(
    vertices: np.ndarray,
    placement: dict,
    *,
    recenter: bool = True,
    extra_rotate_x_deg: float = 90.0,
) -> np.ndarray:
    """Apply static transforms (recenter, scale, X-rot). Returns base vertices
    ready for per-frame Z rotation via apply_frame_rotation()."""
    v = vertices.copy()
    if recenter:
        bbox_center = 0.5 * (v.min(axis=0) + v.max(axis=0))
        v -= bbox_center
    scale = np.asarray(placement["model_static"]["scale"], dtype=np.float64)
    v *= scale
    if abs(extra_rotate_x_deg) > 1e-9:
        v = _rotate_x(v, extra_rotate_x_deg)
    # model_static.location is [0,0,0] for all supported datasets
    v += np.asarray(placement["model_static"]["location"], dtype=np.float64)
    return v


def apply_frame_rotation(base_verts: np.ndarray, rotation_z_rad: float) -> np.ndarray:
    if abs(rotation_z_rad) <= 1e-12:
        return base_verts
    return _rotate_z(base_verts, rotation_z_rad)


# ── camera ────────────────────────────────────────────────────────────────────

def camera_from_placement(
    placement: dict,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """Return (position, focal_point, up, vert_fov_deg) from placement JSON.

    Decomposes view_matrix to recover exact Blender camera position and
    orientation. Converts horizontal FOV (60°) to vertical for PyVista.
    """
    cam = placement["camera_static"]
    V = np.array(cam["view_matrix"], dtype=np.float64).reshape(4, 4)
    R, t = V[:3, :3], V[:3, 3]

    position = (-R.T @ t)
    up = (R.T @ np.array([0.0, 1.0, 0.0]))

    # focal_point: model is centred at model_static.location ≈ [0,0,0]
    focal_point = np.asarray(placement["model_static"]["location"], dtype=np.float64)

    vi = placement["video_info"]
    aspect = vi["resolution_width"] / vi["resolution_height"]
    horiz_fov_rad = math.radians(cam["fov_degrees"])
    vert_fov_deg = math.degrees(
        2.0 * math.atan(math.tan(horiz_fov_rad / 2.0) / aspect)
    )
    return position, focal_point, up, vert_fov_deg


# ── colormap blending ──────────────────────────────────────────────────────────

def compute_rgb_colors(
    values: np.ndarray,
    domain: str,
    *,
    colormap: str = "jet",
    alpha: float = 1.0,
) -> tuple[np.ndarray, str]:
    """Map saliency values to blended RGB (uint8).

    alpha=1.0 → pure heatmap; alpha=0.0 → neutral gray.
    Returns (rgb (N,3) uint8, pv_domain) where pv_domain is 'cell' or 'point'.
    """
    cmap = get_cmap(colormap)
    vmin, vmax = float(values.min()), float(values.max())
    if vmax - vmin < 1e-12:
        normalized = np.zeros(len(values))
    else:
        normalized = (values - vmin) / (vmax - vmin)

    rgba = cmap(normalized)          # (N, 4) float [0,1]
    heatmap_rgb = rgba[:, :3]
    gray = np.full_like(heatmap_rgb, 0.5)
    blended = alpha * heatmap_rgb + (1.0 - alpha) * gray
    rgb_u8 = (np.clip(blended, 0.0, 1.0) * 255).astype(np.uint8)

    pv_domain = "cell" if domain == "face" else "point"
    return rgb_u8, pv_domain


# ── PyVista mesh ───────────────────────────────────────────────────────────────

def build_poly(vertices: np.ndarray, faces: np.ndarray) -> "pv.PolyData":
    pv_faces = np.hstack([
        np.full((len(faces), 1), 3, dtype=np.int32),
        faces.astype(np.int32),
    ])
    return pv.PolyData(vertices.astype(np.float32), pv_faces.ravel())


# ── frame rendering ───────────────────────────────────────────────────────────

def render_frames(
    base_verts: np.ndarray,
    faces: np.ndarray,
    frame_rotations: list[float],
    rgb_colors: np.ndarray,
    pv_domain: str,
    camera_params: tuple,
    frames_dir: Path,
    width: int,
    height: int,
) -> list[Path]:
    """Render frames off-screen. Reuses a single Plotter with in-place point updates."""
    os.environ.setdefault("DISPLAY", "")
    pv.OFF_SCREEN = True

    position, focal_point, up, vert_fov_deg = camera_params

    init_verts = apply_frame_rotation(base_verts, frame_rotations[0])
    mesh_poly = build_poly(init_verts, faces)
    if pv_domain == "cell":
        mesh_poly.cell_data["color"] = rgb_colors
    else:
        mesh_poly.point_data["color"] = rgb_colors

    pl = pv.Plotter(off_screen=True, window_size=(width, height))
    pl.set_background("black")
    pl.add_mesh(
        mesh_poly,
        scalars="color",
        rgb=True,
        show_scalar_bar=False,
        smooth_shading=False,
        preference=pv_domain,
    )
    pl.camera.position = position.tolist()
    pl.camera.focal_point = focal_point.tolist()
    pl.camera.up = up.tolist()
    pl.camera.view_angle = vert_fov_deg

    png_paths: list[Path] = []
    n = len(frame_rotations)
    for i, rot_rad in enumerate(frame_rotations):
        rotated = apply_frame_rotation(base_verts, rot_rad)
        mesh_poly.points = rotated.astype(np.float32)
        pl.render()
        img = pl.screenshot(return_img=True)
        p = frames_dir / f"frame_{i:05d}.png"
        Image.fromarray(img).save(str(p))
        png_paths.append(p)
        if (i + 1) % 50 == 0 or i == n - 1:
            print(f"  frame {i+1}/{n}", flush=True)

    pl.close()
    return png_paths


# ── video assembly ────────────────────────────────────────────────────────────

def frames_to_mp4(frames_dir: Path, output_mp4: Path, fps: int) -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found on PATH — cannot assemble video")
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", str(frames_dir / "frame_%05d.png"),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "medium",
        "-crf", "18",
        str(output_mp4),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{result.stderr[-2000:]}")


# ── manifest ──────────────────────────────────────────────────────────────────

def write_manifest(path: Path, data: dict) -> None:
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2)


# ── CLI ───────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Render per-frame heatmap-on-mesh video from placement JSON."
    )
    ap.add_argument("--dataset", required=True, help="Dataset name (MeshMamba, SAL3D)")
    ap.add_argument("--track", required=True, help="Track (non_texture, rgb_texture)")
    ap.add_argument("--model", required=True, help="Model name")
    ap.add_argument("--map-type", required=True,
                    choices=["screen_space", "cone", "gt"],
                    help="Heatmap source type")
    ap.add_argument("--map-file", type=Path, required=True,
                    help="Per-face or per-vertex saliency .txt file")
    ap.add_argument("--mesh", type=Path, required=True,
                    help="OBJ mesh file")
    ap.add_argument("--placement-json", type=Path, required=True,
                    help="Placement JSON for this model")
    ap.add_argument("--output-dir", type=Path, required=True,
                    help="Output root directory")
    ap.add_argument("--fps", type=int, default=None,
                    help="Output FPS (default: from placement JSON)")
    ap.add_argument("--alpha", type=float, default=1.0,
                    help="Heatmap opacity [0,1]; blends with neutral gray (default: 1.0)")
    ap.add_argument("--colormap", default="jet",
                    help="Matplotlib colormap (default: jet)")
    ap.add_argument("--max-frames", type=int, default=None,
                    help="Limit to first N frames of crop window (debug)")
    ap.add_argument("--width", type=int, default=960,
                    help="Output width px (default: 960)")
    ap.add_argument("--height", type=int, default=540,
                    help="Output height px (default: 540)")
    ap.add_argument("--gt-column", type=int, default=None,
                    help="Column index in multi-column GT file (SAL3D default: 7)")
    ap.add_argument("--keep-frames", action="store_true",
                    help="Keep individual PNG frames after video assembly")
    return ap


def main() -> None:
    if _import_error:
        print(f"[ERROR] Missing rendering dependency: {_import_error}", file=sys.stderr)
        sys.exit(1)

    args = build_parser().parse_args()

    for p, name in [
        (args.map_file, "--map-file"),
        (args.mesh, "--mesh"),
        (args.placement_json, "--placement-json"),
    ]:
        if not p.exists():
            print(f"[ERROR] {name} not found: {p}", file=sys.stderr)
            sys.exit(1)

    placement = json.loads(args.placement_json.read_text())
    vi = placement["video_info"]
    fps = args.fps or vi["fps"]
    total_frames = vi["total_frames"]
    frames_list = placement["frames"]

    start_idx = round(CROP_START_S * fps)
    end_idx = total_frames - round(CROP_END_S * fps)
    if args.max_frames is not None:
        end_idx = min(end_idx, start_idx + args.max_frames)
    n_frames = end_idx - start_idx
    if n_frames <= 0:
        print(f"[ERROR] empty crop window: start={start_idx} end={end_idx}", file=sys.stderr)
        sys.exit(1)
    print(f"[INFO] crop [{start_idx}, {end_idx}) = {n_frames} frames @ {fps} fps", flush=True)

    frame_rotations = [frames_list[i]["rotation_z_radians"] for i in range(start_idx, end_idx)]

    print(f"[INFO] loading mesh: {args.mesh}", flush=True)
    vertices, faces = parse_obj(args.mesh)
    n_vertices, n_faces = len(vertices), len(faces)
    print(f"[INFO] mesh: {n_vertices} vertices, {n_faces} faces", flush=True)

    print(f"[INFO] loading map: {args.map_file}", flush=True)
    values, map_domain = load_map(
        args.map_file, n_vertices, n_faces, gt_column=args.gt_column
    )
    print(f"[INFO] map: {len(values)} elements, domain={map_domain}", flush=True)

    base_verts = precompute_base_transform(vertices, placement)
    rgb_colors, pv_domain = compute_rgb_colors(
        values, map_domain, colormap=args.colormap, alpha=args.alpha
    )
    camera_params = camera_from_placement(placement)
    pos, fp, up, vfov = camera_params
    print(f"[INFO] camera: pos={pos.tolist()}, focal={fp.tolist()}, vfov={vfov:.2f}°", flush=True)

    out_subdir = args.output_dir / args.dataset / args.track / args.model / args.map_type
    out_subdir.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] rendering {n_frames} frames ({args.width}×{args.height}) ...", flush=True)
    with tempfile.TemporaryDirectory(prefix="heatmap_frames_") as tmpdir:
        tmp_path = Path(tmpdir)
        png_paths = render_frames(
            base_verts, faces, frame_rotations,
            rgb_colors, pv_domain, camera_params,
            tmp_path, args.width, args.height,
        )
        if args.keep_frames:
            frames_out = out_subdir / "frames"
            frames_out.mkdir(exist_ok=True)
            for p in png_paths:
                shutil.copy(p, frames_out / p.name)

        mp4_path = out_subdir / "heatmap_video.mp4"
        print(f"[INFO] assembling video: {mp4_path}", flush=True)
        frames_to_mp4(tmp_path, mp4_path, fps)

    manifest_path = out_subdir / "manifest.json"
    write_manifest(manifest_path, {
        "dataset":               args.dataset,
        "track":                 args.track,
        "model":                 args.model,
        "map_type":              args.map_type,
        "map_file":              str(args.map_file.resolve()),
        "mesh_file":             str(args.mesh.resolve()),
        "placement_json":        str(args.placement_json.resolve()),
        "placement_json_timing_used": True,
        "timing_contract": {
            "crop_start_s":  CROP_START_S,
            "crop_end_s":    CROP_END_S,
            "fps":           fps,
            "start_frame_idx": start_idx,
            "end_frame_idx":   end_idx,
        },
        "render": {
            "n_rendered_frames": len(png_paths),
            "fps":               fps,
            "width":             args.width,
            "height":            args.height,
            "alpha":             args.alpha,
            "colormap":          args.colormap,
            "map_domain":        map_domain,
            "n_map_elements":    len(values),
            "n_mesh_vertices":   n_vertices,
            "n_mesh_faces":      n_faces,
        },
        "output_files": {
            "video":    "heatmap_video.mp4",
            "manifest": "manifest.json",
        },
    })
    print(f"[INFO] manifest: {manifest_path}", flush=True)
    print(f"[DONE] {mp4_path}", flush=True)


if __name__ == "__main__":
    main()
