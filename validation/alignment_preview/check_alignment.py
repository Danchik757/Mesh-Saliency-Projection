#!/usr/bin/env python3
"""
Alignment validation preview: render mesh silhouette at canonical frames and
compare with the corresponding real video frame.

For each dataset / model / selected frame index k:
  - Applies the same transform pipeline used by the metric evaluators
    (recenter, scale, per-frame rotation-Z, extra-rotation-X for MeshMamba/SAL3D)
  - Projects all mesh vertices to screen via the placement-JSON camera matrices
  - Rasterises filled triangles → binary silhouette mask
  - Extracts video frame at original-video index (crop_start + k) via ffmpeg
  - Computes overlay (silhouette edge drawn on video frame)
  - Extracts video-based object mask via background subtraction (if video present)
  - Computes silhouette IoU
  - Writes per-frame PNGs, result.json, manifest.json, summary.csv

Timing contract (all 30 fps datasets):
  - crop_start  = round(1.8 * fps) = 54
  - crop_end    = round(0.2 * fps) = 6
  - gaze index k → placement / video frame index (crop_start + k)
  - 17s tracks: usable = 450 frames, k ∈ [0, 449]
  - 24s SAL3D:  usable = 660 frames, k ∈ [0, 659]

Usage — all datasets in one pass (recommended):

    python validation/alignment_preview/check_alignment.py \\
        --dataset 3dva --models bunny A380 \\
        --dataset-root  $VISUAL_ATTENTION_3D_SHAPES_ROOT \\
        --json-root     $THREE_DVA_JSON_ROOT \\
        --video-root    /path/to/videos \\
        --output-root   $OUTPUT_ROOT/alignment_preview_20260610

    python validation/alignment_preview/check_alignment.py \\
        --dataset meshmamba --texture-type non_texture \\
        --models Starfruit_L3 Pear_L3 \\
        --dataset-root $MESHMAMBA_NON_TEXTURE_ROOT \\
        --json-root    $MESHMAMBA_JSON_ROOT \\
        --video-root   /path/to/videos \\
        --output-root  $OUTPUT_ROOT/alignment_preview_20260610

    python validation/alignment_preview/check_alignment.py \\
        --dataset sal3d --models bunny MaxPlanck meca sofa \\
        --dataset-root $SAL3D_DATASET_ROOT \\
        --json-root    $SAL3D_JSON_ROOT \\
        --video-root   /path/to/videos \\
        --output-root  $OUTPUT_ROOT/alignment_preview_20260610

Run with low I/O and CPU priority:
    nice -n 18 ionice -c2 -n7  (set in your launch script, not here)
"""
from __future__ import annotations

import argparse
import csv
import datetime
import json
import math
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np

# --- Optional PIL import (guarded so py_compile and unit tests work without PIL) ---
_pil_error: Exception | None = None
try:
    from PIL import Image, ImageDraw
except ImportError as _e:
    _pil_error = _e
    Image = None   # type: ignore[assignment]
    ImageDraw = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Dataset static configuration
# ---------------------------------------------------------------------------

# Frame indices k for the preview sample (valid for all 17s datasets)
PREVIEW_K_17S = [0, 112, 225, 337, 449]
# Frame indices k for 24s SAL3D
PREVIEW_K_24S = [0, 165, 330, 495, 659]

FPS = 30
CROP_START = 54   # round(1.8 * 30)
CROP_END   =  6   # round(0.2 * 30)

IMG_W = 1920
IMG_H = 1080

# Per-dataset transform & path config
DATASET_CONFIGS: dict[str, dict[str, Any]] = {
    "3dva": {
        "json_prefix":      "3DVA_",
        "video_prefix":     "3DVA_",
        "obj_subdir":       "3DModels-Simplif-up",
        "transform_order":  "3dva",
        "recenter":         True,
        "base_rotate_z_deg":   0.0,
        "extra_rotate_x_deg":  0.0,
        "extra_rotate_y_deg":  0.0,
        "fov_mode":         "horizontal_to_vertical",
        "preview_k":        PREVIEW_K_17S,
    },
    "meshmamba": {
        # json_prefix / video_prefix include texture_type — formatted at runtime
        "json_prefix_template":   "MeshMamba_{texture_type}_",
        "video_prefix_template":  "MeshMamba_{texture_type}_",
        "obj_subdir_template":    "MeshFile/{texture_type}",
        "transform_order":  "blender_rig",
        "recenter":         True,
        "base_rotate_z_deg":   0.0,
        "extra_rotate_x_deg":  90.0,
        "extra_rotate_y_deg":  0.0,
        "fov_mode":         "horizontal_to_vertical",
        "preview_k":        PREVIEW_K_17S,
    },
    "sal3d": {
        "json_prefix":      "Sal3D_",
        "video_prefix":     "Sal3D_",
        "obj_subdir":       "Meshes",
        "transform_order":  "blender_rig",
        "recenter":         True,
        "base_rotate_z_deg":   0.0,
        "extra_rotate_x_deg":  90.0,
        "extra_rotate_y_deg":  0.0,
        "fov_mode":         "horizontal_to_vertical",
        "preview_k":        PREVIEW_K_24S,
    },
}


# ---------------------------------------------------------------------------
# OBJ parsing
# ---------------------------------------------------------------------------

def parse_obj(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Return (vertices [N,3] float64, faces [M,3] int32) from a triangulated OBJ."""
    vertices: list[list[float]] = []
    faces: list[list[int]] = []
    with open(path) as fh:
        for line in fh:
            if line.startswith("v "):
                p = line.split()
                vertices.append([float(p[1]), float(p[2]), float(p[3])])
            elif line.startswith("f "):
                p = line.split()
                tri = [int(t.split("/")[0]) - 1 for t in p[1:4]]
                if len(tri) == 3:
                    faces.append(tri)
    return np.array(vertices, dtype=np.float64), np.array(faces, dtype=np.int32)


# ---------------------------------------------------------------------------
# Camera / projection
# ---------------------------------------------------------------------------

def build_projection_matrix_from_fov(
    fov_deg: float, aspect: float, clip_start: float, clip_end: float
) -> np.ndarray:
    f = 1.0 / math.tan(math.radians(fov_deg) * 0.5)
    near, far = float(clip_start), float(clip_end)
    return np.array(
        [
            [f / aspect, 0, 0, 0],
            [0, f, 0, 0],
            [0, 0, -(far + near) / (far - near), -(2 * far * near) / (far - near)],
            [0, 0, -1, 0],
        ],
        dtype=np.float64,
    )


def horizontal_to_vertical_fov_deg(h_fov_deg: float, aspect: float) -> float:
    return math.degrees(
        2.0 * math.atan(math.tan(math.radians(h_fov_deg) * 0.5) / float(aspect))
    )


def resolve_projection_matrix(camera_data: dict, fov_mode: str) -> tuple[np.ndarray, dict]:
    """Resolve projection matrix from placement JSON.

    fov_mode: "horizontal_to_vertical" (used by all current batch runners) or "json".
    Returns (proj_matrix [4,4], info_dict).
    """
    cam = camera_data["camera_static"]
    vi  = camera_data["video_info"]
    aspect = float(vi["aspect_ratio"])

    if fov_mode == "json":
        proj = np.asarray(cam["projection_matrix"], dtype=np.float64).reshape(4, 4)
        return proj, {"fov_mode": "json", "fov_source": "json_projection_matrix",
                      "input_fov_deg": None, "effective_vfov_deg": None}

    if fov_mode == "horizontal_to_vertical":
        if "fov_degrees" in cam:
            h_fov = float(cam["fov_degrees"])
            src = "json_camera_static.fov_degrees"
        else:
            h_fov = math.degrees(float(cam["fov_radians"]))
            src = "json_camera_static.fov_radians"
        v_fov = horizontal_to_vertical_fov_deg(h_fov, aspect)
        proj = build_projection_matrix_from_fov(
            v_fov, aspect, float(cam["clip_start"]), float(cam["clip_end"])
        )
        return proj, {"fov_mode": "horizontal_to_vertical", "fov_source": src,
                      "input_fov_deg": h_fov, "effective_vfov_deg": v_fov}

    raise ValueError(f"Unknown fov_mode: {fov_mode!r}")


def world_to_screen(
    points_w: np.ndarray,
    view_matrix: np.ndarray,
    proj_matrix: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Project world-space points to fractional screen [0,1]×[0,1].

    Returns (screen_xy [N,2], w_clip [N]).  w_clip ≤ 0 → behind camera.
    """
    ones  = np.ones((len(points_w), 1), dtype=np.float64)
    pts_h = np.hstack([points_w, ones])
    cam   = (view_matrix @ pts_h.T).T
    clip  = (proj_matrix @ cam.T).T
    w     = clip[:, 3]
    safe_w = np.where(np.abs(w) > 1e-12, w, 1e-12)
    screen_x = (clip[:, 0] / safe_w + 1.0) * 0.5
    screen_y = (1.0 - clip[:, 1] / safe_w) * 0.5  # Y flipped
    return np.stack([screen_x, screen_y], axis=1), w


# ---------------------------------------------------------------------------
# Mesh transform
# ---------------------------------------------------------------------------

def _rotate_z(pts: np.ndarray, angle_rad: float) -> np.ndarray:
    if abs(angle_rad) <= 1e-12:
        return pts
    out = pts.copy()
    cz, sz = math.cos(angle_rad), math.sin(angle_rad)
    out[:, 0] = cz * pts[:, 0] - sz * pts[:, 1]
    out[:, 1] = sz * pts[:, 0] + cz * pts[:, 1]
    return out


def _rotate_x(pts: np.ndarray, angle_deg: float) -> np.ndarray:
    angle_rad = math.radians(angle_deg)
    if abs(angle_rad) <= 1e-12:
        return pts
    out = pts.copy()
    crx, srx = math.cos(angle_rad), math.sin(angle_rad)
    out[:, 1] = crx * pts[:, 1] - srx * pts[:, 2]
    out[:, 2] = srx * pts[:, 1] + crx * pts[:, 2]
    return out


def _rotate_y(pts: np.ndarray, angle_deg: float) -> np.ndarray:
    angle_rad = math.radians(angle_deg)
    if abs(angle_rad) <= 1e-12:
        return pts
    out = pts.copy()
    cry, sry = math.cos(angle_rad), math.sin(angle_rad)
    out[:, 0] = cry * pts[:, 0] + sry * pts[:, 2]
    out[:, 2] = -sry * pts[:, 0] + cry * pts[:, 2]
    return out


def precompute_base_verts(
    vertices: np.ndarray,
    recenter: bool,
    base_rotate_z_deg: float,
    transform_order: str,
) -> tuple[np.ndarray, np.ndarray]:
    """One-time pre-frame-loop setup; returns (base_verts, original_bbox_center).

    3dva order:  apply base_rz to raw verts → recenter using ORIGINAL bbox center
    blender_rig: just recenter (base_rz goes inside the per-frame step)

    In practice all current benchmark runs use base_rotate_z_deg=0.0 for all
    datasets, so the two orders are equivalent; the explicit split ensures the
    tool matches evaluator behaviour if a non-zero value is ever introduced.
    """
    v = np.asarray(vertices, dtype=np.float64).copy()
    bbox_center = 0.5 * (v.min(axis=0) + v.max(axis=0))

    if transform_order == "3dva":
        rz0 = math.radians(base_rotate_z_deg)
        v = _rotate_z(v, rz0)
        if recenter:
            v -= bbox_center  # uses ORIGINAL bbox center (before base_rz)
    elif transform_order == "blender_rig":
        if recenter:
            v -= bbox_center
    else:
        raise ValueError(f"Unknown transform_order: {transform_order!r}")

    return v, bbox_center


def apply_frame_transform(
    base_verts: np.ndarray,
    camera_data: dict,
    rotation_z_rad: float,
    base_rotate_z_deg: float,
    extra_rotate_x_deg: float,
    extra_rotate_y_deg: float,
    transform_order: str,
) -> np.ndarray:
    """Apply per-frame transform to pre-computed base_verts.

    Matches the evaluator per-frame ops precisely:
      3dva:        scale → frame_rz → extra_rx → extra_ry → translate
      blender_rig: scale → extra_rx → extra_ry → base_rz → frame_rz → translate

    Note: base_verts already have base_rz and recenter baked in for both orders.
    """
    v = base_verts.copy()
    scale    = np.asarray(camera_data["model_static"]["scale"], dtype=np.float64)
    location = np.asarray(camera_data["model_static"]["location"], dtype=np.float64)
    base_rz  = math.radians(base_rotate_z_deg)

    if transform_order == "3dva":
        v *= scale
        v  = _rotate_z(v, rotation_z_rad)
        v  = _rotate_x(v, extra_rotate_x_deg)
        v  = _rotate_y(v, extra_rotate_y_deg)

    elif transform_order == "blender_rig":
        v *= scale
        v  = _rotate_x(v, extra_rotate_x_deg)
        v  = _rotate_y(v, extra_rotate_y_deg)
        v  = _rotate_z(v, base_rz)
        v  = _rotate_z(v, rotation_z_rad)

    else:
        raise ValueError(f"Unknown transform_order: {transform_order!r}")

    v += location
    return v


# ---------------------------------------------------------------------------
# Silhouette rendering (CPU rasterisation via PIL)
# ---------------------------------------------------------------------------

def rasterize_silhouette(
    world_verts: np.ndarray,
    faces: np.ndarray,
    view_matrix: np.ndarray,
    proj_matrix: np.ndarray,
    img_w: int = IMG_W,
    img_h: int = IMG_H,
) -> np.ndarray:
    """Rasterise projected mesh triangles as a filled binary mask (H×W bool).

    Includes all faces whose three vertices are in front of the camera
    (w_clip > 0), regardless of winding order.  This gives the correct
    projected silhouette for alignment validation.
    """
    if Image is None or ImageDraw is None:
        raise ImportError(f"Pillow is required for silhouette rendering: {_pil_error}")

    screen_xy, w_clip = world_to_screen(world_verts, view_matrix, proj_matrix)

    px = screen_xy[:, 0] * img_w
    py = screen_xy[:, 1] * img_h

    mask_img = Image.new("L", (img_w, img_h), 0)
    draw = ImageDraw.Draw(mask_img)

    for i0, i1, i2 in faces:
        if w_clip[i0] <= 0 or w_clip[i1] <= 0 or w_clip[i2] <= 0:
            continue
        pts = [
            (float(px[i0]), float(py[i0])),
            (float(px[i1]), float(py[i1])),
            (float(px[i2]), float(py[i2])),
        ]
        draw.polygon(pts, fill=255)

    return np.asarray(mask_img, dtype=bool)


def extract_edge_mask(silhouette: np.ndarray) -> np.ndarray:
    """4-connected boundary pixels of a binary silhouette mask."""
    pad = np.pad(silhouette.astype(bool), 1, mode="constant", constant_values=False)
    center   = pad[1:-1, 1:-1]
    interior = (center
                & pad[:-2, 1:-1]   # up
                & pad[2:,  1:-1]   # down
                & pad[1:-1, :-2]   # left
                & pad[1:-1, 2:])   # right
    return center & ~interior


def overlay_edge_on_frame(
    frame_rgb: np.ndarray,
    edge_mask: np.ndarray,
    color: tuple[int, int, int] = (0, 255, 0),
) -> np.ndarray:
    """Draw silhouette edge over an RGB video frame."""
    overlay = frame_rgb.copy()
    overlay[edge_mask] = color
    return overlay


# ---------------------------------------------------------------------------
# Video mask via background subtraction
# ---------------------------------------------------------------------------

def estimate_background_rgb(image_rgb: np.ndarray) -> np.ndarray:
    """Median colour of the four corner patches (same as debug_single_gaze_projection.py)."""
    h, w = image_rgb.shape[:2]
    patch = max(1, min(24, h // 4, w // 4))
    corners = np.concatenate(
        [
            image_rgb[:patch, :patch].reshape(-1, 3),
            image_rgb[:patch, w - patch:].reshape(-1, 3),
            image_rgb[h - patch:, :patch].reshape(-1, 3),
            image_rgb[h - patch:, w - patch:].reshape(-1, 3),
        ],
        axis=0,
    )
    return np.median(corners, axis=0)


def extract_video_mask(image_rgb: np.ndarray, threshold: float = 25.0) -> np.ndarray:
    """Return foreground mask via L2 colour distance from corner-estimated background."""
    bg = estimate_background_rgb(image_rgb)
    dist = np.linalg.norm(image_rgb.astype(np.float32) - bg.reshape(1, 1, 3), axis=2)
    return dist > threshold


# ---------------------------------------------------------------------------
# IoU
# ---------------------------------------------------------------------------

def compute_iou(mask_a: np.ndarray, mask_b: np.ndarray) -> float:
    """Binary mask IoU.  Returns 0.0 when union is empty."""
    inter = float(np.logical_and(mask_a, mask_b).sum())
    union = float(np.logical_or(mask_a, mask_b).sum())
    return inter / union if union > 0.0 else 0.0


# ---------------------------------------------------------------------------
# Video frame extraction
# ---------------------------------------------------------------------------

def extract_video_frame(
    video_path: Path, frame_idx: int, output_png: Path, fps: float = FPS
) -> bool:
    """Extract video frame at frame_idx using ffmpeg.  Returns True on success."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return False
    output_png.parent.mkdir(parents=True, exist_ok=True)
    timestamp = frame_idx / fps
    cmd = [
        ffmpeg, "-y", "-loglevel", "error",
        "-ss", f"{timestamp:.6f}", "-i", str(video_path),
        "-frames:v", "1", str(output_png),
    ]
    result = subprocess.run(cmd, capture_output=True)
    return result.returncode == 0 and output_png.exists()


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _find_file_casefold(directory: Path, stem: str, suffix: str) -> Path | None:
    if not directory.is_dir():
        return None
    target = (stem + suffix).lower()
    for p in directory.iterdir():
        if p.name.lower() == target:
            return p
    return None


def _find_video(video_root: Path, prefix: str, model: str) -> Path | None:
    """Case-insensitive search for {prefix}{model}.mp4 in video_root."""
    if video_root is None or not video_root.is_dir():
        return None
    stem = f"{prefix}{model}"
    return _find_file_casefold(video_root, stem, ".mp4")


def _find_obj(obj_dir: Path, model: str) -> Path | None:
    """Case-insensitive OBJ lookup (exact name or stem match)."""
    exact = obj_dir / f"{model}.obj"
    if exact.exists():
        return exact
    return _find_file_casefold(obj_dir, model, ".obj")


def _find_json(json_root: Path, prefix: str, model: str) -> Path | None:
    """Case-insensitive JSON lookup for {prefix}{model}.json."""
    stem = f"{prefix}{model}"
    return _find_file_casefold(json_root, stem, ".json")


def resolve_dataset_paths(
    dataset: str,
    texture_type: str | None,
    dataset_root: Path,
    json_root: Path,
    video_root: Path | None,
    model: str,
) -> dict[str, Path | None]:
    """Return {obj, json, video} paths for a model (all may be None on miss)."""
    cfg = DATASET_CONFIGS[dataset]

    # JSON prefix
    if "json_prefix_template" in cfg:
        assert texture_type, f"--texture-type required for {dataset}"
        json_prefix = cfg["json_prefix_template"].format(texture_type=texture_type)
        video_prefix = cfg["video_prefix_template"].format(texture_type=texture_type)
        obj_subdir   = Path(cfg["obj_subdir_template"].format(texture_type=texture_type))
    else:
        json_prefix  = cfg["json_prefix"]
        video_prefix = cfg["video_prefix"]
        obj_subdir   = Path(cfg["obj_subdir"])

    obj_dir = dataset_root / obj_subdir
    return {
        "obj":   _find_obj(obj_dir, model),
        "json":  _find_json(json_root, json_prefix, model),
        "video": _find_video(video_root, video_prefix, model) if video_root else None,
    }


# ---------------------------------------------------------------------------
# Per-frame processing
# ---------------------------------------------------------------------------

def process_frame(
    gaze_k: int,
    vertices: np.ndarray,
    base_verts: np.ndarray,
    faces: np.ndarray,
    camera_data: dict,
    proj_matrix: np.ndarray,
    base_rotate_z_deg: float,
    extra_rotate_x_deg: float,
    extra_rotate_y_deg: float,
    transform_order: str,
    video_path: Path | None,
    frame_out_dir: Path,
) -> dict:
    """Render silhouette, extract video frame, compute overlay and IoU for one k."""
    placement_idx = CROP_START + gaze_k
    result: dict[str, Any] = {
        "gaze_k":        gaze_k,
        "placement_idx": placement_idx,
        "video_frame_idx": placement_idx,
    }

    # --- Get rotation from placement JSON ---
    frames_list = camera_data["frames"]
    if placement_idx >= len(frames_list):
        result["status"] = "error"
        result["error"]  = f"placement_idx {placement_idx} >= len(frames) {len(frames_list)}"
        return result

    rotation_z_rad = float(frames_list[placement_idx]["rotation_z_radians"])
    result["rotation_z_radians"] = rotation_z_rad

    # --- Apply transform ---
    world_verts = apply_frame_transform(
        base_verts, camera_data, rotation_z_rad,
        base_rotate_z_deg, extra_rotate_x_deg, extra_rotate_y_deg,
        transform_order,
    )

    # --- Render silhouette ---
    view_matrix = np.asarray(
        camera_data["camera_static"]["view_matrix"], dtype=np.float64
    ).reshape(4, 4)

    silhouette = rasterize_silhouette(world_verts, faces, view_matrix, proj_matrix)
    edge_mask  = extract_edge_mask(silhouette)
    result["rendered_pixels"] = int(silhouette.sum())

    # Save silhouette mask
    frame_out_dir.mkdir(parents=True, exist_ok=True)
    sil_path = frame_out_dir / "silhouette_mask.png"
    _save_bool_mask_png(silhouette, sil_path)
    result["silhouette_mask_png"] = str(sil_path.name)

    # --- Video frame extraction ---
    iou          = None
    iou_reliable = False
    iou_note     = "no_video"

    raw_frame_png  = frame_out_dir / "raw_video_frame.png"
    overlay_png    = frame_out_dir / "overlay_edge.png"
    video_mask_png = frame_out_dir / "video_mask.png"

    if video_path is not None and video_path.exists():
        ok = extract_video_frame(video_path, placement_idx, raw_frame_png)
        if ok:
            try:
                frame_img = Image.open(str(raw_frame_png)).convert("RGB")
                frame_rgb = np.asarray(frame_img, dtype=np.uint8)

                # Resize if needed (video may differ from IMG_W × IMG_H)
                if frame_rgb.shape[1] != silhouette.shape[1] or \
                   frame_rgb.shape[0] != silhouette.shape[0]:
                    frame_img = frame_img.resize(
                        (silhouette.shape[1], silhouette.shape[0]), Image.LANCZOS
                    )
                    frame_rgb = np.asarray(frame_img, dtype=np.uint8)

                overlay_rgb = overlay_edge_on_frame(frame_rgb, edge_mask)
                _save_rgb_png(overlay_rgb, overlay_png)
                result["overlay_edge_png"] = str(overlay_png.name)

                try:
                    video_mask = extract_video_mask(frame_rgb)
                    _save_bool_mask_png(video_mask, video_mask_png)
                    result["video_mask_png"] = str(video_mask_png.name)
                    iou = compute_iou(silhouette, video_mask)
                    iou_reliable = True
                    iou_note = "bg_subtraction"
                except Exception as exc:
                    iou_note = f"video_mask_failed: {exc}"

            except Exception as exc:
                iou_note = f"frame_decode_failed: {exc}"
        else:
            iou_note = "ffmpeg_extraction_failed"
    elif video_path is not None and not video_path.exists():
        iou_note = f"video_not_found: {video_path.name}"

    result["iou"]          = iou
    result["iou_reliable"] = iou_reliable
    result["iou_note"]     = iou_note
    result["status"]       = "ok"
    return result


# ---------------------------------------------------------------------------
# Image save helpers
# ---------------------------------------------------------------------------

def _save_bool_mask_png(mask: np.ndarray, path: Path) -> None:
    if Image is None:
        raise ImportError(f"Pillow required: {_pil_error}")
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(mask.astype(np.uint8) * 255, mode="L").save(str(path))


def _save_rgb_png(rgb: np.ndarray, path: Path) -> None:
    if Image is None:
        raise ImportError(f"Pillow required: {_pil_error}")
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb, mode="RGB").save(str(path))


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _model_output_dir(output_root: Path, dataset: str, texture_type: str | None,
                       model: str) -> Path:
    label = f"{dataset.upper()}_{texture_type}" if texture_type else dataset.upper()
    return output_root / label / model


def _git_commit_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def write_manifest(entries: list[dict], output_root: Path) -> Path:
    p = output_root / "manifest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as fh:
        json.dump(entries, fh, indent=2)
    return p


def write_summary_csv(rows: list[dict], output_root: Path) -> Path:
    p = output_root / "summary.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "dataset", "texture_type", "model",
        "gaze_k", "placement_idx",
        "status", "error_message",
        "rendered_pixels",
        "iou", "iou_reliable", "iou_note",
        "rotation_z_deg",
        "obj_path", "json_path", "video_path",
        "silhouette_mask_png", "overlay_edge_png",
    ]
    with open(p, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})
    return p


# ---------------------------------------------------------------------------
# Per-model processing
# ---------------------------------------------------------------------------

def process_model(
    dataset: str,
    texture_type: str | None,
    model: str,
    dataset_root: Path,
    json_root: Path,
    video_root: Path | None,
    output_root: Path,
    commit_hash: str,
    hostname: str,
) -> list[dict]:
    """Process all preview frames for one model. Returns list of summary rows."""
    cfg = DATASET_CONFIGS[dataset]
    created_at = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"

    paths = resolve_dataset_paths(
        dataset, texture_type, dataset_root, json_root, video_root, model
    )
    obj_path   = paths["obj"]
    json_path  = paths["json"]
    video_path = paths["video"]

    rows: list[dict] = []
    base_row = {
        "dataset":      dataset,
        "texture_type": texture_type or "",
        "model":        model,
        "obj_path":     str(obj_path) if obj_path else "",
        "json_path":    str(json_path) if json_path else "",
        "video_path":   str(video_path) if video_path else "",
    }

    if obj_path is None or not obj_path.exists():
        rows.append({**base_row, "status": "error",
                     "error_message": f"OBJ not found for '{model}'"})
        return rows
    if json_path is None or not json_path.exists():
        rows.append({**base_row, "status": "error",
                     "error_message": f"Placement JSON not found for '{model}'"})
        return rows

    # Load mesh
    try:
        vertices, faces = parse_obj(obj_path)
    except Exception as exc:
        rows.append({**base_row, "status": "error",
                     "error_message": f"OBJ parse error: {exc}"})
        return rows

    # Load placement JSON
    with open(json_path) as fh:
        camera_data = json.load(fh)

    # Build projection matrix
    proj_matrix, proj_info = resolve_projection_matrix(camera_data, cfg["fov_mode"])

    # Precompute base vertices (one-time)
    base_verts, bbox_center = precompute_base_verts(
        vertices,
        recenter=bool(cfg["recenter"]),
        base_rotate_z_deg=float(cfg["base_rotate_z_deg"]),
        transform_order=str(cfg["transform_order"]),
    )

    # Manifest entry common fields
    manifest_common = {
        "dataset":              dataset,
        "texture_type":         texture_type,
        "model":                model,
        "n_verts":              len(vertices),
        "n_faces":              len(faces),
        "obj_path":             str(obj_path),
        "json_path":            str(json_path),
        "video_path":           str(video_path) if video_path else None,
        "transform_order":      cfg["transform_order"],
        "recenter":             cfg["recenter"],
        "base_rotate_z_deg":    cfg["base_rotate_z_deg"],
        "extra_rotate_x_deg":   cfg["extra_rotate_x_deg"],
        "extra_rotate_y_deg":   cfg["extra_rotate_y_deg"],
        "fov_mode":             cfg["fov_mode"],
        "fov_info":             proj_info,
        "timing_crop_start":    CROP_START,
        "timing_fps":           FPS,
        "commit_hash":          commit_hash,
        "server_hostname":      hostname,
        "created_at":           created_at,
    }

    model_out_dir = _model_output_dir(output_root, dataset, texture_type, model)

    for gaze_k in list(cfg["preview_k"]):
        placement_idx = CROP_START + gaze_k
        frame_dir = model_out_dir / f"frame_{gaze_k:04d}_p{placement_idx:04d}"

        try:
            frame_result = process_frame(
                gaze_k=gaze_k,
                vertices=vertices,
                base_verts=base_verts,
                faces=faces,
                camera_data=camera_data,
                proj_matrix=proj_matrix,
                base_rotate_z_deg=float(cfg["base_rotate_z_deg"]),
                extra_rotate_x_deg=float(cfg["extra_rotate_x_deg"]),
                extra_rotate_y_deg=float(cfg["extra_rotate_y_deg"]),
                transform_order=str(cfg["transform_order"]),
                video_path=video_path,
                frame_out_dir=frame_dir,
            )
        except Exception as exc:
            frame_result = {
                "gaze_k":        gaze_k,
                "placement_idx": placement_idx,
                "status":        "error",
                "error":         str(exc),
            }

        # Write per-frame result.json
        result_json_path = frame_dir / "result.json"
        try:
            result_json_path.parent.mkdir(parents=True, exist_ok=True)
            with open(result_json_path, "w") as fh:
                json.dump({**manifest_common, **frame_result}, fh, indent=2)
        except Exception:
            pass

        rot_deg = (math.degrees(frame_result.get("rotation_z_radians", 0))
                   if "rotation_z_radians" in frame_result else None)

        row = {
            **base_row,
            "gaze_k":            gaze_k,
            "placement_idx":     placement_idx,
            "status":            frame_result.get("status", "error"),
            "error_message":     frame_result.get("error", ""),
            "rendered_pixels":   frame_result.get("rendered_pixels", ""),
            "iou":               frame_result.get("iou", ""),
            "iou_reliable":      frame_result.get("iou_reliable", False),
            "iou_note":          frame_result.get("iou_note", ""),
            "rotation_z_deg":    f"{rot_deg:.3f}" if rot_deg is not None else "",
            "silhouette_mask_png": frame_result.get("silhouette_mask_png", ""),
            "overlay_edge_png":    frame_result.get("overlay_edge_png", ""),
        }
        rows.append(row)

    return rows


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description=(
            "Alignment validation preview: render mesh silhouette at canonical "
            "frames and compare with real video frames."
        )
    )
    ap.add_argument("--dataset", required=True,
                    choices=list(DATASET_CONFIGS.keys()),
                    help="Dataset identifier: 3dva | meshmamba | sal3d")
    ap.add_argument("--texture-type", default=None,
                    choices=["non_texture", "rgb_texture"],
                    help="MeshMamba texture type (required for --dataset meshmamba)")
    ap.add_argument("--models", nargs="+", required=True,
                    help="Model names to validate")
    ap.add_argument("--dataset-root", type=Path, required=True,
                    help="Dataset root (contains OBJ meshes)")
    ap.add_argument("--json-root", type=Path, required=True,
                    help="Placement JSON root directory")
    ap.add_argument("--video-root", type=Path, default=None,
                    help="Directory with .mp4 stimulus videos (optional; "
                         "IoU reported as null when absent)")
    ap.add_argument("--output-root", type=Path, required=True,
                    help="Root for rendered output, CSVs, and manifests")
    return ap.parse_args(argv)


def main(argv=None):
    if _pil_error is not None:
        print(f"[ERROR] Pillow is required: {_pil_error}", file=sys.stderr)
        sys.exit(1)

    args = parse_args(argv)

    if args.dataset == "meshmamba" and args.texture_type is None:
        print("[ERROR] --texture-type is required for --dataset meshmamba",
              file=sys.stderr)
        sys.exit(1)
    if not args.dataset_root.is_dir():
        print(f"[ERROR] --dataset-root not found: {args.dataset_root}", file=sys.stderr)
        sys.exit(1)
    if not args.json_root.is_dir():
        print(f"[ERROR] --json-root not found: {args.json_root}", file=sys.stderr)
        sys.exit(1)
    if args.video_root is not None and not args.video_root.is_dir():
        print(f"[WARN] --video-root not found: {args.video_root} — IoU will be null",
              file=sys.stderr)
        args.video_root = None

    commit_hash = _git_commit_hash()
    hostname    = socket.gethostname()

    print(
        f"[INFO] dataset={args.dataset}  texture={args.texture_type or '-'}  "
        f"models={args.models}  output={args.output_root}",
        flush=True,
    )

    all_rows: list[dict] = []

    for idx, model in enumerate(args.models, 1):
        print(f"[{idx}/{len(args.models)}] {model}", flush=True)
        rows = process_model(
            dataset=args.dataset,
            texture_type=args.texture_type,
            model=model,
            dataset_root=args.dataset_root,
            json_root=args.json_root,
            video_root=args.video_root,
            output_root=args.output_root,
            commit_hash=commit_hash,
            hostname=hostname,
        )
        for row in rows:
            k    = row.get("gaze_k", "?")
            st   = row.get("status", "?")
            iou  = row.get("iou")
            note = row.get("iou_note", "")
            iou_str = f"  iou={iou:.3f}" if isinstance(iou, float) else ""
            print(f"    k={k:>4s}  {st}{iou_str}  {note}", flush=True)
        all_rows.extend(rows)

    manifest_path = write_manifest(
        [
            {k: v for k, v in row.items() if v != ""}
            for row in all_rows
        ],
        args.output_root,
    )
    csv_path = write_summary_csv(all_rows, args.output_root)

    ok_count  = sum(1 for r in all_rows if r.get("status") == "ok")
    err_count = sum(1 for r in all_rows if r.get("status") == "error")
    iou_rows  = [r["iou"] for r in all_rows if isinstance(r.get("iou"), float)]
    mean_iou  = float(np.mean(iou_rows)) if iou_rows else None

    print(
        f"\n[DONE] {ok_count} ok  {err_count} errors"
        + (f"  mean_iou={mean_iou:.3f} (n={len(iou_rows)})" if mean_iou is not None else "  iou=n/a (no video)")
        + f"\n  manifest: {manifest_path}\n  summary:  {csv_path}",
        flush=True,
    )


if __name__ == "__main__":
    main()
