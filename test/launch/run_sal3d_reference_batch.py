#!/usr/bin/env python3
"""
Parallel batch runner for SAL3D reference methods.

Methods:
- screen_space_gaussian
- cone_gaussian_on_mesh

Reads GT from metrics_vs_gt_covered_only section (always valid for all SAL3D models).
Includes SAL3D-specific columns: gt_match_type, n_gt_covered, gt_coverage_pct, gt_smoothed.

Usage example (local):
  source test/env/local_paths.example.sh
  python3 test/launch/run_sal3d_reference_batch.py \\
      --methods screen_space cone \\
      --workers 4 \\
      --smooth-gaze-dir "/path/to/SAL3D_final/Smooth Gaze"

Usage example (vg-intellect):
  source configs/server_vg_intellect.env
  "$REPROJECT_PYTHON" test/launch/run_sal3d_reference_batch.py \\
      --methods screen_space cone \\
      --workers 4 \\
      --smooth-gaze-dir "$SAL3D_SMOOTH_GAZE_DIR" \\
      --batch-output-dir "$OUTPUT_ROOT/SAL3D_reference_batch"
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
SCREEN_SCRIPT = REPO_ROOT / "reprojection_methods" / "screen_space_gaussian" / "eval_sal3d_screen_space.py"
CONE_SCRIPT   = REPO_ROOT / "reprojection_methods" / "cone_projection_on_mesh" / "eval_sal3d_cone.py"

METHODS = ("screen_space", "cone")

SCREEN_TAG = "sigmapx26p3_recenter_rotx90p0_horizontaltovertical_blender_rig"
CONE_TAG   = "recenter_rotx90p0_horizontaltovertical_blender_rig"

LONG_BASE_COLUMNS = [
    "model",
    "method",
    "status",
    "error_type",
    "error_message",
    "report_path",
    "stdout_log_path",
    "gt_file",
    "gt_match_type",
    "gt_domain",
    "fixed_gt_file",
    "n_vertices",
    "n_gt_covered",
    "gt_coverage_pct",
    "gt_smoothed",
    "num_rows",
    "num_participants",
    "num_points",
    "num_frames_with_points",
    "projection_fov_mode",
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
    "nonzero_verts_or_faces",
    "culled_back",
    "hit_rate",
    "successful_hits",
    "total_gaze_points",
]

SUMMARY_METRICS = [
    "CC",
    "SIM",
    "KLD",
    "MSE",
    "MAE",
    "Spearman",
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
        value = os.environ.get(key)
        if value:
            return Path(value)
    return Path(fallback) if fallback is not None else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parallel SAL3D reference batch runner.")
    parser.add_argument(
        "--methods",
        nargs="+",
        choices=METHODS,
        default=list(METHODS),
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--batch-output-dir",
        type=Path,
        default=_env_path("SAL3D_BATCH_OUTPUT_DIR", "REPROJECT_OUTPUT_ROOT",
                          fallback=str(REPO_ROOT / "results")) / "SAL3D_reference_batch",
    )
    parser.add_argument(
        "--models",
        nargs="*",
        default=None,
        help="Optional explicit model subset.",
    )
    parser.add_argument(
        "--model-list-file",
        type=Path,
        default=None,
        help="Text file with one model name per line.",
    )
    parser.add_argument(
        "--smooth-gaze-dir",
        type=Path,
        default=_env_path("SAL3D_SMOOTH_GAZE_DIR", "REPROJECT_SAL3D_SMOOTH_GAZE_ROOT"),
        help="Directory with <model>_neighbors.txt for GT smoothing.",
    )
    parser.add_argument(
        "--fixed-gt-dir",
        type=Path,
        default=_env_path("SAL3D_FIXED_GT_DIR"),
        help="Directory with <model>_faces.txt per-face fixed GT files.",
    )
    parser.add_argument(
        "--sal3d-manifest",
        type=Path,
        default=None,
        help="Path to sal3d_manifest.csv (optional, recorded in provenance).",
    )
    parser.add_argument(
        "--smooth-ratio",
        type=int,
        default=500,
    )
    parser.add_argument(
        "--csv-compat",
        action="store_true",
        default=False,
        help="Use legacy CSV input. Reports will show input_mode=csv_compat.",
    )
    parser.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip tasks with an existing report JSON whose participant contract matches.",
    )
    parser.add_argument("--nice-level", type=int, default=10)
    parser.add_argument(
        "--python-bin",
        type=Path,
        default=Path(os.environ.get("REPROJECT_PYTHON", sys.executable)),
    )
    return parser.parse_args()


def resolve_dataset_root() -> Path:
    path = _env_path("SAL3D_DATASET_ROOT", "REPROJECT_DATASET_SAL3D_ROOT")
    if path is None:
        raise RuntimeError("Dataset root not configured. Set SAL3D_DATASET_ROOT.")
    return path


def resolve_csv_root() -> Path:
    path = _env_path(
        "SAL3D_CSV_ROOT",
        "REPROJECT_GAZE_CSV_SAL3D_ROOT",
        fallback=os.environ.get("SIDE_INPUTS_ROOT", "") + "/SAL3D/csv" if os.environ.get("SIDE_INPUTS_ROOT") else None,
    )
    if path is None:
        raise RuntimeError("CSV root not configured. Set SAL3D_CSV_ROOT.")
    return path


def resolve_fixation_root() -> Path:
    path = _env_path(
        "FIXATION_ROOT", "REPROJECT_PROCESSED_FIXATIONS_ROOT",
        "SAL3D_PROCESSED_FIXATIONS_ROOT",
    )
    if path is None:
        raise RuntimeError(
            "Fixation root not configured. Set FIXATION_ROOT, "
            "REPROJECT_PROCESSED_FIXATIONS_ROOT, or SAL3D_PROCESSED_FIXATIONS_ROOT."
        )
    return path


def resolve_json_root() -> Path:
    path = _env_path(
        "SAL3D_JSON_ROOT",
        "REPROJECT_GAZE_JSON_SAL3D_ROOT",
        fallback=str(REPO_ROOT / "jsons" / "object_placement" / "sal3d_jsons"),
    )
    if path is not None and not path.exists() and os.environ.get("SIDE_INPUTS_ROOT"):
        path = Path(os.environ["SIDE_INPUTS_ROOT"]) / "SAL3D" / "json"
    if path is None:
        raise RuntimeError("JSON root not configured. Set SAL3D_JSON_ROOT.")
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
    for m in models:
        if m not in seen:
            deduped.append(m)
            seen.add(m)
    return deduped


def _read_manifest_model_names(manifest_path: Path) -> list[str]:
    """Read model names from the first 'model' column of sal3d_manifest.csv."""
    with manifest_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader, None)
        if header is None:
            return []
        try:
            model_col = [h.strip().lower() for h in header].index("model")
        except ValueError:
            raise RuntimeError(
                f"sal3d_manifest.csv has no 'model' column. Headers: {header}"
            )
        return [
            row[model_col].strip()
            for row in reader
            if len(row) > model_col and row[model_col].strip()
        ]


def inventory_models(
    explicit_models: list[str] | None,
    *,
    csv_compat: bool = False,
    fixed_gt_dir: Path | None = None,
    sal3d_manifest: Path | None = None,
) -> list[str]:
    """Build model list from available GT and participant gaze data.

    Fixed-GT mode (--fixed-gt-dir provided):
      GT source: sal3d_manifest.csv (if --sal3d-manifest given) or *_faces.txt files.
      Intersected with: Meshes/*.obj and participant fixation JSONs.
      Does NOT require dataset_root/Gaze/.

    Classic mode (--fixed-gt-dir not provided):
      GT source: dataset_root/Gaze/*.txt.
      Intersected with: participant fixation JSONs.
    """
    if explicit_models is not None:
        return list(explicit_models)

    if fixed_gt_dir and fixed_gt_dir.is_dir():
        # --- fixed-GT mode ---
        if sal3d_manifest and sal3d_manifest.exists():
            raw_names = _read_manifest_model_names(sal3d_manifest)
        else:
            raw_names = [
                p.stem[: -len("_faces")]
                for p in sorted(fixed_gt_dir.glob("*_faces.txt"))
            ]
        gt_stems: dict[str, str] = {}
        for name in raw_names:
            if name.lower() not in gt_stems:
                gt_stems[name.lower()] = name

        # Intersect with available Meshes/*.obj
        try:
            dataset_root = resolve_dataset_root()
            mesh_dir = dataset_root / "Meshes"
            if mesh_dir.is_dir():
                obj_set = {p.stem.lower() for p in sorted(mesh_dir.glob("*.obj"))}
                gt_stems = {k: v for k, v in gt_stems.items() if k in obj_set}
        except RuntimeError:
            pass  # no dataset_root configured; skip OBJ filter

        # Intersect with participant gaze source
        if csv_compat:
            csv_root = resolve_csv_root()
            gaze_set = {p.stem.lower() for p in sorted(csv_root.glob("*.csv"))}
        else:
            fixation_root = resolve_fixation_root()
            gaze_set = {
                p.parent.name[len("SAL3D_"):].lower()
                for p in sorted(fixation_root.glob("SAL3D_*/fixations.json"))
            }

        return [name for key, name in sorted(gt_stems.items()) if key in gaze_set]

    else:
        # --- classic mode: discover from Gaze/*.txt ---
        dataset_root = resolve_dataset_root()
        gaze_dir = dataset_root / "Gaze"
        if not gaze_dir.is_dir():
            raise RuntimeError(f"Gaze directory not found: {gaze_dir}")

        gt_stems = {p.stem.lower(): p.stem for p in sorted(gaze_dir.glob("*.txt"))}

        if csv_compat:
            csv_root = resolve_csv_root()
            gaze_set = {p.stem.lower() for p in sorted(csv_root.glob("*.csv"))}
        else:
            fixation_root = resolve_fixation_root()
            gaze_set = {
                p.parent.name[len("SAL3D_"):].lower()
                for p in sorted(fixation_root.glob("SAL3D_*/fixations.json"))
            }

        return [name for key, name in sorted(gt_stems.items()) if key in gaze_set]


def task_output_dir(batch_output_dir: Path, method: str) -> Path:
    return batch_output_dir / f"baseline_{method}"


def task_log_path(batch_output_dir: Path, method: str, model: str) -> Path:
    return batch_output_dir / "_logs" / method / f"{model}.log"


def report_path_for_task(batch_output_dir: Path, task: Task) -> Path:
    tag = SCREEN_TAG if task.method == "screen_space" else CONE_TAG
    out_dir = task_output_dir(batch_output_dir, task.method)
    return out_dir / task.model / tag / f"{task.model}_report.json"


def build_command(args: argparse.Namespace, task: Task) -> list[str]:
    dataset_root = resolve_dataset_root()
    json_root    = resolve_json_root()
    output_dir   = task_output_dir(args.batch_output_dir, task.method)

    gaze_args: list[str] = []
    if args.csv_compat:
        gaze_args = ["--csv-compat", "--csv-root", str(resolve_csv_root())]
    else:
        gaze_args = ["--fixation-root", str(resolve_fixation_root())]

    common = [
        "--model",       task.model,
        "--dataset-root", str(dataset_root),
        "--json-root",   str(json_root),
        "--output-dir",  str(output_dir),
        *gaze_args,
        "--recenter-to-bbox-center",
        "--extra-rotate-x-deg", "90",
        "--projection-fov-mode", "horizontal_to_vertical",
        "--transform-order", "blender_rig",
        "--smooth-ratio", str(args.smooth_ratio),
    ]

    smooth_args: list[str] = []
    if args.smooth_gaze_dir and Path(str(args.smooth_gaze_dir)).is_dir():
        smooth_args = ["--smooth-gaze-dir", str(args.smooth_gaze_dir)]

    fixed_gt_args: list[str] = []
    fixed_gt_dir = getattr(args, "fixed_gt_dir", None)
    if fixed_gt_dir and fixed_gt_dir.is_dir():
        fixed_gt_args = ["--fixed-gt-dir", str(fixed_gt_dir)]
        sal3d_manifest = getattr(args, "sal3d_manifest", None)
        if sal3d_manifest:
            fixed_gt_args += ["--sal3d-manifest", str(sal3d_manifest)]

    if task.method == "screen_space":
        cmd = [str(args.python_bin), str(SCREEN_SCRIPT)]
        cmd += common
        cmd += ["--sigma-px", "26.3", "--tag", SCREEN_TAG]
        cmd += smooth_args
        cmd += fixed_gt_args
    else:
        cmd = [str(args.python_bin), str(CONE_SCRIPT)]
        cmd += common
        cmd += ["--sigma-deg", "1.0", "--radius-sigma-mult", "3.0", "--tag", CONE_TAG]
        cmd += smooth_args
        cmd += fixed_gt_args

    return cmd


def classify_error(message: str) -> tuple[str, str]:
    msg = message.lower()
    if "gt" in msg and "not found" in msg:
        return "missing_gt", message.strip()
    if "json" in msg and "not found" in msg:
        return "missing_json", message.strip()
    if "csv" in msg and "not found" in msg:
        return "missing_csv", message.strip()
    if "obj" in msg and "not found" in msg:
        return "missing_obj", message.strip()
    return "runtime_error", message.strip()


def preflight_status(
    task: Task,
    *,
    csv_compat: bool = False,
    fixed_gt_dir: Path | None = None,
) -> tuple[str, str]:
    try:
        dataset_root = resolve_dataset_root()
        json_root    = resolve_json_root()
    except RuntimeError as exc:
        return "config_error", str(exc)

    gaze_dir = dataset_root / "Gaze"
    mesh_dir = dataset_root / "Meshes"
    model_lc = task.model.lower()

    if fixed_gt_dir and fixed_gt_dir.is_dir():
        if not any(
            p.stem.lower() == f"{model_lc}_faces"
            for p in fixed_gt_dir.glob("*_faces.txt")
        ):
            return "missing_gt", (
                f"Fixed face GT not found for '{task.model}' in {fixed_gt_dir}"
            )
    else:
        if not any(p.stem.lower() == model_lc for p in gaze_dir.glob("*.txt")):
            return "missing_gt", f"Gaze GT not found for '{task.model}' in {gaze_dir}"
    if not any(p.stem.lower() == model_lc for p in mesh_dir.glob("*.obj")):
        return "missing_obj", f"OBJ not found for '{task.model}' in {mesh_dir}"
    if csv_compat:
        try:
            csv_root = resolve_csv_root()
        except RuntimeError as exc:
            return "config_error", str(exc)
        if not any(p.stem.lower() == model_lc for p in csv_root.glob("*.csv")):
            return "missing_csv", f"CSV not found for '{task.model}' in {csv_root}"
    else:
        try:
            fixation_path = resolve_fixation_root() / f"SAL3D_{task.model}" / "fixations.json"
        except RuntimeError as exc:
            return "config_error", str(exc)
        if not fixation_path.exists():
            return "missing_fixation", f"fixation JSON not found: {fixation_path}"
    json_prefix = f"sal3d_{model_lc}"
    if not any(p.stem.lower() == json_prefix for p in json_root.glob("*.json")):
        return "missing_json", f"JSON not found for '{task.model}' (prefix Sal3D_) in {json_root}"

    return "", ""


def _provenance_matches(report_path: Path, args: argparse.Namespace) -> bool:
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

    if args.resume and report_path.exists() and _provenance_matches(report_path, args):
        return collect_row_from_report(task, report_path, status="ok", stdout_log_path=log_path)

    preflight_error, preflight_message = preflight_status(
        task,
        csv_compat=args.csv_compat,
        fixed_gt_dir=getattr(args, "fixed_gt_dir", None),
    )
    if preflight_error:
        return base_row(task, status=preflight_error, error_type=preflight_error,
                        error_message=preflight_message, stdout_log_path=log_path, report_path=report_path)

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
    if not report_path.exists():
        return base_row(task, status="runtime_error", error_type="runtime_error",
                        error_message="report json missing after successful exit",
                        stdout_log_path=log_path, report_path=report_path)

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
    row.update({
        "model":            task.model,
        "method":           task.method,
        "status":           status,
        "error_type":       error_type,
        "error_message":    error_message,
        "report_path":      str(report_path) if report_path else "",
        "stdout_log_path":  str(stdout_log_path) if stdout_log_path else "",
    })
    return row


def collect_row_from_report(
    task: Task, report_path: Path, *, status: str, stdout_log_path: Path | None
) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    row = base_row(task, status=status, stdout_log_path=stdout_log_path, report_path=report_path)

    row["gt_file"]        = report.get("gt_file", "")
    row["gt_match_type"]  = report.get("gt_match_type", "")
    row["n_vertices"]     = report.get("n_vertices", "")
    row["n_gt_covered"]   = report.get("n_gt_covered", "")
    row["gt_coverage_pct"] = report.get("gt_coverage_pct", "")
    row["gt_smoothed"]    = report.get("gt_smoothed", "")

    gaze_stats = report.get("gaze_stats", {})
    row["num_rows"]               = gaze_stats.get("num_rows", "")
    row["num_participants"]        = gaze_stats.get("num_participants", "")
    row["num_points"]              = gaze_stats.get("num_points", "")
    row["num_frames_with_points"]  = gaze_stats.get("num_frames_with_points", "")

    run_stats = report.get("run_stats", {})
    proj = run_stats.get("projection", {})
    row["projection_fov_mode"]       = proj.get("projection_fov_mode", "")
    row["input_fov_deg"]             = proj.get("input_fov_deg", "")
    row["effective_vertical_fov_deg"] = proj.get("effective_vertical_fov_deg", "")

    # Prefer fixed-face GT metrics when present; fall back to covered-only vertex metrics.
    fixed_section = report.get("metrics_vs_fixed_face_gt")
    if fixed_section:
        row["gt_match_type"] = "fixed_face"
        row["gt_domain"]     = fixed_section.get("gt_domain", "face")
        row["fixed_gt_file"] = (
            Path(fixed_section.get("gt_path", "")).name
            if fixed_section.get("gt_path") else ""
        )
        method_key = "screen_space_gaussian" if task.method == "screen_space" else "cone_gaussian_on_mesh"
        metrics = fixed_section.get(method_key) or {}
    else:
        row["gt_domain"]    = "vertex"
        row["fixed_gt_file"] = ""
        covered = report.get("metrics_vs_gt_covered_only") or {}
        if task.method == "screen_space":
            metrics = covered.get("screen_space_gaussian") or {}
        else:
            metrics = covered.get("cone_gaussian_on_mesh") or {}

    if task.method == "screen_space":
        row["nonzero_verts_or_faces"] = run_stats.get("nonzero_vertices", "")
        row["culled_back"]            = run_stats.get("culled_back_verts", "")
    else:
        row["hit_rate"]               = run_stats.get("hit_rate", "")
        row["successful_hits"]        = run_stats.get("successful_hits", "")
        row["total_gaze_points"]      = run_stats.get("total_gaze_points", "")
        row["nonzero_verts_or_faces"] = run_stats.get("cone_nonzero_vertices", "")

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
        writer = csv.DictWriter(f, fieldnames=LONG_BASE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def write_wide_csv(rows: list[dict[str, Any]], path: Path) -> None:
    grouped: dict[str, dict[str, Any]] = {}
    metric_fields = [field for field in LONG_BASE_COLUMNS if field not in {"model", "method"}]

    for row in rows:
        key = row["model"]
        target = grouped.setdefault(key, {"model": key})
        prefix = row["method"]
        for field in metric_fields:
            target[f"{prefix}_{field}"] = row.get(field, "")

    fieldnames = ["model"]
    for method in METHODS:
        for field in metric_fields:
            fieldnames.append(f"{method}_{field}")

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for key in sorted(grouped):
            writer.writerow(grouped[key])


def write_summary_csv(rows: list[dict[str, Any]], path: Path) -> None:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(row["method"], []).append(row)

    fieldnames = ["method", "n_total", "n_ok", "n_failed",
                  "n_direct", "n_subset", "n_fixed_face", "n_smoothed_gt"]
    for metric in SUMMARY_METRICS:
        fieldnames.extend([f"{metric}_mean", f"{metric}_median"])

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for method in sorted(groups):
            group_rows = groups[method]
            ok_rows  = [r for r in group_rows if r["status"] == "ok"]
            summary: dict[str, Any] = {
                "method":         method,
                "n_total":        len(group_rows),
                "n_ok":           len(ok_rows),
                "n_failed":       len(group_rows) - len(ok_rows),
                "n_direct":      sum(1 for r in ok_rows if r.get("gt_match_type") == "direct"),
                "n_subset":      sum(1 for r in ok_rows if r.get("gt_match_type") == "subset"),
                "n_fixed_face":  sum(1 for r in ok_rows if r.get("gt_match_type") == "fixed_face"),
                "n_smoothed_gt": sum(1 for r in ok_rows if str(r.get("gt_smoothed", "")).lower() == "true"),
            }
            for metric in SUMMARY_METRICS:
                values = [float(r[metric]) for r in ok_rows if r.get(metric) not in ("", None)]
                summary[f"{metric}_mean"]   = mean(values)   if values else ""
                summary[f"{metric}_median"] = median(values) if values else ""
            writer.writerow(summary)


def main() -> int:
    args = parse_args()
    args.batch_output_dir.mkdir(parents=True, exist_ok=True)
    explicit_models = load_explicit_models(args)

    models = inventory_models(
        explicit_models,
        csv_compat=args.csv_compat,
        fixed_gt_dir=getattr(args, "fixed_gt_dir", None),
        sal3d_manifest=getattr(args, "sal3d_manifest", None),
    )
    tasks: list[Task] = [
        Task(method=method, model=model)
        for method in args.methods
        for model in models
    ]

    smooth_status = (
        f"ENABLED ({args.smooth_gaze_dir})"
        if args.smooth_gaze_dir and Path(str(args.smooth_gaze_dir)).is_dir()
        else "DISABLED (no smooth-gaze-dir)"
    )
    print(f"[run_sal3d_reference_batch] tasks={len(tasks)}  workers={args.workers}  "
          f"models={len(models)}  smooth_gt={smooth_status}")

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(run_task, args, task): task for task in tasks}
        for future in as_completed(futures):
            task = futures[future]
            row  = future.result()
            rows.append(row)
            print(f"[done] {task.method} {task.model} -> {row['status']}")

    rows.sort(key=lambda r: (r["model"], r["method"]))

    long_csv    = args.batch_output_dir / "sal3d_reference_long.csv"
    wide_csv    = args.batch_output_dir / "sal3d_reference_wide.csv"
    summary_csv = args.batch_output_dir / "sal3d_reference_summary.csv"

    write_long_csv(rows, long_csv)
    write_wide_csv(rows, wide_csv)
    write_summary_csv(rows, summary_csv)

    print(f"[run_sal3d_reference_batch] long_csv={long_csv}")
    print(f"[run_sal3d_reference_batch] wide_csv={wide_csv}")
    print(f"[run_sal3d_reference_batch] summary_csv={summary_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
