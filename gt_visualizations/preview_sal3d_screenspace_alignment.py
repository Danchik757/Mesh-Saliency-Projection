#!/usr/bin/env python3
"""
Visual sanity check for the SAL3D screen_space_gaussian projection method.

Produces PNG images to verify that:
  1. The 2D gaze density and projected vertex locations are spatially aligned.
  2. High-gaze areas map to the expected mesh vertices.
  3. The accumulated predicted mesh saliency looks plausible relative to GT.

=== Three panels per frame ===

  LEFT   — Gaze density  (INPUT to the method)
           2D histogram of raw eye-tracker fixations for that frame,
           blurred with the same Gaussian used by screen_space_gaussian.
           Cyan dots = individual raw gaze points.

  MIDDLE — Predicted saliency  (OUR RESULT)
           Each dot = one visible mesh vertex projected to screen.
           Colour = per-vertex saliency value assigned by the method.

  RIGHT  — GT saliency  (REFERENCE / GROUND TRUTH)
           Same vertex projection but coloured by the aligned SAL3D GT
           loaded from Gaze/<model>.txt (optionally Smooth_Gaze-smoothed).

=== Summary image ===

  Two panels: accumulated predicted saliency vs GT at a mid-rotation frame.

=== Outputs ===

  <output-dir>/<model>__<method>__frame<NNNN>.png   — 3-panel image per frame
  <output-dir>/<model>__<method>__summary.png       — accumulated pred vs GT

=== Usage ===

  source test/env/local_paths.example.sh
  python3 gt_visualizations/preview_sal3d_screenspace_alignment.py \\
      --model bunny --output-dir /tmp/preview_sal3d
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_filter

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from reprojection_methods.screen_space_gaussian.eval_sal3d_screen_space import (
    _IMG_H,
    _IMG_W,
    _apply_normal_transform,
    _apply_transform_no_recenter,
    _deposit_bilinear_batch,
    bilinear_sample,
    get_view_matrix,
    load_gaze_batches,
    load_gt_aligned_to_obj,
    load_smooth_gaze,
    resolve_model_paths,
    resolve_projection_matrix,
    world_to_screen,
)


W_OUT = 640
H_OUT = 360
LABEL_H = 22
HEADER_H = 24
METHOD_NAME = "screen_space_gaussian"


def _env_path(primary: str, secondary: str, fallback: str = "") -> Path:
    return Path(os.environ.get(primary) or os.environ.get(secondary) or fallback)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="bunny")
    p.add_argument("--sigma-px", type=float, default=26.3)
    p.add_argument(
        "--preview-frames",
        nargs="+",
        type=int,
        default=None,
        help="Frame indices to preview. Default: 3 evenly spaced.",
    )
    p.add_argument("--output-dir", type=Path, default=Path("/tmp/preview_sal3d_v2"))
    p.add_argument(
        "--dataset-root",
        type=Path,
        default=_env_path("SAL3D_DATASET_ROOT", "REPROJECT_DATASET_SAL3D_ROOT"),
    )
    p.add_argument(
        "--csv-root",
        type=Path,
        default=_env_path("SAL3D_CSV_ROOT", "REPROJECT_GAZE_CSV_SAL3D_ROOT"),
    )
    p.add_argument(
        "--json-root",
        type=Path,
        default=_env_path("SAL3D_JSON_ROOT", "REPROJECT_GAZE_JSON_SAL3D_ROOT"),
    )
    p.add_argument("--gt-column", type=int, choices=[6, 7], default=6)
    p.add_argument(
        "--smooth-gaze-dir",
        type=Path,
        default=_env_path("SAL3D_SMOOTH_GAZE_DIR", "REPROJECT_SAL3D_SMOOTH_GAZE_ROOT"),
    )
    p.add_argument("--smooth-ratio", type=int, default=500)
    p.add_argument(
        "--recenter-to-bbox-center",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    p.add_argument("--base-rotate-z-deg", type=float, default=0.0)
    p.add_argument("--extra-rotate-x-deg", type=float, default=90.0)
    p.add_argument("--extra-rotate-y-deg", type=float, default=0.0)
    p.add_argument("--override-fov-deg", type=float, default=None)
    p.add_argument(
        "--projection-fov-mode",
        choices=["vertical", "horizontal_to_vertical", "json"],
        default="horizontal_to_vertical",
    )
    p.add_argument(
        "--transform-order",
        choices=["eval", "blender_rig"],
        default="blender_rig",
    )
    return p.parse_args()


def _normalise(arr: np.ndarray) -> np.ndarray:
    arr = np.asarray(arr, dtype=np.float64)
    lo, hi = float(arr.min()), float(arr.max())
    if hi <= lo:
        return np.zeros_like(arr)
    return (arr - lo) / (hi - lo)


def _apply_colormap_hot(arr01: np.ndarray) -> np.ndarray:
    r = np.clip(arr01 * 3.0, 0, 1)
    g = np.clip(arr01 * 3.0 - 1.0, 0, 1)
    b = np.clip(arr01 * 3.0 - 2.0, 0, 1)
    return (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)


def _apply_colormap_plasma(val01: float) -> tuple[int, int, int]:
    r = int(np.clip(val01 * 2.5 - 0.2, 0, 1) * 255)
    g = int(np.clip(val01 * 1.5 - 0.3, 0, 1) * 255)
    b = int(np.clip(1.0 - val01 * 1.8, 0, 1) * 255)
    return (r, g, b)


def make_density_panel(density: np.ndarray, title: str) -> Image.Image:
    dn = _normalise(density)
    dn_resized = np.array(
        Image.fromarray(_apply_colormap_hot(dn)).resize((W_OUT, H_OUT), Image.BILINEAR)
    )
    img = Image.fromarray(dn_resized)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, H_OUT - LABEL_H, W_OUT, H_OUT], fill=(30, 30, 30))
    draw.text((4, H_OUT - LABEL_H + 3), title, fill=(220, 220, 220))
    return img


def make_scatter_panel(
    density: np.ndarray,
    screen_xy: np.ndarray,
    visible: np.ndarray,
    values: np.ndarray,
    title: str,
    extra_mask: np.ndarray | None = None,
) -> Image.Image:
    dn = _normalise(density)
    bg = np.array(
        Image.fromarray(_apply_colormap_hot(dn)).resize((W_OUT, H_OUT), Image.BILINEAR)
    ).copy()
    bg = (bg * 0.45).astype(np.uint8)
    img = Image.fromarray(bg)
    draw = ImageDraw.Draw(img)

    mask = visible.copy()
    if extra_mask is not None:
        mask &= np.asarray(extra_mask, dtype=bool)

    vis_xy = screen_xy[mask]
    vis_val = values[mask]
    pos = vis_val > 0.0
    vis_xy = vis_xy[pos]
    vis_val = vis_val[pos]
    vmax = float(vis_val.max()) if vis_val.size and vis_val.max() > 0 else 1.0

    for (sx, sy), v in zip(vis_xy, vis_val):
        if not (0.0 <= sx <= 1.0 and 0.0 <= sy <= 1.0):
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
    dataset_label = "SAL3D"
    output_stem = f"{args.model}__{METHOD_NAME}"

    paths = resolve_model_paths(args)
    with paths["json"].open("r", encoding="utf-8") as f:
        camera_data = json.load(f)

    print(f"DATASET: {dataset_label}")
    print(f"MODEL  : {args.model}")
    print(f"METHOD : {METHOD_NAME}")
    print(f"OBJ    : {paths['obj']}")
    print(f"GT     : {paths['gt']}")
    print(f"CSV    : {paths['csv']}")
    print(f"JSON   : {paths['json']}")

    mesh = trimesh.load(str(paths["obj"]), process=False)
    if not isinstance(mesh, trimesh.Trimesh):
        raise SystemExit(f"Expected Trimesh, got {type(mesh)}")

    smooth_gaze = None
    if args.smooth_gaze_dir and Path(args.smooth_gaze_dir).is_dir():
        smooth_gaze = load_smooth_gaze(args.smooth_gaze_dir, args.model)

    gt, gt_mask, gt_smoothed = load_gt_aligned_to_obj(
        paths["gt"],
        np.asarray(mesh.vertices),
        args.gt_column,
        smooth_gaze=smooth_gaze,
        smooth_ratio=args.smooth_ratio,
    )
    gt_norm = _normalise(gt)
    print(
        f"GT covered vertices: {int(gt_mask.sum())}/{len(gt_mask)}"
        f"  |  smoothed={gt_smoothed}"
    )

    gaze_batches, stats = load_gaze_batches(
        paths["csv"],
        fps=int(camera_data["video_info"]["fps"]),
        total_frames=int(camera_data["video_info"]["total_frames"]),
    )
    frames_list = camera_data["frames"]
    print(f"Frames with gaze: {len(gaze_batches)}  |  total gaze points: {stats['num_points']}")

    proj_mat, _ = resolve_projection_matrix(
        camera_data,
        override_fov_deg=args.override_fov_deg,
        mode=args.projection_fov_mode,
    )
    view_matrix = get_view_matrix(camera_data)
    camera_world = np.linalg.inv(view_matrix)[:3, 3]

    base_verts = np.asarray(mesh.vertices, dtype=np.float64).copy()
    base_normals = np.asarray(mesh.vertex_normals, dtype=np.float64).copy()
    if args.recenter_to_bbox_center:
        bbox_center = 0.5 * (base_verts.min(axis=0) + base_verts.max(axis=0))
        base_verts -= bbox_center

    vert_sal = np.zeros(len(base_verts), dtype=np.float64)
    total_w = 0.0
    frame_data: dict[int, dict[str, np.ndarray | int]] = {}

    for frame, batch in gaze_batches.items():
        n = int(batch.x_norm.size)
        if n == 0 or frame >= len(frames_list):
            continue

        hist = np.zeros((_IMG_H, _IMG_W), dtype=np.float64)
        _deposit_bilinear_batch(hist, batch.x_norm * (_IMG_W - 1), batch.y_norm * (_IMG_H - 1))
        density = gaussian_filter(hist, sigma=args.sigma_px, mode="constant")
        density_sum = float(density.sum())
        if density_sum > 0.0:
            density /= density_sum

        rot_z = float(frames_list[frame]["rotation_z_radians"])
        verts_w = _apply_transform_no_recenter(
            base_verts,
            camera_data,
            rot_z,
            args.base_rotate_z_deg,
            args.extra_rotate_x_deg,
            args.extra_rotate_y_deg,
            args.transform_order,
        )
        normals_w = _apply_normal_transform(
            base_normals,
            rot_z,
            args.base_rotate_z_deg,
            args.extra_rotate_x_deg,
            args.extra_rotate_y_deg,
            args.transform_order,
        )

        screen_xy, w_clip = world_to_screen(verts_w, view_matrix, proj_mat)
        behind = w_clip <= 0
        to_cam = camera_world[None, :] - verts_w
        front = np.einsum("ij,ij->i", normals_w, to_cam) > 0.0
        visible = (~behind) & front

        screen_xy_cull = screen_xy.copy()
        screen_xy_cull[~visible] = -1.0
        sample = bilinear_sample(density, screen_xy_cull)

        vert_sal += n * sample
        total_w += n

        frame_data[frame] = {
            "density": density.copy(),
            "screen_xy": screen_xy.copy(),
            "visible": visible.copy(),
            "sample": sample.copy(),
            "gaze_x": batch.x_norm.copy(),
            "gaze_y": batch.y_norm.copy(),
            "n": n,
        }

    if total_w > 0.0:
        vert_sal /= total_w
    pred_norm = _normalise(vert_sal)

    sorted_frames = sorted(gaze_batches.keys())
    if not sorted_frames:
        raise SystemExit("No valid gaze frames found in the CSV.")

    if args.preview_frames:
        chosen = args.preview_frames
    else:
        k = len(sorted_frames)
        chosen = [sorted_frames[k // 4], sorted_frames[k // 2], sorted_frames[3 * k // 4]]

    for fr in chosen:
        if fr not in frame_data:
            print(f"Frame {fr} not in gaze data, skipping.")
            continue

        fd = frame_data[fr]
        density = fd["density"]
        visible = fd["visible"]
        screen_xy = fd["screen_xy"]

        p1 = make_density_panel(density, f"Gaze density  frame={fr}  n={fd['n']}")
        d1 = ImageDraw.Draw(p1)
        for gx, gy in zip(fd["gaze_x"], fd["gaze_y"]):
            px = int(gx * (W_OUT - 1))
            py = int(gy * (H_OUT - 1))
            d1.ellipse([px - 2, py - 2, px + 2, py + 2], fill=(0, 255, 255))

        p2 = make_scatter_panel(
            density,
            screen_xy,
            visible,
            fd["sample"],
            "Predicted saliency (vertex projections)",
        )
        p3 = make_scatter_panel(
            density,
            screen_xy,
            visible,
            gt_norm,
            "GT saliency (aligned vertices)",
            extra_mask=gt_mask,
        )

        row = hstack_images([p1, p2, p3])
        row = add_header(
            row,
            f"dataset={dataset_label} | model={args.model} | method={METHOD_NAME} | frame={fr:04d}",
        )
        out = args.output_dir / f"{output_stem}__frame{fr:04d}.png"
        row.save(out)
        print(f"Saved: {out}")

    mid_fr = sorted_frames[len(sorted_frames) // 2]
    fd_mid = frame_data[mid_fr]
    p_pred = make_scatter_panel(
        np.zeros((_IMG_H, _IMG_W)),
        fd_mid["screen_xy"],
        fd_mid["visible"],
        pred_norm,
        "Predicted — accumulated",
    )
    p_gt = make_scatter_panel(
        np.zeros((_IMG_H, _IMG_W)),
        fd_mid["screen_xy"],
        fd_mid["visible"],
        gt_norm,
        "GT saliency",
        extra_mask=gt_mask,
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
