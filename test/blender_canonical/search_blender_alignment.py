#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import subprocess
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


def extract_video_mask(image: Image.Image, threshold: float) -> np.ndarray:
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    bg = estimate_background_rgb(rgb)
    dist = np.linalg.norm(rgb - bg.reshape(1, 1, 3), axis=2)
    return dist > threshold


def extract_preview_mask(image: Image.Image, threshold: float) -> np.ndarray:
    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    alpha = rgba[:, :, 3]
    if int(alpha.max()) > 0:
        return alpha > 0
    rgb = rgba[:, :, :3].astype(np.float32)
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
    while current <= stop + 1e-9 and guard < 100000:
        values.append(round(current, 6))
        current += step
        guard += 1
    return values


def render_candidate(blender_bin: Path, blender_script: Path, manifest_path: Path) -> None:
    subprocess.run(
        [
            str(blender_bin),
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
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Grid-search Blender preview alignment by mask overlap.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--blender-bin", type=Path, default=Path("/Applications/Blender.app/Contents/MacOS/Blender"))
    parser.add_argument("--rot-x-start", type=float, required=True)
    parser.add_argument("--rot-x-stop", type=float, required=True)
    parser.add_argument("--rot-x-step", type=float, required=True)
    parser.add_argument("--rot-y-start", type=float, default=0.0)
    parser.add_argument("--rot-y-stop", type=float, default=0.0)
    parser.add_argument("--rot-y-step", type=float, default=1.0)
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
    blender_script = repo_root / "test" / "blender_canonical" / "render_preview_from_manifest_blender.py"

    manifest_path = args.manifest.resolve()
    manifest = preview_mod.load_manifest(manifest_path)
    json_path = preview_mod.expand_path(manifest["json_path"])
    video_path = preview_mod.expand_path(manifest.get("video_path"))
    if json_path is None or video_path is None or not video_path.exists():
        raise FileNotFoundError("Manifest must resolve to existing json_path and video_path")

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
    video_mask = extract_video_mask(video_img, threshold=args.video_mask_threshold)

    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="blender_align_") as tmp_raw:
        tmp_dir = Path(tmp_raw)
        for rot_x in frange(args.rot_x_start, args.rot_x_stop, args.rot_x_step):
            for rot_y in frange(args.rot_y_start, args.rot_y_stop, args.rot_y_step):
                for fov in frange(args.fov_start, args.fov_stop, args.fov_step):
                    candidate_prefix = tmp_dir / f"rx{rot_x}_ry{rot_y}_fov{fov}"
                    candidate_manifest = dict(manifest)
                    candidate_manifest["output_prefix"] = str(candidate_prefix)
                    candidate_manifest["extra_rotate_x_deg"] = float(rot_x)
                    candidate_manifest["extra_rotate_y_deg"] = float(rot_y)
                    candidate_manifest["override_fov_deg"] = float(fov)
                    candidate_manifest_path = tmp_dir / f"rx{rot_x}_ry{rot_y}_fov{fov}.json"
                    candidate_manifest_path.write_text(json.dumps(candidate_manifest), encoding="utf-8")

                    render_candidate(args.blender_bin, blender_script, candidate_manifest_path)

                    preview_path = candidate_prefix.with_name(candidate_prefix.name + "_blender.png")
                    preview_img_rgba = Image.open(preview_path).convert("RGBA")
                    if preview_img_rgba.size != video_img.size:
                        preview_img_rgba = preview_img_rgba.resize(video_img.size, Image.Resampling.BILINEAR)
                    preview_mask = extract_preview_mask(preview_img_rgba, threshold=args.preview_mask_threshold)
                    metrics = score_masks(video_mask, preview_mask)
                    results.append(
                        {
                            "rot_x_deg": rot_x,
                            "rot_y_deg": rot_y,
                            "fov_deg": fov,
                            **metrics,
                        }
                    )

        results.sort(key=lambda row: row["score"], reverse=True)
        best = results[0]

        best_manifest = dict(manifest)
        best_prefix = args.output_dir / "best_candidate"
        best_manifest["output_prefix"] = str(best_prefix)
        best_manifest["extra_rotate_x_deg"] = float(best["rot_x_deg"])
        best_manifest["extra_rotate_y_deg"] = float(best["rot_y_deg"])
        best_manifest["override_fov_deg"] = float(best["fov_deg"])
        best_manifest_path = args.output_dir / "best_candidate_manifest.json"
        best_manifest_path.write_text(json.dumps(best_manifest, indent=2), encoding="utf-8")
        render_candidate(args.blender_bin, blender_script, best_manifest_path)

    best_preview_path = best_prefix.with_name(best_prefix.name + "_blender.png")
    best_preview_rgba = Image.open(best_preview_path).convert("RGBA")
    if best_preview_rgba.size != video_img.size:
        best_preview_rgba = best_preview_rgba.resize(video_img.size, Image.Resampling.BILINEAR)
    best_preview_rgb = best_preview_rgba.convert("RGB")
    best_mask = extract_preview_mask(best_preview_rgba, threshold=args.preview_mask_threshold)
    best_contour = overlay_mod.contour_from_mask(best_mask)
    alpha_overlay = overlay_mod.make_alpha_overlay(video_img, best_preview_rgb, mask=best_mask, alpha=0.35)
    edge_overlay = overlay_mod.make_edge_overlay(video_img, contour=best_contour, edge_color=(220, 20, 60))
    alpha_path = args.output_dir / "best_overlay_alpha.png"
    edge_path = args.output_dir / "best_overlay_edges.png"
    alpha_overlay.save(alpha_path)
    edge_overlay.save(edge_path)

    report = {
        "manifest": str(manifest_path),
        "frame_index": frame_idx,
        "search_grid": {
            "rot_x": [args.rot_x_start, args.rot_x_stop, args.rot_x_step],
            "rot_y": [args.rot_y_start, args.rot_y_stop, args.rot_y_step],
            "fov": [args.fov_start, args.fov_stop, args.fov_step],
        },
        "best": best,
        "top_k": results[: args.top_k],
        "artifacts": {
            "video_frame": str(video_frame_path),
            "best_preview": str(best_preview_path),
            "best_overlay_alpha": str(alpha_path),
            "best_overlay_edges": str(edge_path),
            "best_candidate_manifest": str(best_manifest_path),
        },
    }
    report_path = args.output_dir / "alignment_search_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
