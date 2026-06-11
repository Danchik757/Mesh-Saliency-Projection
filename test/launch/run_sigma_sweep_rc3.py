#!/usr/bin/env python3
"""
Sigma sweep runner — rc3 release.

Sweeps Gaussian blur parameters for screen_space_gaussian and cone_gaussian_on_mesh
with timing fixed at rc3 baseline (one_turn_from_start, delay=0.0, frame_offset=0).

Architecture
────────────
Same global pool + ThreadPoolExecutor design as run_ablation_window_delay.py.
Job identity key:
  "<dataset>:<model>:<method>:<sigma_tag>"
  where sigma_tag = "ss_s{sigma_screen}" or "cone_d{sigma_deg}_r{radius_sigma_mult}"

Sharding: deterministic MD5 hash of job key modulo num_shards.

Resume: loads completed keys from sigma_sweep_rows.jsonl on startup; skips them.

Screen-space sigma
──────────────────
Parameter swept: sigma_screen (fraction of image width).
  MeshMamba evaluator:   --sigma-screen <value>             (img 256px)
  3DVA/SAL3D evaluators: --sigma-px <sigma_screen × 1920>  (img 1920px)
Default grid: 0.010 0.014 0.020 0.025 0.035 0.050 0.065 0.080 0.100
  0.014 ≈ SAL3D current default (26.3 / 1920)
  0.025 ≈ 3DVA current default  (49.0 / 1920)
  0.050   MeshMamba current default

Cone sigma
──────────
Parameters swept: sigma_deg (angular degrees) × radius_sigma_mult (truncation radius).
Default grids:
  sigma_deg:          0.25 0.50 0.75 1.00 1.50 2.00 3.00
  radius_sigma_mult:  2.0  3.0  4.0
Full grid: 7 × 3 = 21 combinations.

Model selection
───────────────
30 models per dataset, stratified by screen_space CC from rc3 full metrics run.
Lists committed to: jsons/sigma_sweep_model_lists/{dataset}_30models.json
  3dva:                    30 of 31 valid (jessi excluded: missing_report in rc3)
  sal3d:                   30 of 54 valid (all have fixed-face GT in rc3)
  meshmamba_non_texture:   30 of 105 valid
  meshmamba_rgb_texture:   30 of 105 valid

Fixed timing (rc3)
──────────────────
  timing_contract:  one_turn_from_start
  delay_seconds:    0.0
  frame_offset:     0
  window_mode:      cut_tail
  fixation_data_tag: processed_fixations_offset0_full_cleaned

Output layout
─────────────
  <batch_output_dir>/
    sigma_sweep_rows.jsonl        — one JSON row per completed job (appended atomically)
    sigma_sweep_summary.csv       — aggregated at end of run (or --aggregate-only)
    per_task/<dataset>/<model>/<method>_<sigma_tag>/
      report.json
      stdout.log

Usage
─────
  # Dry-run (no evaluator calls):
  python3 test/launch/run_sigma_sweep_rc3.py --dry-run

  # Dry-run with job counts:
  python3 test/launch/run_sigma_sweep_rc3.py --dry-run --datasets 3dva --sigma-screen-values 0.025 0.050

  # Aggregate after run:
  python3 test/launch/run_sigma_sweep_rc3.py --aggregate-only \\
      --batch-output-dir outputs/sigma_sweep_rc3/shard_0_of_3

DO NOT RUN on servers without reviewer/controller approval.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

# ── image widths for sigma conversion ────────────────────────────────────────

_IMG_WIDTH: dict[str, int] = {
    "3dva":                  1920,
    "meshmamba_non_texture": 256,
    "meshmamba_rgb_texture": 256,
    "sal3d":                 1920,
}

# ── evaluator scripts ─────────────────────────────────────────────────────────

_SS = REPO_ROOT / "reprojection_methods" / "screen_space_gaussian"
_CN = REPO_ROOT / "reprojection_methods" / "cone_projection_on_mesh"

_EVAL: dict[str, dict[str, Path]] = {
    "3dva": {
        "screen_space": _SS / "eval_3dva_screen_space_combined.py",
        "cone":         _CN / "eval_3dva_cone_combined.py",
    },
    "meshmamba_non_texture": {
        "screen_space": _SS / "eval_meshmamba_screen_space.py",
        "cone":         _CN / "eval_meshmamba_cone.py",
    },
    "meshmamba_rgb_texture": {
        "screen_space": _SS / "eval_meshmamba_screen_space.py",
        "cone":         _CN / "eval_meshmamba_cone.py",
    },
    "sal3d": {
        "screen_space": _SS / "eval_sal3d_screen_space.py",
        "cone":         _CN / "eval_sal3d_cone.py",
    },
}

# ── default sigma grids ───────────────────────────────────────────────────────

DEFAULT_SIGMA_SCREEN = [0.010, 0.014, 0.020, 0.025, 0.035, 0.050, 0.065, 0.080, 0.100]
DEFAULT_SIGMA_DEG    = [0.25,  0.50,  0.75,  1.00,  1.50,  2.00,  3.00]
DEFAULT_RADIUS_MULT  = [2.0,   3.0,   4.0]

ALL_DATASETS = ["3dva", "meshmamba_non_texture", "meshmamba_rgb_texture", "sal3d"]
ALL_METHODS  = ["screen_space", "cone"]

# ── fixed rc3 timing ──────────────────────────────────────────────────────────

TIMING_CONTRACT  = "one_turn_from_start"
DELAY_SECONDS    = 0.0
FRAME_OFFSET     = 0
WINDOW_MODE      = "cut_tail"
RELEASE_TAG      = "v2.0-data-rc3"
FIXATION_DATA_TAG = "processed_fixations_offset0_full_cleaned"

# ── CSV output schema ─────────────────────────────────────────────────────────

CSV_COLUMNS = [
    "job_key",
    "dataset", "texture_type", "model", "method",
    "sigma_screen", "sigma_deg", "radius_sigma_mult",
    "timing_contract", "delay_seconds", "frame_offset",
    "fixation_data_tag", "release_tag", "repo_commit",
    "CC", "SIM", "KLD", "NSS", "AUC_Judd", "Spearman", "MSE",
    "gaze_start_frame", "placement_start_frame", "turn_frames_used",
    "report_path", "stdout_log_path",
    "status", "error_type", "error_message", "elapsed_sec",
]

# ── job identity ──────────────────────────────────────────────────────────────

@dataclass
class SigmaSweepJob:
    dataset: str
    model: str
    method: str
    sigma_screen: Optional[float] = None    # screen_space only
    sigma_deg: Optional[float] = None       # cone only
    radius_sigma_mult: Optional[float] = None  # cone only

    @property
    def texture_type(self) -> str:
        if self.dataset == "meshmamba_non_texture":
            return "non_texture"
        if self.dataset == "meshmamba_rgb_texture":
            return "rgb_texture"
        return ""

    @property
    def sigma_tag(self) -> str:
        if self.method == "screen_space":
            return f"ss_s{self.sigma_screen}".replace(".", "p")
        return (
            f"cone_d{self.sigma_deg}_r{self.radius_sigma_mult}"
            .replace(".", "p")
        )

    @property
    def key(self) -> str:
        return f"{self.dataset}:{self.model}:{self.method}:{self.sigma_tag}"

    def shard(self, num_shards: int) -> int:
        digest = hashlib.md5(self.key.encode()).hexdigest()
        return int(digest, 16) % num_shards


# ── model list loading ────────────────────────────────────────────────────────

_MODEL_LIST_DIR = REPO_ROOT / "jsons" / "sigma_sweep_model_lists"

_DATASET_LIST_FILE: dict[str, str] = {
    "3dva":                  "3dva_30models.json",
    "meshmamba_non_texture": "meshmamba_non_texture_30models.json",
    "meshmamba_rgb_texture": "meshmamba_rgb_texture_30models.json",
    "sal3d":                 "sal3d_30models.json",
}


def load_model_list(dataset: str, models_override: list[str] | None) -> list[str]:
    if models_override:
        return list(models_override)
    path = _MODEL_LIST_DIR / _DATASET_LIST_FILE[dataset]
    if not path.is_file():
        raise FileNotFoundError(
            f"Model list not found: {path}\n"
            f"Run: python3 test/launch/run_sigma_sweep_rc3.py --help"
        )
    data = json.loads(path.read_text())
    return [m["model"] for m in data["models"]]


# ── job list ──────────────────────────────────────────────────────────────────

def build_job_list(args: argparse.Namespace) -> list[SigmaSweepJob]:
    jobs: list[SigmaSweepJob] = []
    for dataset in args.datasets:
        models = load_model_list(dataset, args.models)
        for model in models:
            for method in args.methods:
                if method == "screen_space":
                    for sv in args.sigma_screen_values:
                        jobs.append(SigmaSweepJob(dataset, model, "screen_space", sigma_screen=sv))
                elif method == "cone":
                    for sd in args.sigma_deg_values:
                        for rm in args.radius_sigma_mult_values:
                            jobs.append(SigmaSweepJob(dataset, model, "cone",
                                                       sigma_deg=sd, radius_sigma_mult=rm))
    if args.num_shards > 1:
        jobs = [j for j in jobs if j.shard(args.num_shards) == args.shard_index]
    return jobs


# ── resume ────────────────────────────────────────────────────────────────────

def load_completed_keys(jsonl_path: Path) -> set[str]:
    if not jsonl_path.is_file():
        return set()
    keys: set[str] = set()
    with jsonl_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                if row.get("status") == "ok":
                    keys.add(row["job_key"])
            except (json.JSONDecodeError, KeyError):
                pass
    return keys


# ── command building ──────────────────────────────────────────────────────────

def _env_first(*keys: str) -> str:
    for k in keys:
        v = os.environ.get(k, "")
        if v:
            return v
    return ""


def _env_flags(cmd: list[str], mapping: dict[str, str]) -> None:
    for env_key, flag in mapping.items():
        val = os.environ.get(env_key, "")
        if val:
            cmd += [flag, val]


def build_command(job: SigmaSweepJob, args: argparse.Namespace) -> list[str]:
    script = _EVAL[job.dataset][job.method]
    python = os.environ.get("REPROJECT_PYTHON", sys.executable)

    cmd = [python, str(script), "--models", job.model]
    cmd += ["--timing-contract", TIMING_CONTRACT]
    cmd += ["--delay-seconds", str(DELAY_SECONDS)]
    cmd += ["--frame-offset", str(FRAME_OFFSET)]

    fixation_root = getattr(args, "fixation_root", None) or _env_first(
        "FIXATION_ROOT", "REPROJECT_PROCESSED_FIXATIONS_ROOT"
    )
    if fixation_root:
        cmd += ["--fixation-root", str(fixation_root)]

    # Dataset-specific paths
    if job.dataset == "3dva":
        _env_flags(cmd, {
            "THREE_DVA_JSON_ROOT":       "--json-root",
            "THREE_DVA_COMBINED_GT_DIR": "--combined-gt-dir",
        })
    elif job.dataset == "meshmamba_non_texture":
        _env_flags(cmd, {
            "MESHMAMBA_JSON_ROOT":           "--json-root",
            "MESHMAMBA_NON_TEXTURE_ROOT":    "--dataset-root",
        })
        cmd += ["--texture-type", "non_texture"]
    elif job.dataset == "meshmamba_rgb_texture":
        _env_flags(cmd, {
            "MESHMAMBA_RGB_TEXTURE_JSON_ROOT": "--json-root",
            "MESHMAMBA_RGB_TEXTURE_ROOT":      "--dataset-root",
        })
        cmd += ["--texture-type", "rgb_texture"]
    elif job.dataset == "sal3d":
        _env_flags(cmd, {
            "SAL3D_JSON_ROOT":      "--json-root",
            "SAL3D_DATASET_ROOT":   "--dataset-root",
            "SAL3D_FIXED_GT_DIR":   "--fixed-gt-dir",
        })

    # Sigma parameters
    if job.method == "screen_space":
        img_w = _IMG_WIDTH[job.dataset]
        if img_w == 256:
            cmd += ["--sigma-screen", str(job.sigma_screen)]
        else:
            # Convert fraction → absolute pixels for 1920-wide evaluators
            sigma_px = round(job.sigma_screen * img_w, 4)
            cmd += ["--sigma-px", str(sigma_px)]
    elif job.method == "cone":
        cmd += ["--sigma-deg", str(job.sigma_deg),
                "--radius-sigma-mult", str(job.radius_sigma_mult)]

    task_out = _task_output_dir(job, args)
    cmd += ["--output-dir", str(task_out)]
    cmd += ["--tag", f"sigma_sweep_{job.sigma_tag}"]
    return cmd


def _task_output_dir(job: SigmaSweepJob, args: argparse.Namespace) -> Path:
    return Path(args.batch_output_dir) / "per_task" / job.dataset / job.model / f"{job.method}_{job.sigma_tag}"


# ── job execution ─────────────────────────────────────────────────────────────

def execute_job(job: SigmaSweepJob, args: argparse.Namespace) -> dict[str, Any]:
    row: dict[str, Any] = {col: "" for col in CSV_COLUMNS}
    row.update({
        "job_key":            job.key,
        "dataset":            job.dataset,
        "texture_type":       job.texture_type,
        "model":              job.model,
        "method":             job.method,
        "timing_contract":    TIMING_CONTRACT,
        "delay_seconds":      DELAY_SECONDS,
        "frame_offset":       FRAME_OFFSET,
        "fixation_data_tag":  FIXATION_DATA_TAG,
        "release_tag":        RELEASE_TAG,
    })
    if job.sigma_screen is not None:
        row["sigma_screen"] = job.sigma_screen
    if job.sigma_deg is not None:
        row["sigma_deg"] = job.sigma_deg
    if job.radius_sigma_mult is not None:
        row["radius_sigma_mult"] = job.radius_sigma_mult

    cmd = build_command(job, args)
    task_out = _task_output_dir(job, args)
    task_out.mkdir(parents=True, exist_ok=True)
    log_path = task_out / "stdout.log"
    row["stdout_log_path"] = str(log_path)

    if args.dry_run:
        row["status"] = "ok"
        row["error_type"] = "dry_run"
        row["error_message"] = " ".join(str(x) for x in cmd)
        return row

    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=args.timeout_seconds,
        )
        row["elapsed_sec"] = round(time.monotonic() - t0, 1)
        log_path.write_bytes(proc.stdout)
        if proc.returncode != 0:
            row["status"] = "failed"
            row["error_type"] = "nonzero_exit"
            row["error_message"] = f"exit code {proc.returncode}"
            return row
    except subprocess.TimeoutExpired:
        row["status"] = "failed"
        row["error_type"] = "timeout"
        row["error_message"] = f"exceeded {args.timeout_seconds}s"
        return row
    except Exception as exc:
        row["status"] = "runtime_error"
        row["error_type"] = type(exc).__name__
        row["error_message"] = str(exc)
        return row

    report_files = sorted(task_out.rglob("*.json"))
    if not report_files:
        row["status"] = "failed"
        row["error_type"] = "missing_report"
        return row

    report_path = report_files[0]
    row["report_path"] = str(report_path)
    try:
        report = json.loads(report_path.read_text())
    except Exception as exc:
        row["status"] = "failed"
        row["error_type"] = "report_parse_error"
        row["error_message"] = str(exc)
        return row

    metrics = (
        report.get("metrics_vs_gt_covered_only")
        or report.get("metrics_vs_fixed_face_gt")
        or report.get("metrics_full")
        or report.get("metrics")
        or {}
    )
    row["CC"]       = metrics.get("CC", "")
    row["SIM"]      = metrics.get("SIM", "")
    row["KLD"]      = metrics.get("KLD", "")
    row["NSS"]      = metrics.get("NSS", metrics.get("NSS_gt_top_10pct_proxy", ""))
    row["AUC_Judd"] = metrics.get("AUC_Judd", metrics.get("AUC_Judd_gt_top_10pct_proxy", ""))
    row["Spearman"] = metrics.get("Spearman", "")
    row["MSE"]      = metrics.get("MSE", "")

    prov = report.get("participant_input", {})
    row["gaze_start_frame"]      = prov.get("gaze_start_frame", "")
    row["placement_start_frame"] = prov.get("placement_start_frame", "")
    row["turn_frames_used"]      = prov.get("turn_frame_count", "")
    row["repo_commit"]           = report.get("git_commit", "")
    row["status"] = "ok"
    return row


# ── thread-safe JSONL writer ──────────────────────────────────────────────────

class _JsonlWriter:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, row: dict[str, Any]) -> None:
        line = json.dumps(row) + "\n"
        with self._lock:
            with self._path.open("a") as f:
                f.write(line)


# ── CSV aggregation ───────────────────────────────────────────────────────────

def aggregate_csv(batch_dir: Path) -> Path:
    jsonl_path = batch_dir / "sigma_sweep_rows.jsonl"
    csv_path   = batch_dir / "sigma_sweep_summary.csv"
    if not jsonl_path.is_file():
        raise FileNotFoundError(jsonl_path)
    rows: list[dict[str, Any]] = []
    with jsonl_path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    rows.sort(key=lambda r: (
        r.get("dataset",""), r.get("model",""), r.get("method",""),
        float(r.get("sigma_screen") or 0), float(r.get("sigma_deg") or 0),
    ))
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in CSV_COLUMNS})
    return csv_path


# ── argument parsing ──────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sigma sweep runner (rc3). DO NOT RUN without reviewer/controller approval.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--datasets", nargs="+", default=ALL_DATASETS, choices=ALL_DATASETS)
    parser.add_argument("--methods",  nargs="+", default=ALL_METHODS,  choices=ALL_METHODS)
    parser.add_argument("--models",   nargs="+", default=None,
                        help="Override model list (skips sigma_sweep_model_lists JSON).")

    parser.add_argument(
        "--sigma-screen-values", nargs="+", type=float,
        default=DEFAULT_SIGMA_SCREEN, metavar="FRAC",
        help="sigma_screen sweep values (fraction of image width). "
             "For MeshMamba: --sigma-screen; for 3DVA/SAL3D: --sigma-px = value × 1920.",
    )
    parser.add_argument(
        "--sigma-deg-values", nargs="+", type=float,
        default=DEFAULT_SIGMA_DEG, metavar="DEG",
        help="sigma_deg sweep values for cone (degrees).",
    )
    parser.add_argument(
        "--radius-sigma-mult-values", nargs="+", type=float,
        default=DEFAULT_RADIUS_MULT, metavar="MULT",
        help="radius_sigma_mult sweep values for cone.",
    )

    parser.add_argument("--fixation-root", type=Path, default=None)
    parser.add_argument(
        "--batch-output-dir", type=Path,
        default=REPO_ROOT / "results" / "sigma_sweep_rc3",
    )
    parser.add_argument("--workers",      type=int, default=4)
    parser.add_argument("--shard-index",  type=int, default=0, metavar="I")
    parser.add_argument("--num-shards",   type=int, default=1, metavar="N")
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    parser.add_argument("--dry-run",      action="store_true",
                        help="Build commands and count jobs without executing evaluators.")
    parser.add_argument("--aggregate-only", action="store_true",
                        help="Read sigma_sweep_rows.jsonl and write sigma_sweep_summary.csv.")
    return parser.parse_args()


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    args = parse_args()
    batch_dir = Path(args.batch_output_dir)
    batch_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = batch_dir / "sigma_sweep_rows.jsonl"

    if args.aggregate_only:
        csv_path = aggregate_csv(batch_dir)
        print(f"[sigma_sweep] aggregated → {csv_path}")
        return 0

    jobs = build_job_list(args)
    completed_keys = load_completed_keys(jsonl_path)
    writer = _JsonlWriter(jsonl_path)

    pending: list[SigmaSweepJob] = []
    for job in jobs:
        if job.key in completed_keys:
            print(f"[sigma_sweep] resume-skip: {job.key}", flush=True)
        else:
            pending.append(job)

    total = len(jobs)
    skipped_resume = total - len(pending)

    print(f"[sigma_sweep] jobs: {total} total, {skipped_resume} resume-skipped, {len(pending)} to run", flush=True)
    print(f"[sigma_sweep] workers: {args.workers}  shards: {args.num_shards}  shard_index: {args.shard_index}", flush=True)
    print(f"[sigma_sweep] methods: {args.methods}", flush=True)
    if "screen_space" in args.methods:
        print(f"[sigma_sweep] sigma_screen values: {args.sigma_screen_values}", flush=True)
    if "cone" in args.methods:
        print(f"[sigma_sweep] sigma_deg values: {args.sigma_deg_values}", flush=True)
        print(f"[sigma_sweep] radius_sigma_mult values: {args.radius_sigma_mult_values}", flush=True)
    print(f"[sigma_sweep] output: {batch_dir}", flush=True)

    if args.dry_run:
        print(f"[sigma_sweep] DRY RUN — showing sample commands", flush=True)
        shown = 0
        for job in pending:
            if shown >= 4:
                break
            cmd = build_command(job, args)
            print(f"  {job.key}")
            print(f"    cmd: {' '.join(str(x) for x in cmd)}")
            shown += 1
        if len(pending) > 4:
            print(f"  ... and {len(pending) - 4} more")
        print()

    done = ok = failed = 0

    def _run(job: SigmaSweepJob) -> dict[str, Any]:
        return execute_job(job, args)

    if args.workers <= 1 or args.dry_run:
        for job in pending:
            row = execute_job(job, args)
            writer.append(row)
            done += 1
            ok      += row["status"] == "ok"
            failed  += row["status"] not in ("ok", "skipped")
            if not args.dry_run:
                print(
                    f"[sigma_sweep] {done}/{len(pending)} "
                    f"{job.dataset}/{job.model}/{job.method} {job.sigma_tag} → {row['status']}",
                    flush=True,
                )
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(_run, job): job for job in pending}
            for fut in as_completed(futures):
                job = futures[fut]
                try:
                    row = fut.result()
                except Exception as exc:
                    row = {col: "" for col in CSV_COLUMNS}
                    row.update({
                        "job_key": job.key, "dataset": job.dataset,
                        "model": job.model, "method": job.method,
                        "status": "runtime_error",
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    })
                writer.append(row)
                done += 1
                ok     += row["status"] == "ok"
                failed += row["status"] not in ("ok", "skipped")
                print(
                    f"[sigma_sweep] {done}/{len(pending)} "
                    f"{job.dataset}/{job.model}/{job.method} {job.sigma_tag} → {row['status']}",
                    flush=True,
                )

    print(f"[sigma_sweep] done: ok={ok} failed={failed} resume_skipped={skipped_resume}", flush=True)

    try:
        csv_path = aggregate_csv(batch_dir)
        print(f"[sigma_sweep] aggregated → {csv_path}", flush=True)
    except Exception as exc:
        print(f"[sigma_sweep] aggregation failed: {exc}", flush=True)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
