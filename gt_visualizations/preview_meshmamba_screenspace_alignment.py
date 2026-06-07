#!/usr/bin/env python3
"""
Visual sanity check for the screen_space_gaussian projection method.

Produces PNG images to verify that:
  1. The 2D gaze density and face-centroid projections are spatially aligned
     (no Y-flip or coordinate-system bug).
  2. High-gaze areas map to the correct mesh faces.
  3. The accumulated predicted saliency map looks plausible relative to GT.

=== Three panels per frame ===

  LEFT   — Gaze density  (INPUT to the method)
           2D histogram of raw eye-tracker fixations for that frame,
           blurred with the same Gaussian used by screen_space_gaussian.
           Cyan dots = individual raw gaze points.

  MIDDLE — Predicted saliency  (OUR RESULT)
           Each dot = one face centroid projected to screen.
           Colour = per-face saliency value assigned by the method.
           Hot (yellow/orange) = high predicted attention.

  RIGHT  — GT saliency  (REFERENCE / GROUND TRUTH)
           Same face-centroid projection but coloured by the GT per-face
           CSV value from the dataset (what we compare against via CC/SIM/KLD).

=== Summary image ===

  Two panels: accumulated predicted (all frames) vs GT at mid-rotation view.

=== What to look for ===

  Good alignment:  hot spots in MIDDLE roughly match hot spots in RIGHT.
  Coordinate bug:  hot spots are mirror-flipped between MIDDLE and RIGHT.

=== Usage ===

  # On vg-intellect:
  source configs/server_vg_intellect.env
  $REPROJECT_PYTHON gt_visualizations/preview_meshmamba_screenspace_alignment.py \\
      --model Rubber_Duck_v1_L3 --texture-type non_texture \\
      --output-dir /tmp/preview_v2

  # Specific frames (default: 25%%, 50%%, 75%% of video):
  $REPROJECT_PYTHON gt_visualizations/preview_meshmamba_screenspace_alignment.py \\
      --model Rubber_Duck_v1_L3 --preview-frames 100 255 400

=== Outputs ===

  <output-dir>/<model>__<method>__frame<NNNN>.png   — 3-panel image per frame
  <output-dir>/<model>__<method>__summary.png       — accumulated pred vs GT

=== Dependencies ===

  numpy, scipy, trimesh, Pillow — no display server needed.
  Imports from: reprojection_methods/screen_space_gaussian/eval_meshmamba_screen_space_v2.py
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import gaussian_filter

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from reprojection_methods.screen_space_gaussian.eval_meshmamba_screen_space_v2 import (
    _IMG_W, _IMG_H,
    _deposit_bilinear_batch,
    _apply_transform_no_recenter,
    _apply_normal_transform,
    world_to_screen,
    resolve_projection_matrix,
    load_gaze_batches,
    find_obj_file, find_csv_file, find_json_file, find_gt_file,
)


def _env_path(primary: str, secondary: str, fallback: str = "") -> Path:
    return Path(os.environ.get(primary) or os.environ.get(secondary) or fallback)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="Rubber_Duck_v1_L3")
    p.add_argument("--texture-type", default="non_texture")
    p.add_argument("--sigma-px", type=float, default=26.3)
    p.add_argument(
        "--preview-frames", nargs="+", type=int, default=None,
        help="Frame indices to preview. Default: 3 evenly spaced."
    )
    p.add_argument("--output-dir", type=Path,
                   default=Path("/tmp/preview_v2"))
    # dataset paths — filled from env vars if not given
    p.add_argument("--dataset-root", type=Path,
                   default=None)
    p.add_argument("--csv-root", type=Path,
                   default=None)
    p.add_argument("--json-root", type=Path,
                   default=None)
    args = p.parse_args()

    if args.dataset_root is None:
        args.dataset_root = _env_path(
            "MESHMAMBA_NON_TEXTURE_ROOT",
            "REPROJECT_DATASET_MESHMAMBA_ROOT",
        )

    csv_secondary = (
        "REPROJECT_GAZE_CSV_MESHMAMBA_RGB_TEXTURE_ROOT"
        if args.texture_type == "rgb_texture"
        else "REPROJECT_GAZE_CSV_MESHMAMBA_NON_TEXTURE_ROOT"
    )
    if args.csv_root is None:
        args.csv_root = _env_path("MESHMAMBA_CSV_ROOT", csv_secondary)

    json_secondary = (
        "REPROJECT_GAZE_JSON_MESHMAMBA_RGB_TEXTURE_ROOT"
        if args.texture_type == "rgb_texture"
        else "REPROJECT_GAZE_JSON_MESHMAMBA_NON_TEXTURE_ROOT"
    )
    if args.json_root is None:
        args.json_root = _env_path("MESHMAMBA_JSON_ROOT", json_secondary)

    return args


W_OUT, H_OUT = 640, 360   # output panel size in pixels
LABEL_H = 22              # height of text label strip
HEADER_H = 24
METHOD_NAME = "screen_space_gaussian"


def _normalise(arr: np.ndarray) -> np.ndarray:
    lo, hi = arr.min(), arr.max()
    if hi <= lo:
        return np.zeros_like(arr)
    return (arr - lo) / (hi - lo)


def _apply_colormap_hot(arr01: np.ndarray) -> np.ndarray:
    """Map [0,1] float array → (H,W,3) uint8 using a 'hot' palette."""
    r = np.clip(arr01 * 3.0,       0, 1)
    g = np.clip(arr01 * 3.0 - 1.0, 0, 1)
    b = np.clip(arr01 * 3.0 - 2.0, 0, 1)
    return (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)


def _apply_colormap_plasma(val01: float) -> tuple[int, int, int]:
    """Single value [0,1] → (R,G,B) uint8 via plasma-like palette."""
    # plasma approximation: dark purple → magenta → yellow
    r = int(np.clip(val01 * 2.5 - 0.2, 0, 1) * 255)
    g = int(np.clip(val01 * 1.5 - 0.3, 0, 1) * 255)
    b = int(np.clip(1.0 - val01 * 1.8, 0, 1) * 255)
    return (r, g, b)


def make_density_panel(density: np.ndarray, title: str) -> Image.Image:
    """Render density map (H,W float) as a labelled image."""
    dn = _normalise(density)
    dn_resized = np.array(
        Image.fromarray(_apply_colormap_hot(dn)).resize((W_OUT, H_OUT), Image.BILINEAR)
    )
    img = Image.fromarray(dn_resized)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, H_OUT - LABEL_H, W_OUT, H_OUT], fill=(30, 30, 30))
    draw.text((4, H_OUT - LABEL_H + 3), title, fill=(220, 220, 220))
    return img


def make_scatter_panel(density: np.ndarray, screen_xy: np.ndarray,
                        visible: np.ndarray, values: np.ndarray,
                        title: str) -> Image.Image:
    """Render density bg + face-centroid scatter coloured by values."""
    dn = _normalise(density)
    bg = np.array(
        Image.fromarray(_apply_colormap_hot(dn)).resize((W_OUT, H_OUT), Image.BILINEAR)
    ).copy()
    # darken bg for readability
    bg = (bg * 0.45).astype(np.uint8)
    img = Image.fromarray(bg)
    draw = ImageDraw.Draw(img)

    vis_xy  = screen_xy[visible]
    vis_val = values[visible]
    vmax = float(vis_val.max()) if vis_val.max() > 0 else 1.0

    for (sx, sy), v in zip(vis_xy, vis_val):
        if not (0 <= sx <= 1 and 0 <= sy <= 1):
            continue
        px = int(sx * (W_OUT - 1))
        py = int(sy * (H_OUT - 1))
        col = _apply_colormap_plasma(float(v) / vmax)
        draw.ellipse([px - 1, py - 1, px + 1, py + 1], fill=col)

    draw.rectangle([0, H_OUT - LABEL_H, W_OUT, H_OUT], fill=(30, 30, 30))
    draw.text((4, H_OUT - LABEL_H + 3), title, fill=(220, 220, 220))
    return img


def hstack_images(images: list[Image.Image], gap: int = 4) -> Image.Image:
    w = sum(im.width for im in images) + gap * (len(images) - 1)
    h = max(im.height for im in images)
    out = Image.new("RGB", (w, h), (20, 20, 20))
    x = 0
    for im in images:
        out.paste(im, (x, 0))
        x += im.width + gap
    return out


def add_header(image: Image.Image, text: str) -> Image.Image:
    out = Image.new("RGB", (image.width, image.height + HEADER_H), (20, 20, 20))
    out.paste(image, (0, HEADER_H))
    draw = ImageDraw.Draw(out)
    draw.rectangle([0, 0, image.width, HEADER_H], fill=(18, 18, 18))
    draw.text((6, 5), text, fill=(235, 235, 235))
    return out


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    dataset_label = f"MeshMamba/{args.texture_type}"
    output_stem = f"{args.model}__{METHOD_NAME}"

    # ── locate files ──────────────────────────────────────────────
    texture_type = args.texture_type
    obj_path  = find_obj_file(args.dataset_root / "MeshFile" / texture_type, args.model)
    gt_candidates = [obj_path.stem]
    resolved_stem = obj_path.resolve().stem
    if resolved_stem not in gt_candidates:
        gt_candidates.append(resolved_stem)
    gt_path   = find_gt_file(
        args.dataset_root / "SaliencyMap" / texture_type,
        args.model,
        extra_candidate_names=gt_candidates,
    )
    csv_path  = find_csv_file(args.csv_root, args.model)
    json_path = find_json_file(args.json_root, args.model, texture_type)

    print(f"DATASET: {dataset_label}")
    print(f"MODEL  : {args.model}")
    print(f"METHOD : {METHOD_NAME}")
    print(f"OBJ    : {obj_path}")
    print(f"GT     : {gt_path}")
    print(f"CSV    : {csv_path}")
    print(f"JSON   : {json_path}")

    # ── load data ─────────────────────────────────────────────────
    mesh = trimesh.load(str(obj_path), process=False)
    if not isinstance(mesh, trimesh.Trimesh):
        raise SystemExit(f"Expected Trimesh, got {type(mesh)}")

    with json_path.open() as f:
        camera_data = json.load(f)

    gt = np.loadtxt(gt_path)
    gt_norm = _normalise(gt)

    gaze_batches, stats = load_gaze_batches(
        csv_path,
        fps=int(camera_data["video_info"]["fps"]),
        total_frames=int(camera_data["video_info"]["total_frames"]),
    )
    frames_list = camera_data["frames"]
    print(f"Frames with gaze: {len(gaze_batches)}  |  total gaze points: {stats['num_points']}")

    # ── camera setup ──────────────────────────────────────────────
    proj_mat, _ = resolve_projection_matrix(
        camera_data, override_fov_deg=None,
        projection_fov_mode="horizontal_to_vertical",
    )
    cam = camera_data["camera_static"]
    view_matrix = np.asarray(cam["view_matrix"], dtype=np.float64).reshape(4, 4)
    camera_world = np.linalg.inv(view_matrix)[:3, 3]

    # ── mesh setup ────────────────────────────────────────────────
    verts = np.asarray(mesh.vertices, dtype=np.float64)
    bbox_center = 0.5 * (verts.min(0) + verts.max(0))
    base_centroids = np.asarray(mesh.triangles_center, dtype=np.float64) - bbox_center
    base_normals   = np.asarray(mesh.face_normals, dtype=np.float64)

    # ── accumulate full predicted saliency (all frames) ───────────
    n_faces   = len(mesh.faces)
    face_sal  = np.zeros(n_faces, dtype=np.float64)
    total_w   = 0.0

    frame_data: dict[int, dict] = {}   # cache per-frame data for preview

    for frame, batch in gaze_batches.items():
        n = int(batch.x_norm.size)
        if n == 0 or frame >= len(frames_list):
            continue

        hist = np.zeros((_IMG_H, _IMG_W), dtype=np.float64)
        _deposit_bilinear_batch(hist, batch.x_norm * (_IMG_W - 1),
                                      batch.y_norm * (_IMG_H - 1))
        density = gaussian_filter(hist, sigma=args.sigma_px, mode="constant")
        s = float(density.sum())
        if s > 0:
            density /= s

        rot_z = float(frames_list[frame]["rotation_z_radians"])
        centroids_w = _apply_transform_no_recenter(
            base_centroids, camera_data, rot_z, 0.0, 90.0, 0.0, "blender_rig")
        normals_w = _apply_normal_transform(
            base_normals, rot_z, 0.0, 90.0, 0.0, "blender_rig")

        screen_xy, w_clip = world_to_screen(centroids_w, view_matrix, proj_mat)
        behind = w_clip <= 0
        to_cam = camera_world[None, :] - centroids_w
        front  = np.einsum("ij,ij->i", normals_w, to_cam) > 0.0
        visible = (~behind) & front

        screen_xy_cull = screen_xy.copy()
        screen_xy_cull[~visible] = -1.0

        from reprojection_methods.screen_space_gaussian.eval_meshmamba_screen_space_v2 import bilinear_sample
        sample = bilinear_sample(density, screen_xy_cull)

        face_sal += n * sample
        total_w  += n

        frame_data[frame] = dict(
            density=density.copy(),
            screen_xy=screen_xy.copy(),
            visible=visible.copy(),
            sample=sample.copy(),
            gaze_x=batch.x_norm.copy(),
            gaze_y=batch.y_norm.copy(),
            n=n,
        )

    if total_w > 0:
        face_sal /= total_w
    pred_norm = _normalise(face_sal)

    # ── choose preview frames ─────────────────────────────────────
    sorted_frames = sorted(gaze_batches.keys())
    if args.preview_frames:
        chosen = args.preview_frames
    else:
        k = len(sorted_frames)
        chosen = [sorted_frames[k // 4], sorted_frames[k // 2], sorted_frames[3 * k // 4]]

    # ── per-frame figures ─────────────────────────────────────────
    for fr in chosen:
        if fr not in frame_data:
            print(f"Frame {fr} not in gaze data, skipping.")
            continue
        fd = frame_data[fr]
        vis = fd["visible"]
        sxy = fd["screen_xy"]
        density = fd["density"]

        # panel 1: density + raw gaze dots
        p1 = make_density_panel(density, f"Gaze density  frame={fr}  n={fd['n']}")
        d1 = ImageDraw.Draw(p1)
        for gx, gy in zip(fd["gaze_x"], fd["gaze_y"]):
            px, py = int(gx * (W_OUT - 1)), int(gy * (H_OUT - 1))
            d1.ellipse([px - 2, py - 2, px + 2, py + 2], fill=(0, 255, 255))

        # panel 2: predicted saliency scatter
        p2 = make_scatter_panel(density, sxy, vis, fd["sample"],
                                "Predicted saliency (face centroids)")

        # panel 3: GT saliency scatter
        p3 = make_scatter_panel(density, sxy, vis, gt_norm,
                                "GT saliency (face centroids)")

        row = hstack_images([p1, p2, p3])
        row = add_header(
            row,
            f"dataset={dataset_label} | model={args.model} | method={METHOD_NAME} | frame={fr:04d}",
        )
        out = args.output_dir / f"{output_stem}__frame{fr:04d}.png"
        row.save(out)
        print(f"Saved: {out}")

    # ── summary: accumulated pred vs GT at mid-rotation view ─────
    mid_fr = sorted_frames[len(sorted_frames) // 2]
    fd_mid = frame_data[mid_fr]

    p_pred = make_scatter_panel(
        np.zeros((_IMG_H, _IMG_W)),   # black bg
        fd_mid["screen_xy"], fd_mid["visible"], pred_norm,
        "Predicted — accumulated (v2)",
    )
    p_gt = make_scatter_panel(
        np.zeros((_IMG_H, _IMG_W)),
        fd_mid["screen_xy"], fd_mid["visible"], gt_norm,
        "GT saliency",
    )
    summary = hstack_images([p_pred, p_gt])
    summary = add_header(
        summary,
        f"dataset={dataset_label} | model={args.model} | method={METHOD_NAME} | summary=accumulated_vs_gt",
    )
    out_summary = args.output_dir / f"{output_stem}__summary.png"
    summary.save(out_summary)
    print(f"Saved summary: {out_summary}")
    print(f"\nAll images in: {args.output_dir}")


if __name__ == "__main__":
    main()
