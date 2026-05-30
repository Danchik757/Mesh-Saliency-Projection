#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def estimate_background_rgb(image_rgb: np.ndarray) -> np.ndarray:
    h, w, _ = image_rgb.shape
    patch = min(24, h // 4, w // 4)
    corners = np.concatenate(
        [
            image_rgb[:patch, :patch].reshape(-1, 3),
            image_rgb[:patch, w - patch :].reshape(-1, 3),
            image_rgb[h - patch :, :patch].reshape(-1, 3),
            image_rgb[h - patch :, w - patch :].reshape(-1, 3),
        ],
        axis=0,
    )
    return np.median(corners, axis=0)


def extract_mask(image: Image.Image, threshold: float) -> np.ndarray:
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    bg = estimate_background_rgb(rgb)
    dist = np.linalg.norm(rgb - bg.reshape(1, 1, 3), axis=2)
    return dist > threshold


def mask_centroid(mask: np.ndarray) -> tuple[float, float]:
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return float("nan"), float("nan")
    return float(xs.mean()), float(ys.mean())


def mask_bbox(mask: np.ndarray) -> tuple[int, int]:
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return 0, 0
    return int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)


def score_masks(video_mask: np.ndarray, preview_mask: np.ndarray) -> dict[str, float]:
    inter = float(np.logical_and(video_mask, preview_mask).sum())
    union = float(np.logical_or(video_mask, preview_mask).sum())
    iou = inter / union if union > 0 else 0.0

    vx, vy = mask_centroid(video_mask)
    px, py = mask_centroid(preview_mask)
    h, w = video_mask.shape
    diag = math.hypot(w, h)
    centroid_error = math.hypot(px - vx, py - vy) / diag if np.isfinite([vx, vy, px, py]).all() else 1.0

    vw, vh = mask_bbox(video_mask)
    pw, ph = mask_bbox(preview_mask)
    size_error = (abs(pw - vw) + abs(ph - vh)) / max(1.0, float(vw + vh))

    score = iou - 0.50 * centroid_error - 0.25 * size_error
    return {
        "score": float(score),
        "iou": float(iou),
        "centroid_error_norm": float(centroid_error),
        "size_error_norm": float(size_error),
        "video_bbox_width": int(vw),
        "video_bbox_height": int(vh),
        "preview_bbox_width": int(pw),
        "preview_bbox_height": int(ph),
    }


def frange(start: float, stop: float, step: float) -> list[float]:
    values: list[float] = []
    current = start
    guard = 0
    while current <= stop + 1e-9 and guard < 10000:
        values.append(round(current, 6))
        current += step
        guard += 1
    return values


def main() -> None:
    parser = argparse.ArgumentParser(description="Grid-search preview alignment by mask overlap.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--rot-x-start", type=float, required=True)
    parser.add_argument("--rot-x-stop", type=float, required=True)
    parser.add_argument("--rot-x-step", type=float, required=True)
    parser.add_argument("--fov-start", type=float, required=True)
    parser.add_argument("--fov-stop", type=float, required=True)
    parser.add_argument("--fov-step", type=float, required=True)
    parser.add_argument("--video-mask-threshold", type=float, default=10.0)
    parser.add_argument("--preview-mask-threshold", type=float, default=10.0)
    parser.add_argument("--top-k", type=int, default=10)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    preview_mod = load_module(
        "render_preview_from_manifest",
        repo_root / "test" / "tools" / "render_preview_from_manifest.py",
    )
    overlay_mod = load_module(
        "overlay_video_and_preview",
        repo_root / "test" / "overlay_alignment" / "overlay_video_and_preview.py",
    )

    manifest = preview_mod.load_manifest(args.manifest.resolve())
    obj_path = preview_mod.expand_path(manifest["obj_path"])
    json_path = preview_mod.expand_path(manifest["json_path"])
    video_path = preview_mod.expand_path(manifest.get("video_path"))
    if obj_path is None or json_path is None or video_path is None:
        raise ValueError("Manifest must include obj_path, json_path, and video_path")

    mesh = preview_mod.load_mesh(obj_path)
    metadata = json.loads(json_path.read_text(encoding="utf-8"))
    total_frames = int(metadata["video_info"]["total_frames"])
    frame_idx = int(np.clip(int(manifest.get("frame_index", 0)), 0, total_frames - 1))
    width, height = preview_mod.resolve_video_resolution(metadata, float(manifest.get("resolution_scale", 1.0)))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    video_frame_path = args.output_dir / "video_frame.png"
    preview_mod.extract_video_frame_by_index(video_path=video_path, frame_index=frame_idx, output_path=video_frame_path)
    video_img = Image.open(video_frame_path).convert("RGB")
    if video_img.size != (width, height):
        video_img = video_img.resize((width, height), Image.Resampling.BILINEAR)
    video_mask = extract_mask(video_img, threshold=args.video_mask_threshold)

    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="preview_align_") as tmp_dir_raw:
        tmp_dir = Path(tmp_dir_raw)
        for rot_x in frange(args.rot_x_start, args.rot_x_stop, args.rot_x_step):
            for fov in frange(args.fov_start, args.fov_stop, args.fov_step):
                preview_path = tmp_dir / f"preview_rx{rot_x}_fov{fov}.png"
                preview_mod.render_preview(
                    mesh=mesh,
                    metadata=metadata,
                    frame_idx=frame_idx,
                    output_path=preview_path,
                    width=width,
                    height=height,
                    recenter_to_bbox_center=bool(manifest.get("recenter_to_bbox_center", False)),
                    base_rotate_z_deg=float(manifest.get("base_rotate_z_deg", 0.0)),
                    extra_rotate_x_deg=rot_x,
                    extra_rotate_y_deg=float(manifest.get("extra_rotate_y_deg", 0.0)),
                    override_fov_deg=fov,
                )
                preview_img = Image.open(preview_path).convert("RGB")
                preview_mask = extract_mask(preview_img, threshold=args.preview_mask_threshold)
                metrics = score_masks(video_mask, preview_mask)
                results.append(
                    {
                        "rot_x_deg": rot_x,
                        "fov_deg": fov,
                        **metrics,
                    }
                )

        results.sort(key=lambda row: row["score"], reverse=True)
        best = results[0]
        best_preview_path = args.output_dir / "best_preview.png"
        preview_mod.render_preview(
            mesh=mesh,
            metadata=metadata,
            frame_idx=frame_idx,
            output_path=best_preview_path,
            width=width,
            height=height,
            recenter_to_bbox_center=bool(manifest.get("recenter_to_bbox_center", False)),
            base_rotate_z_deg=float(manifest.get("base_rotate_z_deg", 0.0)),
            extra_rotate_x_deg=float(best["rot_x_deg"]),
            extra_rotate_y_deg=float(manifest.get("extra_rotate_y_deg", 0.0)),
            override_fov_deg=float(best["fov_deg"]),
        )

    preview_img = Image.open(best_preview_path).convert("RGB")
    overlay_mod.main  # keep module reachable for lint-like usage
    best_mask = extract_mask(preview_img, threshold=args.preview_mask_threshold)
    best_contour = overlay_mod.contour_from_mask(best_mask)
    alpha_overlay = overlay_mod.make_alpha_overlay(video_img, preview_img, mask=best_mask, alpha=0.35)
    edge_overlay = overlay_mod.make_edge_overlay(video_img, contour=best_contour, edge_color=(220, 20, 60))
    alpha_overlay_path = args.output_dir / "best_overlay_alpha.png"
    edge_overlay_path = args.output_dir / "best_overlay_edges.png"
    alpha_overlay.save(alpha_overlay_path)
    edge_overlay.save(edge_overlay_path)

    report = {
        "manifest": str(args.manifest.resolve()),
        "frame_index": frame_idx,
        "search_grid": {
            "rot_x": [args.rot_x_start, args.rot_x_stop, args.rot_x_step],
            "fov": [args.fov_start, args.fov_stop, args.fov_step],
        },
        "best": best,
        "top_k": results[: args.top_k],
        "artifacts": {
            "video_frame": str(video_frame_path),
            "best_preview": str(best_preview_path),
            "best_overlay_alpha": str(alpha_overlay_path),
            "best_overlay_edges": str(edge_overlay_path),
        },
    }
    report_path = args.output_dir / "alignment_search_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
