#!/usr/bin/env python3
"""
Parallel batch runner for 3DVA combined-GT reference methods.

Runs both projection methods for all 32 3DVA models against a pre-built
combined GT (produced by scripts/build_3dva_combined_gt.py).

Methods:
  screen_space  → eval_3dva_screen_space_combined.py  (1 method in report)
  cone          → eval_3dva_cone_combined.py           (2 methods: cone + raycast)
  raycast       → eval_3dva_cone_combined.py           (same script, reads raycast metrics)

Reads metrics from: metrics_vs_gt_combined.{method}.metrics_covered_only
(combined GT support mask: union over views of visibility OR (GT > 0)).

Usage example (local):
  export VISUAL_ATTENTION_3D_SHAPES_ROOT=/path/to/3DVA
  export THREE_DVA_CSV_ROOT=/path/to/csv_for_models/3DVA
  export THREE_DVA_JSON_ROOT=/path/to/Mesh-Saliency-Projection/jsons/object_placement/3dva_jsons
  export THREE_DVA_COMBINED_GT_DIR=/path/to/3DVA/CombinedGT
  python3 test/launch/run_3dva_reference_batch.py \\
      --methods screen_space cone \\
      --workers 4 \\
      --batch-output-dir results/3dva_combined_batch

Usage example (vg-intellect):
  source configs/server_vg_intellect.env
  "$REPROJECT_PYTHON" test/launch/run_3dva_reference_batch.py \\
      --methods screen_space cone \\
      --workers 6 \\
      --batch-output-dir "$OUTPUT_ROOT/3DVA_combined_batch"
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shlex
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]

SCREEN_SCRIPT = REPO_ROOT / "reprojection_methods" / "screen_space_gaussian" / "eval_3dva_screen_space_combined.py"
CONE_SCRIPT   = REPO_ROOT / "reprojection_methods" / "cone_projection_on_mesh"  / "eval_3dva_cone_combined.py"

# Methods supported by this runner.
# "cone" and "raycast" both call CONE_SCRIPT but read different keys from the report.
ALL_METHODS = ("screen_space", "cone", "raycast")

# Fixed tags — must match what the eval scripts auto-generate when these params are passed
SCREEN_TAG = "sigpx49p0_recenter_fovh2v_combined"
CONE_TAG   = "recenter_fovh2v_combined"

# A380 has multiple video_ids in the CSV — filter to the correct session
VIDEO_ID_OVERRIDES: dict[str, int] = {
    "A380": 2365,
}

LONG_COLUMNS = [
    "model",
    "method",
    "status",
    "error_type",
    "error_message",
    "report_path",
    "stdout_log_path",
    "n_vertices",
    "n_combined_nonzero",
    "n_gt_positive_vertices",
    "combined_positive_pct",
    "n_covered_vertices",
    "covered_support_pct",
    "combined_coverage_pct",
    "num_participants",
    "num_points",
    "num_frames_with_points",
    "CC",
    "SIM",
    "KLD",
    "MSE",
    "MAE",
    "Spearman",
    "Cosine",
    "AUC_Judd_gt_top_10pct_proxy",
    "AUC_Judd_gt_top_5pct_proxy",
    "AUC_Judd_gt_top_1pct_proxy",
    "NSS_gt_top_10pct_proxy",
    "NSS_gt_top_5pct_proxy",
    "NSS_gt_top_1pct_proxy",
    "PredictionSum",
    "GroundTruthSum",
    # cone/raycast only
    "hit_rate",
    "successful_hits",
    "total_gaze_points",
    # screen_space only
    "nonzero_vertices",
]

SUMMARY_METRICS = [
    "CC", "SIM", "KLD", "MSE", "MAE", "Spearman",
    "AUC_Judd_gt_top_10pct_proxy",
    "NSS_gt_top_10pct_proxy",
    "hit_rate",
]


@dataclass(frozen=True)
class Task:
    method: str
    model:  str


def _env_path(*candidates: str, fallback: str | None = None) -> Path | None:
    for key in candidates:
        val = os.environ.get(key)
        if val:
            return Path(val)
    return Path(fallback) if fallback is not None else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parallel 3DVA combined-GT reference batch runner.")
    parser.add_argument(
        "--methods",
        nargs="+",
        choices=ALL_METHODS,
        default=["screen_space", "cone", "raycast"],
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--batch-output-dir",
        type=Path,
        default=_env_path("THREE_DVA_BATCH_OUTPUT_DIR",
                          fallback=str(REPO_ROOT / "results" / "3dva_combined_batch")),
    )
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=_env_path("VISUAL_ATTENTION_3D_SHAPES_ROOT",
                          fallback="e.g. /path/to/3DVA"),
    )
    parser.add_argument(
        "--csv-root",
        type=Path,
        default=_env_path("THREE_DVA_CSV_ROOT",
                          fallback="e.g. /path/to/csv_for_models/3DVA"),
        help="CSV directory (only used with --csv-compat).",
    )
    parser.add_argument(
        "--fixation-root",
        type=Path,
        default=_env_path(
            "FIXATION_ROOT", "REPROJECT_PROCESSED_FIXATIONS_ROOT",
            "THREE_DVA_PROCESSED_FIXATIONS_ROOT",
        ),
        help="Root of processed_fixations_offset_2000/. Required unless --csv-compat.",
    )
    parser.add_argument(
        "--csv-compat",
        action="store_true",
        default=False,
        help="Use legacy CSV input (requires --csv-root).",
    )
    parser.add_argument(
        "--json-root",
        type=Path,
        default=_env_path("THREE_DVA_JSON_ROOT",
                          fallback="e.g. /path/to/Mesh-Saliency-Projection/jsons/object_placement/3dva_jsons"),
    )
    parser.add_argument(
        "--combined-gt-dir",
        type=Path,
        default=_env_path("THREE_DVA_COMBINED_GT_DIR",
                          fallback="e.g. /path/to/3DVA/CombinedGT"),
        help=(
            "Directory with pre-built combined GT files. "
            "Must contain {model}_combined_gt.txt for each model. "
            "Build with: python3 scripts/build_3dva_combined_gt.py"
        ),
    )
    parser.add_argument(
        "--models",
        nargs="*",
        default=None,
        help="Optional model subset. Default: auto-discover from combined-gt-dir.",
    )
    parser.add_argument(
        "--model-list-file",
        type=Path,
        default=None,
        help="Text file with one model name per line.",
    )
    parser.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "Skip tasks with an existing report JSON. Disabled by default because "
            "reports created with old CSV/no-crop inputs are not valid after input-contract changes."
        ),
    )
    parser.add_argument("--nice-level", type=int, default=10)
    parser.add_argument(
        "--python-bin",
        type=Path,
        default=Path(os.environ.get("REPROJECT_PYTHON", sys.executable)),
    )
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    errors: list[str] = []
    if not args.dataset_root or not Path(str(args.dataset_root)).is_dir():
        errors.append(f"--dataset-root not found: {args.dataset_root}")
    if args.csv_compat:
        if not args.csv_root or not Path(str(args.csv_root)).is_dir():
            errors.append(f"--csv-root not found (required with --csv-compat): {args.csv_root}")
    else:
        if not args.fixation_root or not Path(str(args.fixation_root)).is_dir():
            errors.append(f"--fixation-root not found: {args.fixation_root}")
    if not args.json_root or not Path(str(args.json_root)).is_dir():
        errors.append(f"--json-root not found: {args.json_root}")
    if not args.combined_gt_dir or not Path(str(args.combined_gt_dir)).is_dir():
        errors.append(
            f"--combined-gt-dir not found: {args.combined_gt_dir}\n"
            "  Run: python3 scripts/build_3dva_combined_gt.py --dataset-root <path> --output-dir <path>"
        )
    if errors:
        raise SystemExit("\n".join(errors))


def load_explicit_models(args: argparse.Namespace) -> list[str] | None:
    models: list[str] = []
    if args.models:
        models.extend(args.models)
    if args.model_list_file and args.model_list_file.is_file():
        models.extend(
            line.strip()
            for line in args.model_list_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
    if not models:
        return None
    deduped: list[str] = []
    seen: set[str] = set()
    for m in models:
        if m not in seen:
            deduped.append(m)
            seen.add(m)
    return deduped


def inventory_models(args: argparse.Namespace, explicit: list[str] | None) -> list[str]:
    """Auto-discover models as intersection of combined_gt_dir ∩ gaze_source ∩ json_root."""
    if explicit:
        return list(explicit)

    combined_gt_dir: Path = args.combined_gt_dir

    # Models with combined GT
    gt_models = {
        p.stem.replace("_combined_gt", "").lower(): p.stem.replace("_combined_gt", "")
        for p in sorted(combined_gt_dir.glob("*_combined_gt.txt"))
    }

    if args.csv_compat:
        # Legacy: models with gaze CSV
        gaze_set = {p.stem.lower() for p in sorted(Path(str(args.csv_root)).glob("*.csv"))}
    else:
        # Default: models with processed fixation JSON
        gaze_set = {
            p.parent.name[len("3DVA_"):].lower()
            for p in sorted(Path(str(args.fixation_root)).glob("3DVA_*/fixations.json"))
        }

    models = sorted(
        name for lc, name in gt_models.items()
        if lc in gaze_set
    )
    return models


def task_output_dir(batch_output_dir: Path, method: str) -> Path:
    return batch_output_dir / f"baseline_{method}"


def task_log_path(batch_output_dir: Path, method: str, model: str) -> Path:
    return batch_output_dir / "_logs" / method / f"{model}.log"


def report_path_for_task(batch_output_dir: Path, task: Task) -> Path:
    tag = SCREEN_TAG if task.method == "screen_space" else CONE_TAG
    return task_output_dir(batch_output_dir, task.method) / task.model / tag / f"{task.model}_report.json"


def build_command(args: argparse.Namespace, task: Task) -> list[str]:
    common = [
        "--model",           task.model,
        "--dataset-root",    str(args.dataset_root),
        "--json-root",       str(args.json_root),
        "--combined-gt-dir", str(args.combined_gt_dir),
        "--output-dir",      str(task_output_dir(args.batch_output_dir, task.method)),
        "--recenter-to-bbox-center",
        "--projection-fov-mode", "horizontal_to_vertical",
    ]
    if args.csv_compat:
        common += ["--csv-compat", "--csv-root", str(args.csv_root)]
    else:
        common += ["--fixation-root", str(args.fixation_root)]

    # A380 has a mixed CSV — filter to the correct video session
    if task.model in VIDEO_ID_OVERRIDES:
        common += ["--video-id", str(VIDEO_ID_OVERRIDES[task.model])]

    if task.method == "screen_space":
        return [
            str(args.python_bin), str(SCREEN_SCRIPT),
            *common,
            "--sigma-px", "49.0",
            "--tag", SCREEN_TAG,
        ]
    else:
        # Both "cone" and "raycast" invoke CONE_SCRIPT (it computes both methods).
        # We avoid running it twice by always using "cone" as the task method for
        # subprocess dispatch, then reading the correct key in collect_row_from_report().
        return [
            str(args.python_bin), str(CONE_SCRIPT),
            *common,
            "--sigma-deg", "1.0",
            "--radius-sigma-mult", "3.0",
            "--tag", CONE_TAG,
        ]


def classify_error(message: str) -> tuple[str, str]:
    msg = message.lower()
    if "combined gt not found" in msg:
        return "missing_combined_gt", message.strip()
    if "gt" in msg and "not found" in msg:
        return "missing_gt", message.strip()
    if "json" in msg and "not found" in msg:
        return "missing_json", message.strip()
    if "csv" in msg and "not found" in msg:
        return "missing_csv", message.strip()
    if "obj" in msg and "not found" in msg:
        return "missing_obj", message.strip()
    return "runtime_error", message.strip()


def _provenance_matches(report_path: Path, args: argparse.Namespace) -> bool:
    """Return True only if the existing report was produced under the same participant/timing contract."""
    try:
        existing = json.loads(report_path.read_text(encoding="utf-8"))
        prov = existing.get("participant_input", {})
        current_mode = "csv_compat" if args.csv_compat else "processed_json"
        if not (
            prov.get("input_mode") == current_mode
            and abs(float(prov.get("crop_start_seconds", -1)) - 1.8) < 1e-6
            and abs(float(prov.get("crop_end_seconds", -1)) - 0.2) < 1e-6
        ):
            return False
        if current_mode == "processed_json":
            return prov.get("fixation_format") == "cropped_reset_offset_2000"
        return True
    except Exception:
        return False


def run_task(args: argparse.Namespace, task: Task) -> dict[str, Any]:
    report_path = report_path_for_task(args.batch_output_dir, task)
    log_path    = task_log_path(args.batch_output_dir, task.method, task.model)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    if args.resume and report_path.exists():
        if _provenance_matches(report_path, args):
            return collect_row_from_report(task, report_path, status="ok", stdout_log_path=log_path)

    # For "raycast" tasks, check if the cone report already exists (same script).
    if task.method == "raycast":
        cone_report = report_path_for_task(args.batch_output_dir, Task("cone", task.model))
        if args.resume and cone_report.exists() and _provenance_matches(cone_report, args):
            return collect_row_from_report(task, cone_report, status="ok", stdout_log_path=log_path)

    cmd = build_command(args, task)
    env = os.environ.copy()
    started = time.time()
    proc = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
    )
    elapsed = time.time() - started
    log_path.write_text(
        f"$ {' '.join(shlex.quote(p) for p in cmd)}\n\n"
        f"[exit_code] {proc.returncode}\n"
        f"[elapsed_sec] {elapsed:.2f}\n\n"
        f"{proc.stdout}",
        encoding="utf-8",
    )

    if proc.returncode != 0:
        error_type, message = classify_error(proc.stdout)
        return base_row(task, status=error_type, error_type=error_type, error_message=message,
                        stdout_log_path=log_path, report_path=report_path)

    # Determine the actual report path (cone and raycast share the same JSON)
    actual_report = report_path
    if task.method == "raycast":
        actual_report = report_path_for_task(args.batch_output_dir, Task("cone", task.model))

    if not actual_report.exists():
        return base_row(task, status="runtime_error", error_type="runtime_error",
                        error_message="report json missing after successful exit",
                        stdout_log_path=log_path, report_path=actual_report)

    return collect_row_from_report(task, actual_report, status="ok", stdout_log_path=log_path)


def base_row(
    task: Task,
    *,
    status: str,
    error_type: str = "",
    error_message: str = "",
    stdout_log_path: Path | None = None,
    report_path: Path | None = None,
) -> dict[str, Any]:
    row = {key: "" for key in LONG_COLUMNS}
    row.update({
        "model":           task.model,
        "method":          task.method,
        "status":          status,
        "error_type":      error_type,
        "error_message":   error_message,
        "report_path":     str(report_path)      if report_path      else "",
        "stdout_log_path": str(stdout_log_path)  if stdout_log_path  else "",
    })
    return row


def collect_row_from_report(
    task: Task, report_path: Path, *, status: str, stdout_log_path: Path | None
) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    row = base_row(task, status=status, stdout_log_path=stdout_log_path, report_path=report_path)

    row["n_vertices"]             = report.get("n_vertices", report.get("n_eval", ""))
    row["n_combined_nonzero"]     = report.get("n_combined_nonzero", "")
    row["n_gt_positive_vertices"] = report.get("n_gt_positive_vertices", report.get("n_combined_nonzero", ""))
    row["combined_positive_pct"]  = report.get("combined_positive_pct", "")
    row["n_covered_vertices"]     = report.get("n_covered_vertices", "")
    row["covered_support_pct"]    = report.get("covered_support_pct", report.get("combined_coverage_pct", ""))
    row["combined_coverage_pct"]  = report.get("combined_coverage_pct", "")

    gaze_stats = report.get("gaze_stats", {})
    row["num_participants"]       = gaze_stats.get("num_participants", "")
    row["num_points"]             = gaze_stats.get("num_points", "")
    row["num_frames_with_points"] = gaze_stats.get("num_frames_with_points", "")

    run_stats = report.get("run_stats", {})

    # Select the correct method key from metrics_vs_gt_combined
    combined = report.get("metrics_vs_gt_combined", {})
    if task.method == "screen_space":
        method_metrics_block = combined.get("screen_space_gaussian", {})
        row["nonzero_vertices"] = run_stats.get("nonzero_vertices", "")
    elif task.method == "cone":
        method_metrics_block = combined.get("cone_gaussian_on_mesh", {})
        row["hit_rate"]          = run_stats.get("hit_rate", "")
        row["successful_hits"]   = run_stats.get("successful_hits", "")
        row["total_gaze_points"] = run_stats.get("total_gaze_points", "")
    else:  # raycast
        method_metrics_block = combined.get("raycast_nearest_vertex", {})
        row["hit_rate"]          = run_stats.get("hit_rate", "")
        row["successful_hits"]   = run_stats.get("successful_hits", "")
        row["total_gaze_points"] = run_stats.get("total_gaze_points", "")

    # Always read from metrics_covered_only (the valid benchmark domain)
    metrics = method_metrics_block.get("metrics_covered_only", {})

    for key in (
        "CC", "SIM", "KLD", "MSE", "MAE", "Spearman", "Cosine",
        "AUC_Judd_gt_top_10pct_proxy",
        "AUC_Judd_gt_top_5pct_proxy",
        "AUC_Judd_gt_top_1pct_proxy",
        "NSS_gt_top_10pct_proxy",
        "NSS_gt_top_5pct_proxy",
        "NSS_gt_top_1pct_proxy",
        "PredictionSum",
        "GroundTruthSum",
    ):
        row[key] = metrics.get(key, "")

    return row


def write_long_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LONG_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def write_wide_csv(rows: list[dict[str, Any]], path: Path, methods: list[str]) -> None:
    grouped: dict[str, dict[str, Any]] = {}
    metric_fields = [f for f in LONG_COLUMNS if f not in {"model", "method"}]

    for row in rows:
        key    = row["model"]
        target = grouped.setdefault(key, {"model": key})
        prefix = row["method"]
        for field in metric_fields:
            target[f"{prefix}_{field}"] = row.get(field, "")

    fieldnames = ["model"]
    for method in methods:
        for field in metric_fields:
            fieldnames.append(f"{method}_{field}")

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for key in sorted(grouped):
            writer.writerow(grouped[key])


def write_summary_csv(rows: list[dict[str, Any]], path: Path, methods: list[str]) -> None:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(row["method"], []).append(row)

    fieldnames = ["method", "n_total", "n_ok", "n_failed"]
    for metric in SUMMARY_METRICS:
        fieldnames.extend([f"{metric}_mean", f"{metric}_median"])

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for method in sorted(groups):
            group_rows = groups[method]
            ok_rows    = [r for r in group_rows if r["status"] == "ok"]
            summary: dict[str, Any] = {
                "method":  method,
                "n_total": len(group_rows),
                "n_ok":    len(ok_rows),
                "n_failed": len(group_rows) - len(ok_rows),
            }
            for metric in SUMMARY_METRICS:
                values = [float(r[metric]) for r in ok_rows if r.get(metric) not in ("", None)]
                summary[f"{metric}_mean"]   = mean(values)   if values else ""
                summary[f"{metric}_median"] = median(values) if values else ""
            writer.writerow(summary)


def main() -> int:
    args = parse_args()
    validate_args(args)
    args.batch_output_dir.mkdir(parents=True, exist_ok=True)

    explicit_models = load_explicit_models(args)
    models          = inventory_models(args, explicit_models)

    if not models:
        print("[ERROR] No models found. Check combined-gt-dir, csv-root, json-root.", file=sys.stderr)
        return 1

    # Deduplicate tasks: "cone" and "raycast" both call the cone script.
    # We run the subprocess once (tagged as "cone") and let both collect from it.
    subprocess_tasks: list[Task] = []
    row_tasks: list[Task] = []
    cone_scheduled: set[str] = set()

    for method in args.methods:
        for model in models:
            row_tasks.append(Task(method=method, model=model))
            if method in ("cone", "raycast"):
                if model not in cone_scheduled:
                    subprocess_tasks.append(Task(method="cone", model=model))
                    cone_scheduled.add(model)
            else:
                subprocess_tasks.append(Task(method=method, model=model))

    print(
        f"[run_3dva_reference_batch] models={len(models)}  "
        f"methods={args.methods}  "
        f"subprocess_tasks={len(subprocess_tasks)}  "
        f"result_rows={len(row_tasks)}  "
        f"workers={args.workers}"
    )

    # Run subprocesses in parallel
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(run_task, args, task): task for task in subprocess_tasks}
        for future in as_completed(futures):
            task = futures[future]
            row  = future.result()
            print(f"[done] {task.method} {task.model} -> {row['status']}")

    # Collect rows for ALL requested methods (including raycast which reuses cone report)
    rows: list[dict[str, Any]] = []
    for task in row_tasks:
        report_p = report_path_for_task(args.batch_output_dir, task)
        if task.method == "raycast":
            report_p = report_path_for_task(args.batch_output_dir, Task("cone", task.model))
        log_p = task_log_path(args.batch_output_dir, task.method, task.model)

        if report_p.exists():
            rows.append(collect_row_from_report(task, report_p, status="ok", stdout_log_path=log_p))
        else:
            rows.append(base_row(task, status="missing_report", error_type="missing_report",
                                 error_message="report not found after run", report_path=report_p))

    rows.sort(key=lambda r: (r["model"], r["method"]))

    long_csv    = args.batch_output_dir / "3dva_combined_long.csv"
    wide_csv    = args.batch_output_dir / "3dva_combined_wide.csv"
    summary_csv = args.batch_output_dir / "3dva_combined_summary.csv"

    write_long_csv(rows, long_csv)
    write_wide_csv(rows, wide_csv, list(args.methods))
    write_summary_csv(rows, summary_csv, list(args.methods))

    print(f"[run_3dva_reference_batch] long_csv={long_csv}")
    print(f"[run_3dva_reference_batch] wide_csv={wide_csv}")
    print(f"[run_3dva_reference_batch] summary_csv={summary_csv}")

    n_ok     = sum(1 for r in rows if r["status"] == "ok")
    n_failed = sum(1 for r in rows if r["status"] != "ok")
    print(f"[run_3dva_reference_batch] done: {n_ok} ok  {n_failed} failed")
    return 0 if n_failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
