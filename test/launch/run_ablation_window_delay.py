#!/usr/bin/env python3
"""
Window / delay ablation runner for all three datasets and both methods.

DO NOT RUN until reviewer/controller grants explicit approval.
Target servers: vg-gml01, vg-gml02

──────────────────────────────────────────────────────────────────────────────
Window modes
──────────────────────────────────────────────────────────────────────────────

  cut_tail  (fully supported — maps directly to one_turn_from_start + delay_seconds)
  ────────
  Use the first turn_frames gaze points and first turn_frames placement frames.
  delay=0:   gaze[0:N]   -> placement[0:N]
  delay=+d:  gaze[d:d+N] -> placement[0:N]   (gaze leads placement by d frames)
  delay=-d:  gaze[0:N]   -> placement[d:d+N]  (gaze lags placement by d frames)
  Evaluator flag: --timing-contract one_turn_from_start --delay-seconds <value>

  cut_head  (requires future evaluator --window-mode flag, not yet implemented)
  ────────
  Use the LAST turn_frames gaze points and LAST turn_frames placement frames.
  Let tail = total_frames - turn_frames (= 60 for 3DVA/MM 510-frame, 60 for SAL3D 720-frame).
  delay=0:    gaze[tail:tail+N]     -> placement[tail:tail+N]
  delay=+0.2: gaze[tail+d:tail+d+N] -> placement[tail:tail+N]  (gaze leads, clamped to end)
  delay=-0.2: gaze[tail:tail+N]     -> placement[tail+d:tail+d+N]
  Evaluator flag: --window-mode cut_head --delay-seconds <value>  [NOT YET AVAILABLE]

  center  (requires future evaluator --window-mode flag, not yet implemented)
  ──────
  Use the center turn_frames gaze/placement frames.
  head_skip = (total_frames - turn_frames) // 2
  delay=0:    gaze[hs:hs+N]     -> placement[hs:hs+N]
  delay=+d:   gaze[hs+d:hs+d+N] -> placement[hs:hs+N]
  Evaluator flag: --window-mode center --delay-seconds <value>  [NOT YET AVAILABLE]

──────────────────────────────────────────────────────────────────────────────
Delay values (seconds, applied uniformly across all window modes)
──────────────────────────────────────────────────────────────────────────────
  -0.3, -0.2, -0.1, 0.0, +0.1, +0.2, +0.3

  delay=+0.2 with cut_tail, 3DVA (fps=30): gaze_start=6, so gaze[6:6+450] -> placement[0:450]

──────────────────────────────────────────────────────────────────────────────
Output
──────────────────────────────────────────────────────────────────────────────
  <batch_output_dir>/
    ablation_summary.csv    — one row per (dataset, model, method, window_mode, delay_seconds)
    ablation_rows.jsonl     — same rows as newline-delimited JSON (for streaming/append)
    per_task/<dataset>/<model>/<method>_wm<window_mode>_d<delay>/
      report.json           — evaluator JSON report
      stdout.log            — captured evaluator stdout+stderr

──────────────────────────────────────────────────────────────────────────────
Usage (DRY RUN only — do not run for real until authorized)
──────────────────────────────────────────────────────────────────────────────
  # Preview what would run (no actual evaluator calls):
  python3 test/launch/run_ablation_window_delay.py \\
      --dry-run \\
      --datasets 3dva \\
      --models A380 \\
      --window-modes cut_tail \\
      --delays 0.0 0.2 \\
      --methods screen_space

  # Real run (requires approval + server environment):
  source configs/server_vg_gml01.env
  "$REPROJECT_PYTHON" test/launch/run_ablation_window_delay.py \\
      --workers 8 \\
      --shard-index 0 --num-shards 2 \\
      --batch-output-dir "$OUTPUT_ROOT/ablation_window_delay"
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

# ── evaluator scripts ─────────────────────────────────────────────────────────

_EVAL = {
    "3dva": {
        "screen_space": REPO_ROOT / "reprojection_methods" / "screen_space_gaussian" / "eval_3dva_screen_space_combined.py",
        "cone":         REPO_ROOT / "reprojection_methods" / "cone_projection_on_mesh" / "eval_3dva_cone_combined.py",
    },
    "meshmamba_non_texture": {
        "screen_space": REPO_ROOT / "reprojection_methods" / "screen_space_gaussian" / "eval_meshmamba_screen_space.py",
        "cone":         REPO_ROOT / "reprojection_methods" / "cone_projection_on_mesh" / "eval_meshmamba_cone.py",
    },
    "meshmamba_rgb_texture": {
        "screen_space": REPO_ROOT / "reprojection_methods" / "screen_space_gaussian" / "eval_meshmamba_screen_space.py",
        "cone":         REPO_ROOT / "reprojection_methods" / "cone_projection_on_mesh" / "eval_meshmamba_cone.py",
    },
    "sal3d": {
        "screen_space": REPO_ROOT / "reprojection_methods" / "screen_space_gaussian" / "eval_sal3d_screen_space.py",
        "cone":         REPO_ROOT / "reprojection_methods" / "cone_projection_on_mesh" / "eval_sal3d_cone.py",
    },
}

# Datasets with their frame sizes and turn lengths
_DATASET_FRAMES: dict[str, dict[str, int]] = {
    "3dva":                  {"total_frames": 510, "turn_frames": 450, "fps": 30},
    "meshmamba_non_texture": {"total_frames": 510, "turn_frames": 450, "fps": 30},
    "meshmamba_rgb_texture": {"total_frames": 510, "turn_frames": 450, "fps": 30},
    "sal3d":                 {"total_frames": 720, "turn_frames": 660, "fps": 30},
}

ALL_DATASETS = list(_DATASET_FRAMES)
ALL_METHODS = ["screen_space", "cone"]
ALL_WINDOW_MODES = ["cut_tail", "cut_head", "center"]
ALL_DELAYS = [-0.3, -0.2, -0.1, 0.0, 0.1, 0.2, 0.3]

_WINDOW_MODE_EVALUATOR_READY = {"cut_tail"}

_SIGMA_DEFAULTS: dict[str, dict[str, Any]] = {
    "screen_space": {
        "3dva":                  {"sigma_px": 26.3},
        "meshmamba_non_texture": {"sigma_screen": 0.05},
        "meshmamba_rgb_texture": {"sigma_screen": 0.05},
        "sal3d":                 {"sigma_px": 26.3},
    },
    "cone": {
        "3dva":                  {"sigma_deg": 1.0, "radius_sigma_mult": 3.0},
        "meshmamba_non_texture": {"sigma_deg": 1.0, "radius_sigma_mult": 3.0},
        "meshmamba_rgb_texture": {"sigma_deg": 1.0, "radius_sigma_mult": 3.0},
        "sal3d":                 {"sigma_deg": 1.0, "radius_sigma_mult": 3.0},
    },
}

# ── output schema ─────────────────────────────────────────────────────────────

CSV_COLUMNS = [
    # identity
    "dataset",
    "model",
    "method",
    "window_mode",
    "delay_seconds",
    # sigma params
    "sigma_px",
    "sigma_screen",
    "sigma_deg",
    "radius_sigma_mult",
    # metrics
    "CC",
    "SIM",
    "KLD",
    "MSE",
    "AUC_Judd",
    "NSS",
    # report provenance
    "report_path",
    "git_commit",
    "input_type",
    "timing_contract",
    "fixation_format",
    "gaze_start_frame",
    "placement_start_frame",
    "turn_frames_used",
    "fps",
    # task status
    "status",
    "error_type",
    "error_message",
    "stdout_log_path",
    "elapsed_seconds",
]


# ── pairing documentation helpers ────────────────────────────────────────────

def describe_pairing(dataset: str, window_mode: str, delay_seconds: float) -> str:
    """Human-readable pairing description for a given (dataset, window_mode, delay)."""
    info = _DATASET_FRAMES[dataset]
    N = info["turn_frames"]
    total = info["total_frames"]
    fps = info["fps"]
    d = round(delay_seconds * fps)

    if window_mode == "cut_tail":
        g_start = max(0, d)
        p_start = max(0, -d)
        return (
            f"cut_tail: gaze[{g_start}:{g_start+N}] -> placement[{p_start}:{p_start+N}]"
            f"  (delay={delay_seconds:+.1f}s = {d:+d} frames)"
        )
    elif window_mode == "cut_head":
        tail = total - N
        g_tail = tail + max(0, d)
        p_tail = tail + max(0, -d)
        return (
            f"cut_head: gaze[{g_tail}:{g_tail+N}] -> placement[{p_tail}:{p_tail+N}]"
            f"  (tail_skip={tail}, delay={delay_seconds:+.1f}s = {d:+d} frames)"
        )
    elif window_mode == "center":
        hs = (total - N) // 2
        g_start = hs + max(0, d)
        p_start = hs + max(0, -d)
        return (
            f"center: gaze[{g_start}:{g_start+N}] -> placement[{p_start}:{p_start+N}]"
            f"  (head_skip={hs}, delay={delay_seconds:+.1f}s = {d:+d} frames)"
        )
    return f"unknown window_mode={window_mode!r}"


# ── task building ─────────────────────────────────────────────────────────────

@dataclass
class AblationTask:
    dataset: str
    model: str
    method: str
    window_mode: str
    delay_seconds: float


def build_command(task: AblationTask, args: argparse.Namespace) -> list[str] | None:
    """Return subprocess argv for this task, or None if not yet evaluator-supported."""
    if task.window_mode not in _WINDOW_MODE_EVALUATOR_READY:
        return None

    script = _EVAL[task.dataset][task.method]
    python = os.environ.get("REPROJECT_PYTHON", sys.executable)
    sigma = _SIGMA_DEFAULTS[task.method][task.dataset]

    cmd = [python, str(script)]

    # model
    cmd += ["--models", task.model]

    # timing contract
    cmd += ["--timing-contract", "one_turn_from_start"]
    cmd += ["--delay-seconds", str(task.delay_seconds)]

    # fixation root (from env or arg)
    fixation_root = getattr(args, "fixation_root", None) or os.environ.get(
        "FIXATION_ROOT",
        os.environ.get("REPROJECT_PROCESSED_FIXATIONS_ROOT", ""),
    )
    if fixation_root:
        cmd += ["--fixation-root", fixation_root]

    # dataset-specific paths from env
    if task.dataset == "3dva":
        for env_key, flag in [
            ("THREE_DVA_JSON_ROOT", "--json-root"),
            ("THREE_DVA_OBJ_ROOT", "--obj-root"),
            ("THREE_DVA_COMBINED_GT_ROOT", "--combined-gt-dir"),
        ]:
            val = os.environ.get(env_key, "")
            if val:
                cmd += [flag, val]
    elif task.dataset.startswith("meshmamba"):
        texture = task.dataset.split("_", 1)[1]
        for env_key, flag in [
            ("MESHMAMBA_JSON_ROOT", "--json-root"),
            ("MESHMAMBA_OBJ_ROOT", "--obj-root"),
            ("MESHMAMBA_GT_ROOT", "--gt-root"),
        ]:
            val = os.environ.get(env_key, "")
            if val:
                cmd += [flag, val]
        cmd += ["--texture-type", texture]
    elif task.dataset == "sal3d":
        for env_key, flag in [
            ("SAL3D_JSON_ROOT", "--json-root"),
            ("SAL3D_DATASET_ROOT", "--dataset-root"),
            ("SAL3D_FIXED_GT_DIR", "--fixed-gt-dir"),
        ]:
            val = os.environ.get(env_key, "")
            if val:
                cmd += [flag, val]

    # sigma parameters
    if task.method == "screen_space":
        if "sigma_px" in sigma:
            cmd += ["--sigma-px", str(sigma["sigma_px"])]
        elif "sigma_screen" in sigma:
            cmd += ["--sigma-screen", str(sigma["sigma_screen"])]
    elif task.method == "cone":
        cmd += [
            "--sigma-deg", str(sigma["sigma_deg"]),
            "--radius-sigma-mult", str(sigma["radius_sigma_mult"]),
        ]

    # output dir
    task_out = _task_output_dir(task, args)
    cmd += ["--output-dir", str(task_out)]

    # tag encodes window_mode and delay
    delay_tag = f"wm{task.window_mode}_d{task.delay_seconds:+.3f}".replace("+", "p").replace("-", "m").replace(".", "")
    cmd += ["--tag", f"ablation_{delay_tag}"]

    return cmd


def _task_output_dir(task: AblationTask, args: argparse.Namespace) -> Path:
    base = Path(args.batch_output_dir)
    delay_str = f"d{task.delay_seconds:+.3f}".replace("+", "p").replace("-", "m").replace(".", "")
    return base / "per_task" / task.dataset / task.model / f"{task.method}_wm{task.window_mode}_{delay_str}"


# ── task enumeration and sharding ────────────────────────────────────────────

def enumerate_models(dataset: str, args: argparse.Namespace) -> list[str]:
    if args.model_list_file:
        text = Path(args.model_list_file).read_text()
        return [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]
    if args.models:
        return args.models
    # Default: read from dataset_model_info JSON
    info_dir = REPO_ROOT / "jsons" / "dataset_model_info"
    ds_map = {
        "3dva": "3dva_models.json",
        "meshmamba_non_texture": "meshmamba_non_texture_models.json",
        "meshmamba_rgb_texture": "meshmamba_rgb_texture_models.json",
        "sal3d": "sal3d_models.json",
    }
    json_path = info_dir / ds_map[dataset]
    if not json_path.is_file():
        raise FileNotFoundError(f"model info JSON not found: {json_path}")
    data = json.loads(json_path.read_text())
    return [m["model"] for m in data["models"]]


def build_task_list(args: argparse.Namespace) -> list[AblationTask]:
    tasks: list[AblationTask] = []
    for dataset in args.datasets:
        models = enumerate_models(dataset, args)
        for model in models:
            for method in args.methods:
                for wm in args.window_modes:
                    for delay in args.delays:
                        tasks.append(AblationTask(dataset, model, method, wm, delay))
    # Shard
    if args.num_shards > 1:
        tasks = [t for i, t in enumerate(tasks) if i % args.num_shards == args.shard_index]
    return tasks


# ── task execution ───────────────────────────────────────────────────────────

def run_task(task: AblationTask, args: argparse.Namespace) -> dict[str, Any]:
    row: dict[str, Any] = {col: "" for col in CSV_COLUMNS}
    row.update({
        "dataset": task.dataset,
        "model": task.model,
        "method": task.method,
        "window_mode": task.window_mode,
        "delay_seconds": task.delay_seconds,
        "timing_contract": "one_turn_from_start",
    })
    sigma = _SIGMA_DEFAULTS[task.method][task.dataset]
    row.update(sigma)

    frame_info = _DATASET_FRAMES[task.dataset]
    fps = frame_info["fps"]
    d = round(task.delay_seconds * fps)
    row["fps"] = fps
    row["turn_frames_used"] = frame_info["turn_frames"]

    if task.window_mode == "cut_tail":
        row["gaze_start_frame"] = max(0, d)
        row["placement_start_frame"] = max(0, -d)
    elif task.window_mode == "cut_head":
        tail = frame_info["total_frames"] - frame_info["turn_frames"]
        row["gaze_start_frame"] = tail + max(0, d)
        row["placement_start_frame"] = tail + max(0, -d)
    elif task.window_mode == "center":
        hs = (frame_info["total_frames"] - frame_info["turn_frames"]) // 2
        row["gaze_start_frame"] = hs + max(0, d)
        row["placement_start_frame"] = hs + max(0, -d)

    if task.window_mode not in _WINDOW_MODE_EVALUATOR_READY:
        row["status"] = "skipped"
        row["error_type"] = "window_mode_not_implemented"
        row["error_message"] = (
            f"window_mode={task.window_mode!r} requires --window-mode evaluator support "
            f"(not yet available). Pairing: {describe_pairing(task.dataset, task.window_mode, task.delay_seconds)}"
        )
        return row

    cmd = build_command(task, args)
    task_out = _task_output_dir(task, args)
    task_out.mkdir(parents=True, exist_ok=True)
    log_path = task_out / "stdout.log"
    row["stdout_log_path"] = str(log_path)

    if args.dry_run:
        row["status"] = "dry_run"
        row["error_message"] = " ".join(cmd)
        print(f"[dry-run] {task.dataset}/{task.model}/{task.method} wm={task.window_mode} d={task.delay_seconds:+.1f}:")
        print(f"          {' '.join(cmd)}")
        return row

    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=getattr(args, "timeout_seconds", 3600),
        )
        elapsed = time.monotonic() - t0
        row["elapsed_seconds"] = round(elapsed, 1)
        log_path.write_bytes(proc.stdout)
        if proc.returncode != 0:
            row["status"] = "evaluator_error"
            row["error_type"] = "nonzero_exit"
            row["error_message"] = f"exit code {proc.returncode}"
            return row
    except subprocess.TimeoutExpired as exc:
        row["status"] = "timeout"
        row["error_type"] = "timeout"
        row["error_message"] = str(exc)
        return row
    except Exception as exc:
        row["status"] = "error"
        row["error_type"] = type(exc).__name__
        row["error_message"] = str(exc)
        return row

    # Find and parse report JSON
    report_files = sorted(task_out.rglob("*.json"))
    if not report_files:
        row["status"] = "no_report"
        row["error_type"] = "missing_report"
        return row

    report_path = report_files[0]
    row["report_path"] = str(report_path)
    try:
        report = json.loads(report_path.read_text())
    except Exception as exc:
        row["status"] = "parse_error"
        row["error_type"] = "json_parse"
        row["error_message"] = str(exc)
        return row

    # Extract metrics — prefer metrics_vs_gt_covered_only for SAL3D, metrics_full otherwise
    metrics_section = (
        report.get("metrics_vs_gt_covered_only")
        or report.get("metrics_vs_fixed_face_gt")
        or report.get("metrics_full")
        or report.get("metrics")
        or {}
    )
    for metric in ("CC", "SIM", "KLD", "MSE", "AUC_Judd", "NSS"):
        row[metric] = metrics_section.get(metric, "")

    # Provenance
    prov = report.get("participant_input", {})
    row["input_type"] = prov.get("input_mode", "")
    row["fixation_format"] = prov.get("fixation_format", "")
    row["git_commit"] = report.get("git_commit", "")

    row["status"] = "ok"
    return row


# ── output writing ───────────────────────────────────────────────────────────

def write_row(row: dict[str, Any], args: argparse.Namespace) -> None:
    out_dir = Path(args.batch_output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / "ablation_summary.csv"
    write_header = not csv_path.exists()
    with csv_path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerow(row)

    jsonl_path = out_dir / "ablation_rows.jsonl"
    with jsonl_path.open("a") as f:
        f.write(json.dumps(row) + "\n")


# ── argument parsing ─────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Window / delay ablation runner. DO NOT RUN without reviewer approval.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--datasets",
        nargs="+",
        default=ALL_DATASETS,
        choices=ALL_DATASETS,
        help="Datasets to evaluate (default: all).",
    )
    parser.add_argument(
        "--methods",
        nargs="+",
        default=ALL_METHODS,
        choices=ALL_METHODS,
        help="Projection methods (default: screen_space cone).",
    )
    parser.add_argument(
        "--window-modes",
        nargs="+",
        default=["cut_tail"],
        choices=ALL_WINDOW_MODES,
        help=(
            "Window modes. cut_tail is evaluator-ready. "
            "cut_head and center require future --window-mode evaluator support."
        ),
    )
    parser.add_argument(
        "--delays",
        nargs="+",
        type=float,
        default=ALL_DELAYS,
        metavar="SEC",
        help="Delay values in seconds (default: -0.3 -0.2 -0.1 0.0 0.1 0.2 0.3).",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=None,
        help="Explicit model names to run (overrides dataset JSON discovery).",
    )
    parser.add_argument(
        "--model-list-file",
        type=Path,
        default=None,
        metavar="FILE",
        help="Path to a text file with one model name per line.",
    )
    parser.add_argument(
        "--fixation-root",
        type=Path,
        default=None,
        metavar="DIR",
        help="Root directory for participant fixation JSONs (offset0_full_cleaned).",
    )
    parser.add_argument(
        "--batch-output-dir",
        type=Path,
        default=REPO_ROOT / "results" / "ablation_window_delay",
        metavar="DIR",
        help="Output directory for ablation_summary.csv, ablation_rows.jsonl, and per-task logs.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of parallel evaluator workers (default: 4).",
    )
    parser.add_argument(
        "--shard-index",
        type=int,
        default=0,
        metavar="I",
        help="Zero-based shard index (for distributing work across servers).",
    )
    parser.add_argument(
        "--num-shards",
        type=int,
        default=1,
        metavar="N",
        help="Total number of shards (use 2 for vg-gml01 + vg-gml02).",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=3600,
        help="Per-task timeout in seconds (default: 3600).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing. Recommended for first verification.",
    )
    return parser.parse_args()


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    args = parse_args()
    tasks = build_task_list(args)

    if args.dry_run:
        print(f"[ablation] DRY RUN — {len(tasks)} tasks across {args.workers} workers")
        print(f"[ablation] window_modes: {args.window_modes}")
        print(f"[ablation] delays:       {args.delays}")
        print(f"[ablation] datasets:     {args.datasets}")
        for task in tasks[:5]:
            print(f"  {describe_pairing(task.dataset, task.window_mode, task.delay_seconds)}")
        if len(tasks) > 5:
            print(f"  ... and {len(tasks) - 5} more")
        print()

    print(f"[ablation] total tasks: {len(tasks)}", flush=True)
    print(f"[ablation] output: {args.batch_output_dir}", flush=True)

    if args.dry_run or args.workers <= 1:
        for task in tasks:
            row = run_task(task, args)
            write_row(row, args)
            print(
                f"[ablation] {task.dataset}/{task.model}/{task.method} "
                f"wm={task.window_mode} d={task.delay_seconds:+.1f}  → {row['status']}",
                flush=True,
            )
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(run_task, task, args): task for task in tasks}
            for fut in as_completed(futures):
                task = futures[fut]
                try:
                    row = fut.result()
                except Exception as exc:
                    row = {col: "" for col in CSV_COLUMNS}
                    row.update({
                        "dataset": task.dataset,
                        "model": task.model,
                        "method": task.method,
                        "window_mode": task.window_mode,
                        "delay_seconds": task.delay_seconds,
                        "status": "exception",
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    })
                write_row(row, args)
                print(
                    f"[ablation] {task.dataset}/{task.model}/{task.method} "
                    f"wm={task.window_mode} d={task.delay_seconds:+.1f}  → {row['status']}",
                    flush=True,
                )

    print(f"[ablation] done — results in {args.batch_output_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
