#!/usr/bin/env python3
"""
Run a focused parameter sweep for KLD diagnostics.

The script orchestrates the existing single-model evaluators and does not
reimplement projection. It is intended for quick experiments that answer:
- does KLD drop when screen/cone smoothing is widened?
- is high KLD caused by GT mass on zero/near-zero predictions?

Default sweep:
- SAL3D: bunny, A380, dog, flowerpot, dragon
- MeshMamba non_texture: Pear_L3, Flying_saucer_v1_L3, MushroomShitake_L3,
  Domestic_cat_V2_L3, Starfruit_L3
- screen_space: several sigma values
- cone: sigma_deg x radius_sigma_mult grid

Outputs:
- kld_sweep_long.csv: one row per dataset/model/method/parameter set
- kld_sweep_summary.csv: aggregate rows per parameter set
- kld_sweep_best_by_model.csv: best KLD row per dataset/model/method
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

SAL3D_SCREEN_SCRIPT = REPO_ROOT / "reprojection_methods" / "screen_space_gaussian" / "eval_sal3d_screen_space.py"
SAL3D_CONE_SCRIPT = REPO_ROOT / "reprojection_methods" / "cone_projection_on_mesh" / "eval_sal3d_cone.py"
MESHMAMBA_SCREEN_SCRIPT = REPO_ROOT / "reprojection_methods" / "screen_space_gaussian" / "eval_meshmamba_screen_space.py"
MESHMAMBA_CONE_SCRIPT = REPO_ROOT / "reprojection_methods" / "cone_projection_on_mesh" / "eval_meshmamba_cone.py"

DEFAULT_SAL3D_MODELS = ["bunny", "A380", "dog", "flowerpot", "dragon"]
DEFAULT_MESHMAMBA_MODELS = [
    "Pear_L3",
    "Flying_saucer_v1_L3",
    "MushroomShitake_L3",
    "Domestic_cat_V2_L3",
    "Starfruit_L3",
]

METHOD_KEYS = {
    "screen_space": "screen_space_gaussian",
    "cone": "cone_gaussian_on_mesh",
}

METRIC_COLUMNS = [
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
    "gt_mass_on_pred_zero",
    "pred_mass_on_pred_zero",
    "pred_count_zero",
    "gt_mass_on_pred_le_1e_8",
    "pred_mass_on_pred_le_1e_8",
    "pred_count_le_1e_8",
    "gt_mass_on_pred_le_1e_6",
    "pred_mass_on_pred_le_1e_6",
    "pred_count_le_1e_6",
    "top100_kld_contrib_sum",
    "top100_kld_gt_mass",
    "top100_kld_pred_mass",
]

ROW_COLUMNS = [
    "dataset",
    "texture_type",
    "model",
    "method",
    "param_id",
    "screen_sigma_px",
    "screen_sigma_screen",
    "cone_sigma_deg",
    "cone_radius_sigma_mult",
    "status",
    "error_type",
    "error_message",
    "elapsed_sec",
    "report_path",
    "stdout_log_path",
    "gt_file",
    "gt_match_type",
    "n_vertices",
    "n_faces",
    "n_gt_covered",
    "gt_coverage_pct",
    "gt_smoothed",
    "num_points",
    "num_frames_with_points",
    "projection_fov_mode",
    "input_fov_deg",
    "effective_vertical_fov_deg",
    "nonzero_verts_or_faces",
    "culled_back",
    "hit_rate",
    "successful_hits",
    "total_gaze_points",
] + METRIC_COLUMNS

SUMMARY_METRICS = [
    "KLD",
    "CC",
    "SIM",
    "Spearman",
    "AUC_Judd_gt_top_10pct_proxy",
    "NSS_gt_top_10pct_proxy",
    "gt_mass_on_pred_zero",
    "gt_mass_on_pred_le_1e_8",
    "gt_mass_on_pred_le_1e_6",
    "top100_kld_gt_mass",
    "top100_kld_pred_mass",
    "hit_rate",
]


@dataclass(frozen=True)
class Task:
    dataset: str
    texture_type: str
    model: str
    method: str
    screen_sigma_px: float | None = None
    screen_sigma_screen: float | None = None
    cone_sigma_deg: float | None = None
    cone_radius_sigma_mult: float | None = None


def _env_path(*keys: str, fallback: str | None = None) -> Path | None:
    for key in keys:
        value = os.environ.get(key)
        if value:
            return Path(value)
    return Path(fallback) if fallback is not None else None


def _float_list(value: str) -> list[float]:
    return [float(part.strip()) for part in value.split(",") if part.strip()]


def _safe_float(value: Any) -> float | None:
    if value in ("", None):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt_num(value: float | None) -> str:
    if value is None:
        return "na"
    text = f"{value:g}".replace("-", "m").replace(".", "p")
    return text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run focused KLD parameter sweep.")
    parser.add_argument("--datasets", nargs="+", choices=["sal3d", "meshmamba"], default=["sal3d", "meshmamba"])
    parser.add_argument("--methods", nargs="+", choices=["screen_space", "cone"], default=["screen_space", "cone"])
    parser.add_argument("--texture-types", nargs="+", choices=["non_texture", "rgb_texture"], default=["non_texture"])
    parser.add_argument("--sal3d-models", nargs="*", default=DEFAULT_SAL3D_MODELS)
    parser.add_argument("--meshmamba-models", nargs="*", default=DEFAULT_MESHMAMBA_MODELS)
    parser.add_argument("--sal3d-screen-sigma-px", type=_float_list, default=_float_list("13.15,26.3,52.6,78.9"))
    parser.add_argument("--meshmamba-screen-sigma", type=_float_list, default=_float_list("0.025,0.05,0.075,0.1,0.15"))
    parser.add_argument("--cone-sigma-deg", type=_float_list, default=_float_list("1,2,3,5"))
    parser.add_argument("--cone-radius-sigma-mult", type=_float_list, default=_float_list("3,5,7"))
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--nice-level", type=int, default=10)
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--python-bin", type=Path, default=Path(os.environ.get("REPROJECT_PYTHON", sys.executable)))
    parser.add_argument(
        "--batch-output-dir",
        type=Path,
        default=_env_path("KLD_SWEEP_OUTPUT_DIR", "REPROJECT_OUTPUT_ROOT", fallback=str(REPO_ROOT / "results")) / "KLD_parameter_sweep",
    )
    parser.add_argument(
        "--smooth-gaze-dir",
        type=Path,
        default=_env_path("SAL3D_SMOOTH_GAZE_DIR", "REPROJECT_SAL3D_SMOOTH_GAZE_ROOT"),
    )
    parser.add_argument("--smooth-ratio", type=int, default=500)
    return parser.parse_args()


def resolve_sal3d_roots() -> tuple[Path, Path, Path]:
    dataset_root = _env_path("SAL3D_DATASET_ROOT", "REPROJECT_DATASET_SAL3D_ROOT")
    csv_root = _env_path("SAL3D_CSV_ROOT", "REPROJECT_GAZE_CSV_SAL3D_ROOT")
    json_root = _env_path("SAL3D_JSON_ROOT", "REPROJECT_GAZE_JSON_SAL3D_ROOT")
    if not (dataset_root and csv_root and json_root):
        raise RuntimeError("SAL3D roots are not configured: set SAL3D_DATASET_ROOT, SAL3D_CSV_ROOT, SAL3D_JSON_ROOT.")
    return dataset_root, csv_root, json_root


def resolve_meshmamba_roots(texture_type: str) -> tuple[Path, Path, Path]:
    side_inputs_root = os.environ.get("SIDE_INPUTS_ROOT")
    if texture_type == "non_texture":
        dataset_root = _env_path("MESHMAMBA_NON_TEXTURE_ROOT", "REPROJECT_DATASET_MESHMAMBA_ROOT")
        csv_root = _env_path(
            "MESHMAMBA_CSV_ROOT",
            "REPROJECT_GAZE_CSV_MESHMAMBA_NON_TEXTURE_ROOT",
            fallback=f"{side_inputs_root}/MeshMamba_non_texture/csv" if side_inputs_root else None,
        )
        json_root = _env_path(
            "MESHMAMBA_JSON_ROOT",
            "REPROJECT_GAZE_JSON_MESHMAMBA_NON_TEXTURE_ROOT",
            fallback=f"{side_inputs_root}/MeshMamba_non_texture/json" if side_inputs_root else None,
        )
    else:
        dataset_root = _env_path("MESHMAMBA_RGB_TEXTURE_ROOT", "REPROJECT_DATASET_MESHMAMBA_RGB_TEXTURE_ROOT")
        csv_root = _env_path(
            "MESHMAMBA_RGB_TEXTURE_CSV_ROOT",
            "REPROJECT_GAZE_CSV_MESHMAMBA_RGB_TEXTURE_ROOT",
            fallback=f"{side_inputs_root}/MeshMamba_rgb_texture/csv" if side_inputs_root else None,
        )
        json_root = _env_path(
            "MESHMAMBA_RGB_TEXTURE_JSON_ROOT",
            "REPROJECT_GAZE_JSON_MESHMAMBA_RGB_TEXTURE_ROOT",
            fallback=f"{side_inputs_root}/MeshMamba_rgb_texture/json" if side_inputs_root else None,
        )
    if not (dataset_root and csv_root and json_root):
        raise RuntimeError(f"MeshMamba roots are not configured for {texture_type}.")
    return dataset_root, csv_root, json_root


def make_tasks(args: argparse.Namespace) -> list[Task]:
    tasks: list[Task] = []
    if "sal3d" in args.datasets:
        if "screen_space" in args.methods:
            for model in args.sal3d_models:
                for sigma_px in args.sal3d_screen_sigma_px:
                    tasks.append(Task("sal3d", "", model, "screen_space", screen_sigma_px=sigma_px))
        if "cone" in args.methods:
            for model in args.sal3d_models:
                for sigma_deg in args.cone_sigma_deg:
                    for radius in args.cone_radius_sigma_mult:
                        tasks.append(Task("sal3d", "", model, "cone", cone_sigma_deg=sigma_deg, cone_radius_sigma_mult=radius))

    if "meshmamba" in args.datasets:
        for texture_type in args.texture_types:
            if "screen_space" in args.methods:
                for model in args.meshmamba_models:
                    for sigma_screen in args.meshmamba_screen_sigma:
                        tasks.append(Task("meshmamba", texture_type, model, "screen_space", screen_sigma_screen=sigma_screen))
            if "cone" in args.methods:
                for model in args.meshmamba_models:
                    for sigma_deg in args.cone_sigma_deg:
                        for radius in args.cone_radius_sigma_mult:
                            tasks.append(Task("meshmamba", texture_type, model, "cone", cone_sigma_deg=sigma_deg, cone_radius_sigma_mult=radius))
    return tasks


def param_id(task: Task) -> str:
    if task.method == "screen_space":
        if task.dataset == "sal3d":
            return f"screen_sigmapx{_fmt_num(task.screen_sigma_px)}"
        return f"screen_sigmascreen{_fmt_num(task.screen_sigma_screen)}"
    return f"cone_sigma{_fmt_num(task.cone_sigma_deg)}_radius{_fmt_num(task.cone_radius_sigma_mult)}"


def tag_for_task(task: Task) -> str:
    return f"sweep_{param_id(task)}_recenter_rotx90p0_horizontaltovertical_blender_rig"


def output_dir_for_task(args: argparse.Namespace, task: Task) -> Path:
    dataset_part = "SAL3D" if task.dataset == "sal3d" else f"MeshMamba_{task.texture_type}"
    return args.batch_output_dir / dataset_part / task.method / param_id(task)


def report_path_for_task(args: argparse.Namespace, task: Task) -> Path:
    return output_dir_for_task(args, task) / task.model / tag_for_task(task) / f"{task.model}_report.json"


def log_path_for_task(args: argparse.Namespace, task: Task) -> Path:
    dataset_part = "SAL3D" if task.dataset == "sal3d" else f"MeshMamba_{task.texture_type}"
    return args.batch_output_dir / "_logs" / dataset_part / task.method / param_id(task) / f"{task.model}.log"


def build_command(args: argparse.Namespace, task: Task) -> list[str]:
    output_dir = output_dir_for_task(args, task)
    tag = tag_for_task(task)
    if task.dataset == "sal3d":
        dataset_root, csv_root, json_root = resolve_sal3d_roots()
        common = [
            "--model", task.model,
            "--dataset-root", str(dataset_root),
            "--csv-root", str(csv_root),
            "--json-root", str(json_root),
            "--output-dir", str(output_dir),
            "--recenter-to-bbox-center",
            "--extra-rotate-x-deg", "90",
            "--projection-fov-mode", "horizontal_to_vertical",
            "--transform-order", "blender_rig",
            "--smooth-ratio", str(args.smooth_ratio),
            "--tag", tag,
        ]
        if args.smooth_gaze_dir and Path(str(args.smooth_gaze_dir)).is_dir():
            common.extend(["--smooth-gaze-dir", str(args.smooth_gaze_dir)])
        if task.method == "screen_space":
            return [str(args.python_bin), str(SAL3D_SCREEN_SCRIPT), *common, "--sigma-px", str(task.screen_sigma_px)]
        return [
            str(args.python_bin), str(SAL3D_CONE_SCRIPT), *common,
            "--sigma-deg", str(task.cone_sigma_deg),
            "--radius-sigma-mult", str(task.cone_radius_sigma_mult),
        ]

    dataset_root, csv_root, json_root = resolve_meshmamba_roots(task.texture_type)
    common = [
        "--model", task.model,
        "--texture-type", task.texture_type,
        "--dataset-root", str(dataset_root),
        "--csv-root", str(csv_root),
        "--json-root", str(json_root),
        "--output-dir", str(output_dir),
        "--recenter-to-bbox-center",
        "--extra-rotate-x-deg", "90",
        "--projection-fov-mode", "horizontal_to_vertical",
        "--transform-order", "blender_rig",
        "--tag", tag,
    ]
    if task.method == "screen_space":
        return [str(args.python_bin), str(MESHMAMBA_SCREEN_SCRIPT), *common, "--sigma-screen", str(task.screen_sigma_screen)]
    return [
        str(args.python_bin), str(MESHMAMBA_CONE_SCRIPT), *common,
        "--sigma-deg", str(task.cone_sigma_deg),
        "--radius-sigma-mult", str(task.cone_radius_sigma_mult),
    ]


def base_row(task: Task, args: argparse.Namespace, *, status: str, error_type: str = "", error_message: str = "", elapsed_sec: float | None = None) -> dict[str, Any]:
    row = {column: "" for column in ROW_COLUMNS}
    row.update(
        {
            "dataset": task.dataset,
            "texture_type": task.texture_type,
            "model": task.model,
            "method": task.method,
            "param_id": param_id(task),
            "screen_sigma_px": task.screen_sigma_px if task.screen_sigma_px is not None else "",
            "screen_sigma_screen": task.screen_sigma_screen if task.screen_sigma_screen is not None else "",
            "cone_sigma_deg": task.cone_sigma_deg if task.cone_sigma_deg is not None else "",
            "cone_radius_sigma_mult": task.cone_radius_sigma_mult if task.cone_radius_sigma_mult is not None else "",
            "status": status,
            "error_type": error_type,
            "error_message": error_message,
            "elapsed_sec": f"{elapsed_sec:.3f}" if elapsed_sec is not None else "",
            "report_path": str(report_path_for_task(args, task)),
            "stdout_log_path": str(log_path_for_task(args, task)),
        }
    )
    return row


def classify_error(output: str) -> tuple[str, str]:
    lower = output.lower()
    if "not found" in lower and "json" in lower:
        return "missing_json", output.strip()[-1000:]
    if "not found" in lower and "csv" in lower:
        return "missing_csv", output.strip()[-1000:]
    if "not found" in lower and ("obj" in lower or "model" in lower):
        return "missing_obj", output.strip()[-1000:]
    return "runtime_error", output.strip()[-1000:]


def collect_row(task: Task, args: argparse.Namespace, report_path: Path, elapsed_sec: float | None) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    row = base_row(task, args, status="ok", elapsed_sec=elapsed_sec)
    row["gt_file"] = report.get("gt_file", "")
    row["gt_match_type"] = report.get("gt_match_type", "")
    row["n_vertices"] = report.get("n_vertices", "")
    row["n_faces"] = report.get("n_faces", "")
    row["n_gt_covered"] = report.get("n_gt_covered", "")
    row["gt_coverage_pct"] = report.get("gt_coverage_pct", "")
    row["gt_smoothed"] = report.get("gt_smoothed", "")

    gaze_stats = report.get("gaze_stats", {})
    row["num_points"] = gaze_stats.get("num_points", "")
    row["num_frames_with_points"] = gaze_stats.get("num_frames_with_points", "")

    run_stats = report.get("run_stats", {})
    projection = run_stats.get("projection", {})
    row["projection_fov_mode"] = projection.get("projection_fov_mode", "")
    row["input_fov_deg"] = projection.get("input_fov_deg", "")
    row["effective_vertical_fov_deg"] = projection.get("effective_vertical_fov_deg", "")
    row["hit_rate"] = run_stats.get("hit_rate", "")
    row["successful_hits"] = run_stats.get("successful_hits", "")
    row["total_gaze_points"] = run_stats.get("total_gaze_points", "")

    if task.method == "screen_space":
        row["nonzero_verts_or_faces"] = run_stats.get("nonzero_vertices", run_stats.get("nonzero_faces", ""))
        row["culled_back"] = run_stats.get("culled_back_verts", run_stats.get("culled_back_faces", ""))
    else:
        row["nonzero_verts_or_faces"] = run_stats.get("cone_nonzero_vertices", run_stats.get("cone_nonzero_faces", ""))

    metric_root = report.get("metrics_vs_gt_covered_only") if task.dataset == "sal3d" else report.get("metrics_vs_gt")
    metrics = (metric_root or {}).get(METHOD_KEYS[task.method], {})
    for metric in METRIC_COLUMNS:
        row[metric] = metrics.get(metric, "")
    return row


def run_task(args: argparse.Namespace, task: Task) -> dict[str, Any]:
    report_path = report_path_for_task(args, task)
    log_path = log_path_for_task(args, task)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    output_dir_for_task(args, task).mkdir(parents=True, exist_ok=True)

    if args.resume and report_path.exists():
        return collect_row(task, args, report_path, elapsed_sec=None)

    cmd = build_command(args, task)
    if args.nice_level:
        cmd = ["nice", "-n", str(args.nice_level), *cmd]

    started = time.time()
    proc = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=os.environ.copy(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
    )
    elapsed = time.time() - started
    log_path.write_text(
        f"$ {' '.join(shlex.quote(part) for part in cmd)}\n\n"
        f"[exit_code] {proc.returncode}\n"
        f"[elapsed_sec] {elapsed:.3f}\n\n"
        f"{proc.stdout}",
        encoding="utf-8",
    )
    if proc.returncode != 0:
        error_type, message = classify_error(proc.stdout)
        return base_row(task, args, status=error_type, error_type=error_type, error_message=message, elapsed_sec=elapsed)
    if not report_path.exists():
        return base_row(task, args, status="runtime_error", error_type="runtime_error", error_message="report JSON missing", elapsed_sec=elapsed)
    return collect_row(task, args, report_path, elapsed_sec=elapsed)


def write_csv(rows: list[dict[str, Any]], path: Path, fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_summary(rows: list[dict[str, Any]], path: Path) -> None:
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((row["dataset"], row["texture_type"], row["method"], row["param_id"]), []).append(row)

    fieldnames = [
        "dataset",
        "texture_type",
        "method",
        "param_id",
        "n_total",
        "n_ok",
        "n_failed",
    ]
    for metric in SUMMARY_METRICS:
        fieldnames.extend([f"{metric}_mean", f"{metric}_median"])

    summary_rows: list[dict[str, Any]] = []
    for key in sorted(groups):
        dataset, texture_type, method, pid = key
        group_rows = groups[key]
        ok_rows = [row for row in group_rows if row["status"] == "ok"]
        out: dict[str, Any] = {
            "dataset": dataset,
            "texture_type": texture_type,
            "method": method,
            "param_id": pid,
            "n_total": len(group_rows),
            "n_ok": len(ok_rows),
            "n_failed": len(group_rows) - len(ok_rows),
        }
        for metric in SUMMARY_METRICS:
            values = [_safe_float(row.get(metric)) for row in ok_rows]
            values = [value for value in values if value is not None]
            out[f"{metric}_mean"] = mean(values) if values else ""
            out[f"{metric}_median"] = median(values) if values else ""
        summary_rows.append(out)
    write_csv(summary_rows, path, fieldnames)


def write_best(rows: list[dict[str, Any]], path: Path) -> None:
    best: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in rows:
        if row["status"] != "ok":
            continue
        kld = _safe_float(row.get("KLD"))
        if kld is None:
            continue
        key = (row["dataset"], row["texture_type"], row["model"], row["method"])
        prev = best.get(key)
        if prev is None or kld < float(prev["KLD"]):
            best[key] = row
    write_csv([best[key] for key in sorted(best)], path, ROW_COLUMNS)


def write_outputs(rows: list[dict[str, Any]], output_dir: Path) -> None:
    rows = sorted(rows, key=lambda row: (row["dataset"], row["texture_type"], row["model"], row["method"], row["param_id"]))
    write_csv(rows, output_dir / "kld_sweep_long.csv", ROW_COLUMNS)
    write_summary(rows, output_dir / "kld_sweep_summary.csv")
    write_best(rows, output_dir / "kld_sweep_best_by_model.csv")


def main() -> int:
    args = parse_args()
    args.batch_output_dir.mkdir(parents=True, exist_ok=True)
    tasks = make_tasks(args)
    print(f"[kld_sweep] tasks={len(tasks)} workers={args.workers} output={args.batch_output_dir}", flush=True)

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(run_task, args, task): task for task in tasks}
        for future in as_completed(futures):
            task = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                row = base_row(task, args, status="runtime_error", error_type="runtime_error", error_message=repr(exc))
            rows.append(row)
            print(
                f"[done] {task.dataset} {task.texture_type or '-'} {task.method} "
                f"{task.model} {param_id(task)} -> {row['status']}",
                flush=True,
            )
            write_outputs(rows, args.batch_output_dir)

    write_outputs(rows, args.batch_output_dir)
    print(f"[kld_sweep] long_csv={args.batch_output_dir / 'kld_sweep_long.csv'}", flush=True)
    print(f"[kld_sweep] summary_csv={args.batch_output_dir / 'kld_sweep_summary.csv'}", flush=True)
    print(f"[kld_sweep] best_csv={args.batch_output_dir / 'kld_sweep_best_by_model.csv'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
