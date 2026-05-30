#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import shutil
import subprocess
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


def extract_preview_mask(image: Image.Image, threshold: float) -> np.ndarray:
    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    alpha = rgba[:, :, 3]
    if int(alpha.max()) > 0:
        return alpha > 0
    return extract_mask(image.convert("RGB"), threshold=threshold)


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Blender canonical preview + mask overlap checks for multiple manifests.")
    parser.add_argument("--manifest", type=Path, nargs="+", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--blender-bin", type=Path, default=Path("/Applications/Blender.app/Contents/MacOS/Blender"))
    parser.add_argument("--video-mask-threshold", type=float, default=10.0)
    parser.add_argument("--preview-mask-threshold", type=float, default=10.0)
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
    blender_script = repo_root / "test" / "blender_canonical" / "render_preview_from_manifest_blender.py"

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary: list[dict[str, Any]] = []

    for manifest_path in args.manifest:
        manifest_path = manifest_path.resolve()
        manifest = preview_mod.load_manifest(manifest_path)

        dataset = str(manifest["dataset"])
        model = str(manifest["model"])
        video_path = preview_mod.expand_path(manifest.get("video_path"))
        output_prefix = preview_mod.expand_path(manifest["output_prefix"])
        result_dir = args.output_dir / dataset / model
        result_dir.mkdir(parents=True, exist_ok=True)

        row: dict[str, Any] = {
            "manifest": str(manifest_path),
            "dataset": dataset,
            "model": model,
            "status": "pending",
        }

        if video_path is None or not video_path.exists():
            row["status"] = "skipped_missing_video"
            row["video_path"] = None if video_path is None else str(video_path)
            summary.append(row)
            continue

        subprocess.run(
            [
                str(args.blender_bin),
                "--background",
                "--factory-startup",
                "--python",
                str(blender_script),
                "--",
                "--manifest",
                str(manifest_path),
            ],
            check=True,
            env=os.environ.copy(),
        )

        blender_preview_path = output_prefix.with_name(output_prefix.name + "_blender.png")
        if not blender_preview_path.exists():
            raise FileNotFoundError(f"Expected Blender preview is missing: {blender_preview_path}")

        meta = json.loads(preview_mod.expand_path(manifest["json_path"]).read_text(encoding="utf-8"))
        frame_idx = int(np.clip(int(manifest.get("frame_index", 0)), 0, int(meta["video_info"]["total_frames"]) - 1))
        width, height = preview_mod.resolve_video_resolution(meta, float(manifest.get("resolution_scale", 1.0)))

        video_frame_path = result_dir / "video_frame.png"
        preview_mod.extract_video_frame_by_index(video_path=video_path, frame_index=frame_idx, output_path=video_frame_path)

        video_img = Image.open(video_frame_path).convert("RGB")
        if video_img.size != (width, height):
            video_img = video_img.resize((width, height), Image.Resampling.BILINEAR)

        preview_rgba = Image.open(blender_preview_path).convert("RGBA")
        if preview_rgba.size != video_img.size:
            preview_rgba = preview_rgba.resize(video_img.size, Image.Resampling.BILINEAR)
        preview_img = preview_rgba.convert("RGB")

        video_mask = extract_mask(video_img, threshold=args.video_mask_threshold)
        preview_mask = extract_preview_mask(preview_rgba, threshold=args.preview_mask_threshold)
        metrics = score_masks(video_mask, preview_mask)

        contour = overlay_mod.contour_from_mask(preview_mask)
        alpha_overlay = overlay_mod.make_alpha_overlay(video_img, preview_img, mask=preview_mask, alpha=0.35)
        edge_overlay = overlay_mod.make_edge_overlay(video_img, contour=contour, edge_color=(220, 20, 60))
        alpha_path = result_dir / "overlay_alpha.png"
        edge_path = result_dir / "overlay_edges.png"
        preview_copy_path = result_dir / "blender_preview.png"
        alpha_overlay.save(alpha_path)
        edge_overlay.save(edge_path)
        preview_img.save(preview_copy_path)

        row.update(
            {
                "status": "ok",
                "video_path": str(video_path),
                "video_frame": str(video_frame_path),
                "blender_preview": str(preview_copy_path),
                "overlay_alpha": str(alpha_path),
                "overlay_edges": str(edge_path),
                **metrics,
            }
        )
        summary.append(row)

    report = {
        "blender_bin": str(args.blender_bin),
        "count_total": len(summary),
        "count_ok": sum(1 for row in summary if row["status"] == "ok"),
        "count_skipped": sum(1 for row in summary if row["status"] != "ok"),
        "results": summary,
    }
    report_path = args.output_dir / "summary.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
