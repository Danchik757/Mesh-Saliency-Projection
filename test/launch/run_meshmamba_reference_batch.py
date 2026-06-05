#!/usr/bin/env python3
"""
Parallel batch runner for MeshMamba reference methods.

Methods:
- screen_space_gaussian
- cone_gaussian_on_mesh

This script does not reimplement the metric logic. It orchestrates per-model
evaluation by calling the validated single-model eval scripts, captures logs,
and collects normalized CSV tables:
- long-format: one row per texture_type × model × method
- wide-format: one row per texture_type × model, method metrics as prefixed cols
- summary: aggregates by texture_type × method

Usage example on vg-intellect:
  source configs/server_vg_intellect.env
  "$REPROJECT_PYTHON" test/launch/run_meshmamba_reference_batch.py \
      --texture-types non_texture rgb_texture \
      --methods screen_space cone \
      --workers 4 \
      --batch-output-dir "$OUTPUT_ROOT/MeshMamba_reference_batch"
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
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
SCREEN_SCRIPT = REPO_ROOT / "reprojection_methods" / "screen_space_gaussian" / "eval_meshmamba_screen_space.py"
CONE_SCRIPT = REPO_ROOT / "reprojection_methods" / "cone_projection_on_mesh" / "eval_meshmamba_cone.py"

TEXTURE_TYPES = ("non_texture", "rgb_texture")
METHODS = ("screen_space", "cone")

SCREEN_TAG = "sigma0p05_recenter_rotx90p0_horizontaltovertical_blender_rig"
CONE_TAG = "recenter_rotx90p0_horizontaltovertical_blender_rig"

LONG_BASE_COLUMNS = [
    "texture_type",
    "model",
    "method",
    "status",
    "error_type",
    "error_message",
    "report_path",
    "stdout_log_path",
    "gt_file",
    "n_faces",
    "num_rows",
    "num_participants",
    "num_points",
    "num_frames_with_points",
    "projection_fov_mode",
    "projection_fov_source",
    "input_fov_deg",
    "effective_vertical_fov_deg",
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
    "nonzero_faces",
    "culled_back_faces",
    "hit_rate",
    "successful_hits",
    "total_gaze_points",
    "cone_nonzero_faces",
]

SUMMARY_METRICS = [
    "CC",
    "SIM",
    "KLD",
    "MSE",
    "MAE",
    "Spearman",
    "Cosine",
    "AUC_Judd_gt_top_10pct_proxy",
    "NSS_gt_top_10pct_proxy",
    "hit_rate",
]


@dataclass(frozen=True)
class Task:
    texture_type: str
    method: str
    model: str


def _env_path(*candidates: str, fallback: str | None = None) -> Path | None:
    for key in candidates:
        value = os.environ.get(key)
        if value:
            return Path(value)
    return Path(fallback) if fallback is not None else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parallel MeshMamba reference batch runner.")
    parser.add_argument(
        "--texture-types",
        nargs="+",
        choices=TEXTURE_TYPES,
        default=list(TEXTURE_TYPES),
        help="Texture tracks to evaluate.",
    )
    parser.add_argument(
        "--methods",
        nargs="+",
        choices=METHODS,
        default=list(METHODS),
        help="Reference methods to evaluate.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Max parallel per-model subprocesses.",
    )
    parser.add_argument(
        "--batch-output-dir",
        type=Path,
        default=_env_path("MESHMAMBA_BATCH_OUTPUT_DIR", "REPROJECT_OUTPUT_ROOT", fallback=str(REPO_ROOT / "results")) / "MeshMamba_reference_batch",
        help="Root output directory for batch logs, per-model outputs, and collected CSVs.",
    )
    parser.add_argument(
        "--models",
        nargs="*",
        default=None,
        help="Optional explicit model subset. If omitted, inventory is built from dataset roots.",
    )
    parser.add_argument(
        "--model-list-file",
        type=Path,
        default=None,
        help="Optional text file with one model per line.",
    )
    parser.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip tasks with an already existing report JSON.",
    )
    parser.add_argument(
        "--nice-level",
        type=int,
        default=10,
        help="nice level for subprocesses.",
    )
    parser.add_argument(
        "--python-bin",
        type=Path,
        default=Path(os.environ.get("REPROJECT_PYTHON", sys.executable)),
        help="Python interpreter used to run single-model eval scripts.",
    )
    return parser.parse_args()


def resolve_dataset_root(texture_type: str) -> Path:
    if texture_type == "non_texture":
        path = _env_path("MESHMAMBA_NON_TEXTURE_ROOT", "REPROJECT_DATASET_MESHMAMBA_ROOT")
    else:
        path = _env_path(
            "MESHMAMBA_RGB_TEXTURE_ROOT",
            "REPROJECT_DATASET_MESHMAMBA_RGB_TEXTURE_ROOT",
            "MESHMAMBA_NON_TEXTURE_ROOT",
            "REPROJECT_DATASET_MESHMAMBA_ROOT",
        )
    if path is None:
        raise RuntimeError(f"Dataset root not configured for {texture_type}.")
    return path


def resolve_csv_root(texture_type: str) -> Path:
    side_inputs_root = os.environ.get("SIDE_INPUTS_ROOT")
    if texture_type == "non_texture":
        path = _env_path(
            "MESHMAMBA_CSV_ROOT",
            "REPROJECT_GAZE_CSV_MESHMAMBA_NON_TEXTURE_ROOT",
            fallback=f"{side_inputs_root}/MeshMamba_non_texture/csv" if side_inputs_root else None,
        )
    else:
        path = _env_path(
            "MESHMAMBA_RGB_TEXTURE_CSV_ROOT",
            "REPROJECT_GAZE_CSV_MESHMAMBA_RGB_TEXTURE_ROOT",
            fallback=f"{side_inputs_root}/MeshMamba_rgb_texture/csv" if side_inputs_root else None,
        )
    if path is None:
        raise RuntimeError(f"CSV root not configured for {texture_type}.")
    return path


def resolve_json_root(texture_type: str) -> Path:
    side_inputs_root = os.environ.get("SIDE_INPUTS_ROOT")
    if texture_type == "non_texture":
        path = _env_path(
            "MESHMAMBA_JSON_ROOT",
            "REPROJECT_GAZE_JSON_MESHMAMBA_NON_TEXTURE_ROOT",
            fallback=str(REPO_ROOT / "jsons" / "mamba_non_jsons"),
        )
    else:
        path = _env_path(
            "MESHMAMBA_RGB_TEXTURE_JSON_ROOT",
            "REPROJECT_GAZE_JSON_MESHMAMBA_RGB_TEXTURE_ROOT",
            fallback=str(REPO_ROOT / "jsons" / "mamba_rgb_jsons"),
        )
    if path is not None and not path.exists() and side_inputs_root:
        path = Path(f"{side_inputs_root}/MeshMamba_{texture_type}/json")
    if path is None:
        raise RuntimeError(f"JSON root not configured for {texture_type}.")
    return path


def load_explicit_models(args: argparse.Namespace) -> list[str] | None:
    models: list[str] = []
    if args.models:
        models.extend(args.models)
    if args.model_list_file:
        models.extend(
            line.strip()
            for line in args.model_list_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
    if not models:
        return None
    deduped: list[str] = []
    seen: set[str] = set()
    for model in models:
        if model not in seen:
            deduped.append(model)
            seen.add(model)
    return deduped


def is_meshmamba_duplicate_dir(model_dir_name: str, csv_root: Path, json_root: Path, gt_root: Path, mesh_root: Path) -> bool:
    match = re.fullmatch(r"(.+)\s+2", model_dir_name)
    if not match:
        return False
    canonical = match.group(1)
    if not (mesh_root / canonical).is_dir():
        return False
    has_exact_csv = (csv_root / f"{model_dir_name}.csv").exists()
    has_exact_json = (json_root / f"MeshMamba_rgb_texture_{model_dir_name}.json").exists() or (json_root / f"MeshMamba_non_texture_{model_dir_name}.json").exists()
    has_exact_gt = (gt_root / f"{model_dir_name}.csv").exists()
    return not (has_exact_csv or has_exact_json or has_exact_gt)


def inventory_models(texture_type: str, explicit_models: list[str] | None) -> list[str]:
    if explicit_models is not None:
        return list(explicit_models)

    dataset_root = resolve_dataset_root(texture_type)
    mesh_root = dataset_root / "MeshFile" / texture_type
    gt_root = dataset_root / "SaliencyMap" / texture_type
    csv_root = resolve_csv_root(texture_type)
    json_root = resolve_json_root(texture_type)

    models: list[str] = []
    for path in sorted(mesh_root.iterdir()):
        if not path.is_dir():
            continue
        if is_meshmamba_duplicate_dir(path.name, csv_root, json_root, gt_root, mesh_root):
            continue
        models.append(path.name)
    return models


def task_output_dir(batch_output_dir: Path, texture_type: str, method: str) -> Path:
    return batch_output_dir / texture_type / f"baseline_{method}"


def task_log_path(batch_output_dir: Path, texture_type: str, method: str, model: str) -> Path:
    return batch_output_dir / "_logs" / texture_type / method / f"{model}.log"


def report_path_for_task(batch_output_dir: Path, task: Task) -> Path:
    tag = SCREEN_TAG if task.method == "screen_space" else CONE_TAG
    return task_output_dir(batch_output_dir, task.texture_type, task.method) / task.model / tag / f"{task.model}_report.json"


def build_command(args: argparse.Namespace, task: Task) -> list[str]:
    dataset_root = resolve_dataset_root(task.texture_type)
    csv_root = resolve_csv_root(task.texture_type)
    json_root = resolve_json_root(task.texture_type)
    output_dir = task_output_dir(args.batch_output_dir, task.texture_type, task.method)

    if task.method == "screen_space":
        return [
            str(args.python_bin),
            str(SCREEN_SCRIPT),
            "--model", task.model,
            "--texture-type", task.texture_type,
            "--dataset-root", str(dataset_root),
            "--csv-root", str(csv_root),
            "--json-root", str(json_root),
            "--output-dir", str(output_dir),
            "--sigma-screen", "0.05",
            "--recenter-to-bbox-center",
            "--extra-rotate-x-deg", "90",
            "--projection-fov-mode", "horizontal_to_vertical",
            "--transform-order", "blender_rig",
            "--tag", SCREEN_TAG,
        ]

    return [
        str(args.python_bin),
        str(CONE_SCRIPT),
        "--model", task.model,
        "--texture-type", task.texture_type,
        "--dataset-root", str(dataset_root),
        "--csv-root", str(csv_root),
        "--json-root", str(json_root),
        "--output-dir", str(output_dir),
        "--sigma-deg", "1.0",
        "--radius-sigma-mult", "3.0",
        "--recenter-to-bbox-center",
        "--extra-rotate-x-deg", "90",
        "--projection-fov-mode", "horizontal_to_vertical",
        "--transform-order", "blender_rig",
        "--tag", CONE_TAG,
    ]


def classify_error(message: str) -> tuple[str, str]:
    msg = message.lower()
    if "gt file not found" in msg:
        return "missing_gt", message.strip()
    if "json file" in msg and "not found" in msg:
        return "missing_json", message.strip()
    if "csv" in msg and "not found" in msg:
        return "missing_csv", message.strip()
    if "model directory not found" in msg or "obj" in msg and "not found" in msg:
        return "missing_obj", message.strip()
    return "runtime_error", message.strip()


def preflight_status(task: Task) -> tuple[str, str]:
    dataset_root = resolve_dataset_root(task.texture_type)
    mesh_root = dataset_root / "MeshFile" / task.texture_type
    csv_root = resolve_csv_root(task.texture_type)
    json_root = resolve_json_root(task.texture_type)

    if not (mesh_root / task.model).is_dir():
        return "missing_obj", f"model dir not found: {(mesh_root / task.model)}"
    if not (csv_root / f"{task.model}.csv").exists():
        return "missing_csv", f"csv not found: {(csv_root / f'{task.model}.csv')}"
    json_name = f"MeshMamba_{task.texture_type}_{task.model}.json"
    if not (json_root / json_name).exists():
        return "missing_json", f"json not found: {(json_root / json_name)}"
    return "", ""


def run_task(args: argparse.Namespace, task: Task) -> dict[str, Any]:
    report_path = report_path_for_task(args.batch_output_dir, task)
    log_path = task_log_path(args.batch_output_dir, task.texture_type, task.method, task.model)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    if args.resume and report_path.exists():
        return collect_row_from_report(task, report_path, status="ok", stdout_log_path=log_path)

    preflight_error, preflight_message = preflight_status(task)
    if preflight_error:
        return base_row(task, status=preflight_error, error_type=preflight_error, error_message=preflight_message, stdout_log_path=log_path, report_path=report_path)

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
        f"$ {' '.join(shlex.quote(part) for part in cmd)}\n\n"
        f"[exit_code] {proc.returncode}\n"
        f"[elapsed_sec] {elapsed:.2f}\n\n"
        f"{proc.stdout}",
        encoding="utf-8",
    )

    if proc.returncode != 0:
        error_type, message = classify_error(proc.stdout)
        return base_row(task, status=error_type, error_type=error_type, error_message=message, stdout_log_path=log_path, report_path=report_path)
    if not report_path.exists():
        return base_row(task, status="runtime_error", error_type="runtime_error", error_message="report json missing after successful exit", stdout_log_path=log_path, report_path=report_path)

    return collect_row_from_report(task, report_path, status="ok", stdout_log_path=log_path)


def base_row(
    task: Task,
    *,
    status: str,
    error_type: str = "",
    error_message: str = "",
    stdout_log_path: Path | None = None,
    report_path: Path | None = None,
) -> dict[str, Any]:
    row = {key: "" for key in LONG_BASE_COLUMNS}
    row.update(
        {
            "texture_type": task.texture_type,
            "model": task.model,
            "method": task.method,
            "status": status,
            "error_type": error_type,
            "error_message": error_message,
            "report_path": str(report_path) if report_path else "",
            "stdout_log_path": str(stdout_log_path) if stdout_log_path else "",
        }
    )
    return row


def collect_row_from_report(task: Task, report_path: Path, *, status: str, stdout_log_path: Path | None) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    row = base_row(task, status=status, stdout_log_path=stdout_log_path, report_path=report_path)

    row["gt_file"] = report.get("gt_file", "")
    row["n_faces"] = report.get("n_faces", "")

    gaze_stats = report.get("gaze_stats", {})
    row["num_rows"] = gaze_stats.get("num_rows", "")
    row["num_participants"] = gaze_stats.get("num_participants", "")
    row["num_points"] = gaze_stats.get("num_points", "")
    row["num_frames_with_points"] = gaze_stats.get("num_frames_with_points", "")

    run_stats = report.get("run_stats", {})
    proj = run_stats.get("projection", {})
    row["projection_fov_mode"] = proj.get("projection_fov_mode", "")
    row["projection_fov_source"] = proj.get("projection_fov_source", "")
    row["input_fov_deg"] = proj.get("input_fov_deg", "")
    row["effective_vertical_fov_deg"] = proj.get("effective_vertical_fov_deg", "")

    if task.method == "screen_space":
        metrics = report.get("metrics_vs_gt", {}).get("screen_space_gaussian", {})
        row["nonzero_faces"] = run_stats.get("nonzero_faces", "")
        row["culled_back_faces"] = run_stats.get("culled_back_faces", "")
    else:
        metrics = report.get("metrics_vs_gt", {}).get("cone_gaussian_on_mesh", {})
        row["hit_rate"] = run_stats.get("hit_rate", "")
        row["successful_hits"] = run_stats.get("successful_hits", "")
        row["total_gaze_points"] = run_stats.get("total_gaze_points", "")
        row["cone_nonzero_faces"] = run_stats.get("cone_nonzero_faces", "")

    for key in (
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
    ):
        row[key] = metrics.get(key, "")
    return row


def write_long_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LONG_BASE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def write_wide_csv(rows: list[dict[str, Any]], path: Path) -> None:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    metric_fields = [field for field in LONG_BASE_COLUMNS if field not in {"texture_type", "model", "method"}]

    for row in rows:
        key = (row["texture_type"], row["model"])
        target = grouped.setdefault(
            key,
            {"texture_type": row["texture_type"], "model": row["model"]},
        )
        prefix = row["method"]
        for field in metric_fields:
            target[f"{prefix}_{field}"] = row.get(field, "")

    fieldnames = ["texture_type", "model"]
    for method in METHODS:
        for field in metric_fields:
            fieldnames.append(f"{method}_{field}")

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for key in sorted(grouped):
            writer.writerow(grouped[key])


def write_summary_csv(rows: list[dict[str, Any]], path: Path) -> None:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((row["texture_type"], row["method"]), []).append(row)

    fieldnames = [
        "texture_type",
        "method",
        "n_total",
        "n_ok",
        "n_failed",
    ]
    for metric in SUMMARY_METRICS:
        fieldnames.extend([f"{metric}_mean", f"{metric}_median"])

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for key in sorted(groups):
            texture_type, method = key
            group_rows = groups[key]
            ok_rows = [row for row in group_rows if row["status"] == "ok"]
            summary: dict[str, Any] = {
                "texture_type": texture_type,
                "method": method,
                "n_total": len(group_rows),
                "n_ok": len(ok_rows),
                "n_failed": len(group_rows) - len(ok_rows),
            }
            for metric in SUMMARY_METRICS:
                values = [float(row[metric]) for row in ok_rows if row.get(metric) not in ("", None)]
                summary[f"{metric}_mean"] = mean(values) if values else ""
                summary[f"{metric}_median"] = median(values) if values else ""
            writer.writerow(summary)


def main() -> int:
    args = parse_args()
    args.batch_output_dir.mkdir(parents=True, exist_ok=True)
    explicit_models = load_explicit_models(args)

    tasks: list[Task] = []
    for texture_type in args.texture_types:
        models = inventory_models(texture_type, explicit_models)
        for method in args.methods:
            tasks.extend(Task(texture_type=texture_type, method=method, model=model) for model in models)

    print(f"[run_meshmamba_reference_batch] tasks={len(tasks)} workers={args.workers}")
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(run_task, args, task): task for task in tasks}
        for future in as_completed(futures):
            task = futures[future]
            row = future.result()
            rows.append(row)
            print(f"[done] {task.texture_type} {task.method} {task.model} -> {row['status']}")

    rows.sort(key=lambda row: (row["texture_type"], row["model"], row["method"]))

    long_csv = args.batch_output_dir / "meshmamba_reference_long.csv"
    wide_csv = args.batch_output_dir / "meshmamba_reference_wide.csv"
    summary_csv = args.batch_output_dir / "meshmamba_reference_summary.csv"

    write_long_csv(rows, long_csv)
    write_wide_csv(rows, wide_csv)
    write_summary_csv(rows, summary_csv)

    print(f"[run_meshmamba_reference_batch] long_csv={long_csv}")
    print(f"[run_meshmamba_reference_batch] wide_csv={wide_csv}")
    print(f"[run_meshmamba_reference_batch] summary_csv={summary_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
