#!/usr/bin/env python3
"""
Batch runner: render rc3 fixation JSON overlay videos for multiple models.

Discovers models by scanning --fixation-root for fixations.json files,
then matches each to a source video under --video-root.

Output layout:
  {output-root}/{mode}/{dataset}/{model}/overlay.mp4
  {output-root}/{mode}/{dataset}/{model}/manifest.json
  {output-root}/manifest.json   (combined, all models)
  {output-root}/manifest.csv    (combined, all models)

Usage:
  python video_creation/gaze_heatmap_overlays/run_batch_gaze_overlay.py \\
    --fixation-root /data/rc3/participant_fixations_offset0_full_cleaned \\
    --video-root    /data/rc3/source_videos \\
    --output-root   results/gaze_overlays \\
    --mode          full_video_overlay \\
    --models        3DVA_A380 SAL3D_bunny MeshMamba_non_texture_Starfruit_L3

  # Dry run (list models, find videos, no rendering):
  python ... --dry-run

  # Full batch (all models with matching videos):
  python ... --mode benchmark_one_turn_overlay
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from video_creation.gaze_heatmap_overlays.render_fixation_overlay import (
    DEFAULT_EXCLUDED,
    MODES,
    detect_dataset,
    parse_model_key,
    render_fixation_overlay,
)

# Manifest CSV column order
_CSV_FIELDS = [
    "model_key", "dataset", "track", "model", "mode",
    "fixation_format", "fixation_json_path", "video_path", "output_path",
    "n_json_frames", "frame_count", "fps", "resolution",
    "crop_start_sec", "crop_end_sec", "status", "error",
]


def find_fixation_files(fixation_root: Path) -> list[Path]:
    return sorted(fixation_root.glob("*/fixations.json"))


def find_video(video_root: Path, model_key: str) -> Path | None:
    for p in sorted(video_root.rglob(f"{model_key}.mp4")):
        return p
    return None


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


def discover_models(
    fixation_root: Path,
    video_root: Path,
    filter_models: list[str] | None,
    excluded: frozenset[str],
) -> list[dict]:
    entries = []
    for fix_path in find_fixation_files(fixation_root):
        model_key = fix_path.parent.name
        try:
            info = parse_model_key(model_key)
        except ValueError as e:
            print(f"[WARN] skipping unparseable model_key: {e}", file=sys.stderr)
            continue
        if model_key in excluded:
            print(f"[SKIP] excluded: {model_key}")
            continue
        if filter_models and model_key not in filter_models:
            continue
        video_path = find_video(video_root, model_key)
        entries.append({
            "model_key": model_key,
            "info": info,
            "fix_path": fix_path,
            "video_path": video_path,
        })
    return entries


def run_batch(
    fixation_root: Path,
    video_root: Path,
    output_root: Path,
    mode: str,
    filter_models: list[str] | None,
    excluded: frozenset[str],
    sigma_ref_px: float,
    map_width: int,
    map_height: int,
    max_opacity: float,
    drop_audio: bool,
    dry_run: bool,
    nice: bool,
    limit: int | None = None,
) -> None:
    entries = discover_models(fixation_root, video_root, filter_models, excluded)
    if not entries:
        print("[ERROR] No models found.", file=sys.stderr)
        sys.exit(1)

    if limit is not None:
        entries = entries[:limit]

    print(f"[INFO] mode={mode}  models={len(entries)}  dry_run={dry_run}  limit={limit}")
    for e in entries:
        video_status = str(e["video_path"]) if e["video_path"] else "VIDEO_NOT_FOUND"
        print(f"  {e['model_key']:45s}  video={video_status}")

    if dry_run:
        return

    mode_root = output_root / mode
    combined_manifest: list[dict] = []
    commit = git_commit()

    for e in entries:
        model_key = e["model_key"]
        info = e["info"]
        fix_path: Path = e["fix_path"]
        video_path: Path | None = e["video_path"]

        dataset_dir = f"{info['dataset']}_{info['track']}" if info["track"] else info["dataset"]
        out_dir = mode_root / dataset_dir / info["model"]
        out_mp4 = out_dir / "overlay.mp4"
        out_dir.mkdir(parents=True, exist_ok=True)

        row: dict = {
            "model_key": model_key,
            "dataset": info["dataset"],
            "track": info["track"],
            "model": info["model"],
            "mode": mode,
            "fixation_format": "one_turn_from_start_offset_0",
            "fixation_json_path": str(fix_path),
            "video_path": str(video_path) if video_path else "",
            "output_path": str(out_mp4),
            "n_json_frames": "",
            "frame_count": "",
            "fps": "",
            "resolution": "",
            "crop_start_sec": 0.0,
            "crop_end_sec": 0.0,
            "status": "",
            "error": "",
            "repo_commit": commit,
        }

        if video_path is None:
            row["status"] = "skipped_no_video"
            print(f"[SKIP] {model_key}: no video found under {video_root}")
            combined_manifest.append(row)
            continue

        print(f"[RENDER] {model_key}", flush=True)
        t0 = time.time()
        try:
            result = render_fixation_overlay(
                fixation_json_path=fix_path,
                video_path=video_path,
                output_path=out_mp4,
                mode=mode,
                sigma_ref_px=sigma_ref_px,
                map_width=map_width,
                map_height=map_height,
                max_opacity=max_opacity,
                drop_audio=drop_audio,
            )
            row.update({
                "n_json_frames": result["n_json_frames"],
                "frame_count": result["frame_count"],
                "fps": result["fps"],
                "resolution": result["resolution"],
                "status": "ok",
            })
            per_model_manifest = {**result, "repo_commit": commit}
            (out_dir / "manifest.json").write_text(json.dumps(per_model_manifest, indent=2))
            elapsed = time.time() - t0
            print(f"  done in {elapsed:.1f}s — {result['frame_count']} frames → {out_mp4}", flush=True)
        except Exception as exc:
            row["status"] = "error"
            row["error"] = str(exc)
            print(f"[ERROR] {model_key}: {exc}", file=sys.stderr)

        combined_manifest.append(row)

    # Write combined manifest
    manifest_json = output_root / "manifest.json"
    manifest_csv = output_root / "manifest.csv"
    output_root.mkdir(parents=True, exist_ok=True)
    manifest_json.write_text(json.dumps(combined_manifest, indent=2))
    with manifest_csv.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_CSV_FIELDS + ["repo_commit"],
                                extrasaction="ignore")
        writer.writeheader()
        writer.writerows(combined_manifest)

    n_ok = sum(1 for r in combined_manifest if r.get("status") == "ok")
    n_skip = sum(1 for r in combined_manifest if r.get("status") == "skipped_no_video")
    n_err = sum(1 for r in combined_manifest if r.get("status") == "error")
    print(f"\n[DONE] ok={n_ok} skipped={n_skip} errors={n_err}")
    print(f"       manifest: {manifest_json}")
    print(f"       manifest: {manifest_csv}")


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Batch gaze overlay renderer using rc3 fixation JSON."
    )
    ap.add_argument("--fixation-root", type=Path, required=True,
                    help="Path to participant_fixations_offset0_full_cleaned/ directory")
    ap.add_argument("--video-root", type=Path, required=True,
                    help="Root directory containing source video MP4 files")
    ap.add_argument("--output-root", type=Path, required=True,
                    help="Output root; subdirs per mode/dataset/model are created automatically")
    ap.add_argument("--mode", choices=MODES, default="full_video_overlay")
    ap.add_argument("--models", nargs="+", default=None,
                    help="Subset of model_keys to process (e.g. 3DVA_A380 SAL3D_bunny)")
    ap.add_argument("--exclude-models", nargs="+", default=None,
                    help="Additional model_keys to exclude (default excludes 3DVA_jessi)")
    ap.add_argument("--sigma-ref-px", type=float, default=40.0)
    ap.add_argument("--map-width", type=int, default=960)
    ap.add_argument("--map-height", type=int, default=540)
    ap.add_argument("--max-opacity", type=float, default=0.82)
    ap.add_argument("--drop-audio", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="List models and videos only; do not render")
    ap.add_argument("--limit", type=int, default=None,
                    help="Process at most N models (applied after --models filter; use for smoke)")
    ap.add_argument("--nice", action="store_true",
                    help="(ignored; use 'nice -n 18 ionice -c2 -n7' in the shell wrapper)")
    return ap


def main() -> None:
    args = _build_parser().parse_args()
    excluded = DEFAULT_EXCLUDED
    if args.exclude_models:
        excluded = excluded | frozenset(args.exclude_models)

    for p, name in [(args.fixation_root, "--fixation-root"), (args.video_root, "--video-root")]:
        if not p.is_dir():
            print(f"[ERROR] {name} not found or not a directory: {p}", file=sys.stderr)
            sys.exit(1)

    run_batch(
        fixation_root=args.fixation_root,
        video_root=args.video_root,
        output_root=args.output_root,
        mode=args.mode,
        filter_models=args.models,
        excluded=excluded,
        sigma_ref_px=args.sigma_ref_px,
        map_width=args.map_width,
        map_height=args.map_height,
        max_opacity=args.max_opacity,
        drop_audio=args.drop_audio,
        dry_run=args.dry_run,
        nice=args.nice,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
