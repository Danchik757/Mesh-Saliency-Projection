#!/usr/bin/env python3
"""
Derive benchmark_one_turn_overlay videos from already-rendered full_video_overlay
by trimming with ffmpeg stream-copy (no heatmap recomputation).

Reads  {output-root}/manifest.json  (full_video_overlay combined manifest)
Writes {output-root}/benchmark_one_turn_overlay/{dataset}/{model}/overlay.mp4
       {output-root}/benchmark_derived_manifest.json
       {output-root}/benchmark_derived_manifest.csv

Trim lengths (rc3 one-turn contract):
  3DVA / MeshMamba : first 450 frames
  SAL3D            : first 660 frames

Usage:
  python video_creation/gaze_heatmap_overlays/trim_benchmark_overlay.py \\
    --output-root /tmp/rc3_output

  # Dry run:
  python ... --dry-run
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path

TURN_FRAMES: dict[str, int] = {
    "3DVA": 450,
    "MeshMamba": 450,
    "SAL3D": 660,
}

_DERIVED_MODE = "benchmark_one_turn_overlay_derived_from_full"

_CSV_FIELDS = [
    "model_key", "dataset", "track", "model",
    "mode", "source_full_overlay_path",
    "output_path", "trim_frames", "fps", "resolution",
    "status", "error",
]


def _find_ffmpeg() -> str:
    for candidate in ["ffmpeg", str(Path.home() / ".local/bin/ffmpeg")]:
        try:
            subprocess.run([candidate, "-version"], capture_output=True, check=True)
            return candidate
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass
    raise RuntimeError("ffmpeg not found; install or add to PATH")


def _trim(ffmpeg: str, src: Path, dst: Path, vframes: int) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [ffmpeg, "-nostdin", "-y", "-v", "error",
         "-i", str(src),
         "-vframes", str(vframes),
         "-c", "copy",
         str(dst)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffmpeg trim failed")


def run_trim(output_root: Path, dry_run: bool) -> None:
    full_manifest_path = output_root / "manifest.json"
    if not full_manifest_path.exists():
        print(f"[ERROR] manifest not found: {full_manifest_path}", file=sys.stderr)
        sys.exit(1)

    rows: list[dict] = json.loads(full_manifest_path.read_text())
    ok_rows = [r for r in rows if r.get("status") == "ok"
               and r.get("mode") == "full_video_overlay"]

    if not ok_rows:
        print("[ERROR] No ok full_video_overlay rows found in manifest.", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] full_video_overlay ok rows: {len(ok_rows)}  dry_run={dry_run}")

    ffmpeg = _find_ffmpeg()
    bench_root = output_root / "benchmark_one_turn_overlay"
    results: list[dict] = []

    for row in ok_rows:
        dataset = row["dataset"]
        track = row.get("track", "")
        model = row["model"]
        model_key = row["model_key"]
        fps = row.get("fps", "")
        resolution = row.get("resolution", "")

        trim_frames = TURN_FRAMES.get(dataset)
        if trim_frames is None:
            print(f"[WARN] Unknown dataset {dataset!r} for {model_key}, skipping", file=sys.stderr)
            continue

        src_path = Path(row["output_path"])
        dataset_dir = f"{dataset}_{track}" if track else dataset
        dst_path = bench_root / dataset_dir / model / "overlay.mp4"

        n_full = int(row.get("frame_count") or 0)
        actual_trim = min(trim_frames, n_full) if n_full else trim_frames

        print(f"  {model_key:45s}  trim={actual_trim}/{n_full}  → {dst_path}")

        rec: dict = {
            "model_key": model_key,
            "dataset": dataset,
            "track": track,
            "model": model,
            "mode": _DERIVED_MODE,
            "source_full_overlay_path": str(src_path),
            "output_path": str(dst_path),
            "trim_frames": actual_trim,
            "fps": fps,
            "resolution": resolution,
            "status": "",
            "error": "",
        }

        if dry_run:
            rec["status"] = "dry_run"
            results.append(rec)
            continue

        if not src_path.exists():
            rec["status"] = "error"
            rec["error"] = f"source not found: {src_path}"
            print(f"[ERROR] {model_key}: source missing: {src_path}", file=sys.stderr)
            results.append(rec)
            continue

        t0 = time.time()
        try:
            _trim(ffmpeg, src_path, dst_path, actual_trim)
            rec["status"] = "ok"
            elapsed = time.time() - t0
            print(f"    done in {elapsed:.1f}s", flush=True)
            (dst_path.parent / "manifest.json").write_text(json.dumps({
                **rec,
                "source_manifest": str(full_manifest_path),
            }, indent=2))
        except Exception as exc:
            rec["status"] = "error"
            rec["error"] = str(exc)
            print(f"[ERROR] {model_key}: {exc}", file=sys.stderr)

        results.append(rec)

    out_json = output_root / "benchmark_derived_manifest.json"
    out_csv = output_root / "benchmark_derived_manifest.csv"
    if not dry_run:
        out_json.write_text(json.dumps(results, indent=2))
        with out_csv.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=_CSV_FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(results)

    n_ok = sum(1 for r in results if r["status"] == "ok")
    n_err = sum(1 for r in results if r["status"] == "error")
    n_dry = sum(1 for r in results if r["status"] == "dry_run")
    print(f"\n[DONE] ok={n_ok}  errors={n_err}  dry_run={n_dry}")
    if not dry_run:
        print(f"       manifest: {out_json}")
        print(f"       manifest: {out_csv}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Trim full_video_overlay → benchmark_one_turn_overlay via ffmpeg stream copy."
    )
    ap.add_argument("--output-root", type=Path, required=True,
                    help="Same output-root used for the full_video_overlay batch render")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print what would be trimmed without running ffmpeg")
    args = ap.parse_args()

    if not args.output_root.is_dir():
        print(f"[ERROR] --output-root not found: {args.output_root}", file=sys.stderr)
        sys.exit(1)

    run_trim(output_root=args.output_root, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
