#!/usr/bin/env python3
"""
Stage-1 sigma sweep runner — rc3 release.

Sweeps dataset-specific Gaussian parameters for screen_space_gaussian
and cone_gaussian_on_mesh with timing locked at rc3 baseline.

Design
──────
screen_space:  sigma_screen = BASE_SIGMA_SCREEN[dataset] × multiplier
  base sigma (sigma_screen, fraction of image width):
    3dva                  → 0.025  (≈ 49 px at 1920px)
    sal3d                 → 0.014  (≈ 26.3 px at 1920px)
    meshmamba_non_texture → 0.050  (= 12.8 px at 256px)
    meshmamba_rgb_texture → 0.050
  multipliers: 0.50 0.70 0.85 1.00 1.15 1.30 1.50   (7 values)
  Evaluator call:
    MeshMamba (256px):    --sigma-screen <effective>
    3DVA/SAL3D (1920px):  --sigma-px     <effective × 1920>

cone:  sigma_deg swept, radius_sigma_mult fixed at 3.0
  sigma_deg: 0.50 0.65 0.80 1.00 1.25 1.60 2.00      (7 values)
  radius_sigma_mult: 3.0 (fixed)

Model selection (stage-1)
─────────────────────────
25 models per dataset, 5 quintile bins × 5 evenly-spaced models each.
Lists in: jsons/sigma_sweep_model_lists/{dataset}_25models.json

Fixed timing (rc3)
──────────────────
  timing_contract:   one_turn_from_start
  delay_seconds:     0.0
  frame_offset:      0
  window_mode:       cut_tail
  fixation_data_tag: processed_fixations_offset0_full_cleaned

Job counts (total 1400)
────────────────────────
  screen_space: 25 × 4 datasets × 7 multipliers = 700
  cone:         25 × 4 datasets × 7 sigma_deg   = 700

Output
──────
  <batch_output_dir>/
    sigma_sweep_rows.jsonl           — one JSON row per job (appended atomically)
    sigma_sweep_partial_long.csv     — all completed rows, long format
    sigma_sweep_partial_summary.csv  — mean/std CC/SIM/KLD/NSS/MSE per sigma value
    sigma_sweep_best_so_far.csv      — best sigma per (dataset, model, method) by CC
    plots/
      cc_vs_sigma_screen_space.png
      cc_vs_sigma_cone.png
      kld_vs_sigma_screen_space.png
      kld_vs_sigma_cone.png
      sim_vs_sigma_screen_space.png
      sim_vs_sigma_cone.png
    per_task/<dataset>/<model>/<method>_<sigma_tag>/
      report.json
      stdout.log

Usage
─────
  # Full dry-run:
  python3 test/launch/run_sigma_sweep_rc3.py --dry-run

  # Partial aggregation during or after run:
  python3 test/launch/run_sigma_sweep_rc3.py --aggregate-only \\
      --batch-output-dir <path>

  # Aggregate without plots (faster):
  python3 test/launch/run_sigma_sweep_rc3.py --aggregate-only \\
      --no-plots --batch-output-dir <path>

  # Tiny smoke run (1 job, actually invokes evaluator — catches CLI arg errors):
  #   Requires: MESHMAMBA_JSON_ROOT, MESHMAMBA_NON_TEXTURE_ROOT, FIXATION_ROOT
  #   set in env (or sourced from server/rc3_ablation_env.sh).
  #   Use this instead of --dry-run when verifying CLI argument changes.
  python3 test/launch/run_sigma_sweep_rc3.py \\
      --datasets meshmamba_non_texture \\
      --methods screen_space \\
      --models Starfruit_L3 \\
      --ss-multipliers 1.0 \\
      --workers 1 \\
      --batch-output-dir /tmp/sigma_smoke_$(date +%Y%m%d_%H%M%S)

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
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

# ── dataset-specific base sigmas (sigma_screen = fraction of image width) ────

BASE_SIGMA_SCREEN: dict[str, float] = {
    "3dva":                  0.025,
    "meshmamba_non_texture": 0.050,
    "meshmamba_rgb_texture": 0.050,
    "sal3d":                 0.014,
}

_IMG_WIDTH: dict[str, int] = {
    "3dva":                  1920,
    "meshmamba_non_texture": 256,
    "meshmamba_rgb_texture": 256,
    "sal3d":                 1920,
}

# ── sigma grids ───────────────────────────────────────────────────────────────

SS_MULTIPLIERS:   list[float] = [0.50, 0.70, 0.85, 1.00, 1.15, 1.30, 1.50]
CONE_SIGMA_DEG:   list[float] = [0.50, 0.65, 0.80, 1.00, 1.25, 1.60, 2.00]
CONE_RADIUS_MULT: float       = 3.0

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

ALL_DATASETS = ["3dva", "meshmamba_non_texture", "meshmamba_rgb_texture", "sal3d"]
ALL_METHODS  = ["screen_space", "cone"]

# ── fixed rc3 timing ──────────────────────────────────────────────────────────

TIMING_CONTRACT   = "one_turn_from_start"
DELAY_SECONDS     = 0.0
FRAME_OFFSET      = 0
# Environment-driven so an rc4 (or later) sweep records the right provenance
# without editing this file; defaults to rc3 for backward compatibility.
RELEASE_TAG       = os.environ.get("REPROJECT_RELEASE_TAG", "v2.0-data-rc4")
FIXATION_DATA_TAG = "processed_fixations_offset0_full_cleaned"


def _config_signature() -> str:
    """Stable string capturing the run-wide timing/release/fixation contract.

    Read from the module globals at call time so a test (or REPROJECT_RELEASE_TAG)
    that changes the contract changes the signature — and therefore the job key
    and per-task paths.
    """
    return (f"{RELEASE_TAG}|{TIMING_CONTRACT}|{FIXATION_DATA_TAG}"
            f"|fo{FRAME_OFFSET}|dl{DELAY_SECONDS}")


def _config_path_token() -> str:
    """Filesystem-safe token for the config signature (release tag + short hash)."""
    digest = hashlib.md5(_config_signature().encode()).hexdigest()[:8]
    rel = RELEASE_TAG.replace(".", "p").replace("/", "_")
    return f"{rel}_{digest}"

# ── model list ────────────────────────────────────────────────────────────────

_MODEL_LIST_DIR = REPO_ROOT / "jsons" / "sigma_sweep_model_lists"

_DATASET_LIST_FILE: dict[str, str] = {
    "3dva":                  "3dva_25models.json",
    "meshmamba_non_texture": "meshmamba_non_texture_25models.json",
    "meshmamba_rgb_texture": "meshmamba_rgb_texture_25models.json",
    "sal3d":                 "sal3d_25models.json",
}


def load_model_list(dataset: str, models_override: list[str] | None = None) -> list[str]:
    if models_override:
        return list(models_override)
    path = _MODEL_LIST_DIR / _DATASET_LIST_FILE[dataset]
    if not path.is_file():
        raise FileNotFoundError(f"Model list not found: {path}")
    return [m["model"] for m in json.loads(path.read_text())["models"]]


def print_model_selections() -> None:
    """Print selected models per dataset to stdout (for preflight verification)."""
    for ds in ALL_DATASETS:
        path = _MODEL_LIST_DIR / _DATASET_LIST_FILE[ds]
        if not path.is_file():
            print(f"[models] {ds}: list file not found — {path}")
            continue
        data = json.loads(path.read_text())
        print(f"[models] {ds}: {data['n_selected']} models "
              f"(from {data['total_pool']} valid, {data['selection_method']})")
        for m in data["models"]:
            print(f"  Q{m['quintile']} {m['model']:40s} cc={m['cc_screen_space']:.4f}")


# ── job identity ──────────────────────────────────────────────────────────────

def _fmt(v: float) -> str:
    """Format float for use in key/tag strings: 1.0→'1p0', 0.5→'0p5'."""
    return str(v).replace(".", "p")


@dataclass
class SigmaSweepJob:
    dataset: str
    model: str
    method: str
    # screen_space fields
    sigma_multiplier: Optional[float] = None
    sigma_screen_base: Optional[float] = None
    sigma_screen_effective: Optional[float] = None
    # cone fields
    sigma_deg: Optional[float] = None
    radius_sigma_mult: float = CONE_RADIUS_MULT

    @property
    def texture_type(self) -> str:
        if "non_texture" in self.dataset:
            return "non_texture"
        if "rgb_texture" in self.dataset:
            return "rgb_texture"
        return ""

    @property
    def sigma_tag(self) -> str:
        if self.method == "screen_space":
            return f"ss_m{_fmt(self.sigma_multiplier)}"
        return f"cone_d{_fmt(self.sigma_deg)}_r{_fmt(self.radius_sigma_mult)}"

    @property
    def key(self) -> str:
        # Identity embeds the timing/release/fixation/frame_offset/delay contract so a
        # resume into a directory built under a different configuration cannot
        # silently skip jobs that share dataset/model/method/sigma but not contract.
        return (f"{_config_signature()}:"
                f"{self.dataset}:{self.model}:{self.method}:{self.sigma_tag}")

    def shard(self, num_shards: int) -> int:
        return int(hashlib.md5(self.key.encode()).hexdigest(), 16) % num_shards


# ── job list ──────────────────────────────────────────────────────────────────

def build_job_list(args: argparse.Namespace) -> list[SigmaSweepJob]:
    jobs: list[SigmaSweepJob] = []
    for dataset in args.datasets:
        models = load_model_list(dataset, args.models)
        base   = BASE_SIGMA_SCREEN[dataset]
        for model in models:
            if "screen_space" in args.methods:
                for mult in args.ss_multipliers:
                    jobs.append(SigmaSweepJob(
                        dataset=dataset, model=model, method="screen_space",
                        sigma_multiplier=mult,
                        sigma_screen_base=base,
                        sigma_screen_effective=round(base * mult, 8),
                    ))
            if "cone" in args.methods:
                for deg in args.cone_sigma_deg:
                    jobs.append(SigmaSweepJob(
                        dataset=dataset, model=model, method="cone",
                        sigma_deg=deg,
                        radius_sigma_mult=args.cone_radius_mult,
                    ))
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
                # Dry-run rows are placeholders, never real completions.
                if row.get("status") == "ok" and row.get("error_type", "") != "dry_run":
                    keys.add(row["job_key"])
            except (json.JSONDecodeError, KeyError):
                pass
    return keys


# ── command building ──────────────────────────────────────────────────────────

def _env_val(*keys: str) -> str:
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
    cmd = [python, str(script), "--model", job.model]
    cmd += ["--timing-contract", TIMING_CONTRACT,
            "--delay-seconds", str(DELAY_SECONDS),
            "--frame-offset", str(FRAME_OFFSET)]

    fixation_root = getattr(args, "fixation_root", None) or _env_val(
        "FIXATION_ROOT", "REPROJECT_PROCESSED_FIXATIONS_ROOT"
    )
    if fixation_root:
        cmd += ["--fixation-root", str(fixation_root)]
    # Canonical, single-sourced provenance tag (matches the full-run launcher).
    cmd += ["--fixation-data-tag", FIXATION_DATA_TAG]

    if job.dataset == "3dva":
        _env_flags(cmd, {
            "THREE_DVA_JSON_ROOT":       "--json-root",
            "THREE_DVA_COMBINED_GT_DIR": "--combined-gt-dir",
        })
    elif job.dataset == "meshmamba_non_texture":
        _env_flags(cmd, {
            "MESHMAMBA_JSON_ROOT":        "--json-root",
            "MESHMAMBA_NON_TEXTURE_ROOT": "--dataset-root",
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
            "SAL3D_JSON_ROOT":    "--json-root",
            "SAL3D_DATASET_ROOT": "--dataset-root",
            "SAL3D_FIXED_GT_DIR": "--fixed-gt-dir",
        })

    if job.method == "screen_space":
        img_w = _IMG_WIDTH[job.dataset]
        if img_w == 256:
            cmd += ["--sigma-screen", str(job.sigma_screen_effective)]
        else:
            sigma_px = round(job.sigma_screen_effective * img_w, 4)
            cmd += ["--sigma-px", str(sigma_px)]
    else:
        cmd += ["--sigma-deg", str(job.sigma_deg),
                "--radius-sigma-mult", str(job.radius_sigma_mult)]

    task_out = _task_output_dir(job, args)
    cmd += ["--output-dir", str(task_out),
            "--tag", f"sigma1_{_config_path_token()}_{job.sigma_tag}"]
    return cmd


def _task_output_dir(job: SigmaSweepJob, args: argparse.Namespace) -> Path:
    # Config token segregates per-task outputs by contract so a stale report from a
    # different release/timing/fixation/delay configuration is never selected.
    return (Path(args.batch_output_dir) / "per_task" / _config_path_token()
            / job.dataset / job.model / f"{job.method}_{job.sigma_tag}")


# ── metric extraction ─────────────────────────────────────────────────────────

def extract_metrics(report: dict, dataset: str, method: str) -> "dict[str, Any] | None":
    """
    Extract the canonical flat metrics dict {CC, SIM, KLD, ...} from a report.

    Lookup order mirrors the actual evaluator report layouts:
      MeshMamba *   : report["metrics_vs_gt"][method_key]
      SAL3D fixed   : report["metrics_vs_fixed_face_gt"][method_key]  (preferred)
      SAL3D raw GT  : report["metrics_vs_gt_covered_only"][method_key]
      3DVA *        : report["metrics_vs_gt_combined"][method_key]["metrics_covered_only"]

    method_key:  screen_space → "screen_space_gaussian"
                 cone         → "cone_gaussian_on_mesh"

    Returns None when no recognised metrics section is found; callers should
    treat that as a failed job with error_type="missing_metrics".
    """
    method_key = "screen_space_gaussian" if method == "screen_space" else "cone_gaussian_on_mesh"

    def _leaf(section: "Any", *keys: str) -> "dict | None":
        node = section
        for k in keys:
            if not isinstance(node, dict) or k not in node:
                return None
            node = node[k]
        return node if isinstance(node, dict) and "CC" in node else None

    return (
        _leaf(report.get("metrics_vs_gt"), method_key)
        or _leaf(report.get("metrics_vs_fixed_face_gt"), method_key)
        or _leaf(report.get("metrics_vs_gt_covered_only"), method_key)
        or _leaf(report.get("metrics_vs_gt_combined"), method_key, "metrics_covered_only")
        or _leaf(report.get("metrics_vs_gt_combined"), method_key, "metrics_full")
    )


# ── job execution ─────────────────────────────────────────────────────────────

def _select_report(task_out: Path) -> "Path | None":
    """Deterministically choose the evaluator report (prefer ``*_report.json``)."""
    sidecars = {"provenance.json", "metrics_rows.json"}
    candidates = [p for p in sorted(task_out.rglob("*.json")) if p.name not in sidecars]
    if not candidates:
        return None
    preferred = [p for p in candidates if p.name.endswith("_report.json")]
    return preferred[0] if preferred else candidates[0]


def _provenance_mismatches(report: dict) -> list[str]:
    """Required participant_input fields must be present and match the FIXED sweep
    contract (one_turn_from_start, frame_offset=0, delay_seconds=0).
    """
    prov = report.get("participant_input")
    if not isinstance(prov, dict):
        return ["participant_input missing or not an object"]
    out: list[str] = []
    for field in ("timing_contract", "frame_offset", "fixation_data_tag",
                  "delay_frames", "fps", "gaze_start_frame", "placement_start_frame"):
        if prov.get(field) in (None, ""):
            out.append(f"missing {field}")
    tc = prov.get("timing_contract")
    if tc not in (None, "") and tc != TIMING_CONTRACT:
        out.append(f"timing_contract={tc!r}!={TIMING_CONTRACT!r}")
    fo = prov.get("frame_offset")
    if fo not in (None, ""):
        try:
            if int(fo) != FRAME_OFFSET:
                out.append(f"frame_offset={fo!r}!={FRAME_OFFSET}")
        except (TypeError, ValueError):
            out.append(f"frame_offset={fo!r} not an int")
    tag = prov.get("fixation_data_tag")
    if tag not in (None, "") and tag != FIXATION_DATA_TAG:
        out.append(f"fixation_data_tag={tag!r}!={FIXATION_DATA_TAG!r}")

    fps = prov.get("fps")
    expected_delay_frames = None
    if fps not in (None, ""):
        try:
            expected_delay_frames = round(DELAY_SECONDS * float(fps))
        except (TypeError, ValueError):
            out.append(f"fps={fps!r} not numeric")
    if expected_delay_frames is not None:
        df = prov.get("delay_frames")
        if df not in (None, ""):
            try:
                if int(df) != expected_delay_frames:
                    out.append(f"delay_frames={df!r}!={expected_delay_frames}")
            except (TypeError, ValueError):
                out.append(f"delay_frames={df!r} not an int")
        expected_gaze_start = FRAME_OFFSET + max(0, expected_delay_frames)
        expected_placement_start = FRAME_OFFSET + max(0, -expected_delay_frames)
        gsf = prov.get("gaze_start_frame")
        if gsf not in (None, ""):
            try:
                if int(gsf) != expected_gaze_start:
                    out.append(f"gaze_start_frame={gsf!r}!={expected_gaze_start}")
            except (TypeError, ValueError):
                out.append(f"gaze_start_frame={gsf!r} not an int")
        psf = prov.get("placement_start_frame")
        if psf not in (None, ""):
            try:
                if int(psf) != expected_placement_start:
                    out.append(f"placement_start_frame={psf!r}!={expected_placement_start}")
            except (TypeError, ValueError):
                out.append(f"placement_start_frame={psf!r} not an int")
    return out


def execute_job(job: SigmaSweepJob, args: argparse.Namespace) -> dict[str, Any]:
    row: dict[str, Any] = {
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
        # sigma fields
        "base_sigma":              job.sigma_screen_base if job.method == "screen_space" else "",
        "sigma_multiplier":        job.sigma_multiplier if job.method == "screen_space" else "",
        "sigma_screen":            job.sigma_screen_effective if job.method == "screen_space" else "",
        "sigma_deg":               job.sigma_deg if job.method == "cone" else "",
        "radius_sigma_mult":       job.radius_sigma_mult if job.method == "cone" else "",
    }

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
            row.update(status="failed", error_type="nonzero_exit",
                       error_message=f"exit code {proc.returncode}")
            return row
    except subprocess.TimeoutExpired:
        row.update(status="failed", error_type="timeout",
                   error_message=f"exceeded {args.timeout_seconds}s")
        return row
    except Exception as exc:
        row.update(status="runtime_error", error_type=type(exc).__name__,
                   error_message=str(exc))
        return row

    report_path = _select_report(task_out)
    if report_path is None:
        row.update(status="failed", error_type="missing_report")
        return row

    row["report_path"] = str(report_path)
    try:
        report = json.loads(report_path.read_text())
    except Exception as exc:
        row.update(status="failed", error_type="report_parse_error",
                   error_message=str(exc))
        return row

    prov_problems = _provenance_mismatches(report)
    if prov_problems:
        row.update(status="failed", error_type="provenance_mismatch",
                   error_message="; ".join(prov_problems))
        return row

    metrics = extract_metrics(report, job.dataset, job.method)
    if metrics is None:
        row.update(
            status="failed",
            error_type="missing_metrics",
            error_message=(
                f"no metrics section found; top-level keys: {list(report.keys())}"
            ),
        )
        return row
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


# ── JSONL writer ──────────────────────────────────────────────────────────────

class _JsonlWriter:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, row: dict[str, Any]) -> None:
        with self._lock:
            with self._path.open("a") as f:
                f.write(json.dumps(row) + "\n")


# ── aggregation ───────────────────────────────────────────────────────────────

_LONG_COLS = [
    "job_key", "dataset", "texture_type", "model", "method",
    "base_sigma", "sigma_multiplier", "sigma_screen",
    "sigma_deg", "radius_sigma_mult",
    "CC", "SIM", "KLD", "NSS", "AUC_Judd", "Spearman", "MSE",
    "timing_contract", "delay_seconds", "frame_offset",
    "fixation_data_tag", "release_tag", "repo_commit",
    "gaze_start_frame", "placement_start_frame", "turn_frames_used",
    "report_path", "stdout_log_path",
    "status", "error_type", "error_message", "elapsed_sec",
]

_SUMMARY_COLS = [
    "dataset", "texture_type", "method",
    "sigma_param", "base_sigma", "sigma_multiplier", "sigma_value",
    "n_models",
    "mean_CC", "std_CC", "mean_SIM", "std_SIM",
    "mean_KLD", "std_KLD", "mean_NSS", "std_NSS",
    "mean_MSE", "std_MSE",
]

_BEST_COLS = [
    "dataset", "texture_type", "model", "method",
    "best_sigma_param", "best_sigma_value", "best_multiplier",
    "best_CC", "best_SIM", "best_KLD",
    "n_evaluated", "n_total",
]


def _fv(row: dict, col: str) -> float | None:
    v = row.get(col, "")
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _mean_std(vals: list[float]) -> tuple[str, str]:
    if not vals:
        return ("", "")
    n = len(vals)
    mean = sum(vals) / n
    if n > 1:
        std = (sum((x - mean) ** 2 for x in vals) / (n - 1)) ** 0.5
    else:
        std = 0.0
    return (f"{mean:.6f}", f"{std:.6f}")


def _load_ok_rows(jsonl_path: Path) -> list[dict[str, Any]]:
    if not jsonl_path.is_file():
        return []
    rows = []
    with jsonl_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                if r.get("status") == "ok" and r.get("error_type", "") != "dry_run":
                    rows.append(r)
            except json.JSONDecodeError:
                pass
    return rows


def write_partial_long(rows: list[dict], path: Path) -> None:
    rows_sorted = sorted(rows, key=lambda r: (
        r.get("dataset", ""), r.get("model", ""), r.get("method", ""),
        str(r.get("sigma_multiplier", "")), str(r.get("sigma_deg", "")),
    ))
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_LONG_COLS, extrasaction="ignore")
        w.writeheader()
        for r in rows_sorted:
            w.writerow({c: r.get(c, "") for c in _LONG_COLS})


def write_partial_summary(rows: list[dict], path: Path) -> None:
    # group key → list of metric dicts
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        method = r.get("method", "")
        if method == "screen_space":
            key = (r.get("dataset",""), r.get("texture_type",""), method,
                   r.get("sigma_multiplier",""), r.get("sigma_screen",""))
        else:
            key = (r.get("dataset",""), r.get("texture_type",""), method,
                   "", r.get("sigma_deg",""))
        groups[key].append(r)

    summary_rows = []
    for key, grp in sorted(groups.items()):
        ds, tex, method, mult, sig_val = key
        cc_vals  = [v for r in grp if (v := _fv(r, "CC")) is not None]
        sim_vals = [v for r in grp if (v := _fv(r, "SIM")) is not None]
        kld_vals = [v for r in grp if (v := _fv(r, "KLD")) is not None]
        nss_vals = [v for r in grp if (v := _fv(r, "NSS")) is not None]
        mse_vals = [v for r in grp if (v := _fv(r, "MSE")) is not None]
        m_cc, s_cc   = _mean_std(cc_vals)
        m_sim, s_sim = _mean_std(sim_vals)
        m_kld, s_kld = _mean_std(kld_vals)
        m_nss, s_nss = _mean_std(nss_vals)
        m_mse, s_mse = _mean_std(mse_vals)
        base = grp[0].get("base_sigma", "") if method == "screen_space" else ""
        summary_rows.append({
            "dataset": ds, "texture_type": tex, "method": method,
            "sigma_param":      "sigma_screen" if method == "screen_space" else "sigma_deg",
            "base_sigma":       base,
            "sigma_multiplier": mult if method == "screen_space" else "",
            "sigma_value":      sig_val,
            "n_models":         len(grp),
            "mean_CC": m_cc, "std_CC": s_cc,
            "mean_SIM": m_sim, "std_SIM": s_sim,
            "mean_KLD": m_kld, "std_KLD": s_kld,
            "mean_NSS": m_nss, "std_NSS": s_nss,
            "mean_MSE": m_mse, "std_MSE": s_mse,
        })

    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_SUMMARY_COLS, extrasaction="ignore")
        w.writeheader()
        for r in summary_rows:
            w.writerow({c: r.get(c, "") for c in _SUMMARY_COLS})


def write_best_so_far(rows: list[dict], path: Path) -> None:
    # group by (dataset, model, method)
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        key = (r.get("dataset",""), r.get("model",""), r.get("method",""))
        groups[key].append(r)

    n_total_map = {"screen_space": len(SS_MULTIPLIERS), "cone": len(CONE_SIGMA_DEG)}
    best_rows = []
    for (ds, model, method), grp in sorted(groups.items()):
        cc_evaluated = [(r, _fv(r, "CC")) for r in grp if _fv(r, "CC") is not None]
        if not cc_evaluated:
            continue
        best_r, best_cc = max(cc_evaluated, key=lambda x: x[1])
        tex = best_r.get("texture_type", "")
        if method == "screen_space":
            sigma_param = "sigma_screen"
            sigma_val   = best_r.get("sigma_screen", "")
            best_mult   = best_r.get("sigma_multiplier", "")
        else:
            sigma_param = "sigma_deg"
            sigma_val   = best_r.get("sigma_deg", "")
            best_mult   = ""
        best_rows.append({
            "dataset": ds, "texture_type": tex, "model": model, "method": method,
            "best_sigma_param":  sigma_param,
            "best_sigma_value":  sigma_val,
            "best_multiplier":   best_mult,
            "best_CC":           f"{best_cc:.6f}",
            "best_SIM":          f"{v:.6f}" if (v := _fv(best_r, "SIM")) is not None else "",
            "best_KLD":          f"{v:.6f}" if (v := _fv(best_r, "KLD")) is not None else "",
            "n_evaluated":       len(cc_evaluated),
            "n_total":           n_total_map.get(method, ""),
        })

    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_BEST_COLS, extrasaction="ignore")
        w.writeheader()
        for r in best_rows:
            w.writerow({c: r.get(c, "") for c in _BEST_COLS})


def write_plots(rows: list[dict], plots_dir: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("[sigma_sweep] matplotlib not available — skipping plots")
        return

    plots_dir.mkdir(parents=True, exist_ok=True)

    ds_colors = {
        "3dva":                  "#1f77b4",
        "meshmamba_non_texture": "#ff7f0e",
        "meshmamba_rgb_texture": "#2ca02c",
        "sal3d":                 "#d62728",
    }
    ds_labels = {
        "3dva":                  "3DVA",
        "meshmamba_non_texture": "MeshMamba non_tex",
        "meshmamba_rgb_texture": "MeshMamba rgb_tex",
        "sal3d":                 "SAL3D",
    }

    for metric in ("CC", "KLD", "SIM"):
        for method in ("screen_space", "cone"):
            method_rows = [r for r in rows if r.get("method") == method]
            if not method_rows:
                continue

            fig, ax = plt.subplots(figsize=(8, 5))
            plotted_any = False

            for ds in ALL_DATASETS:
                ds_rows = [r for r in method_rows if r.get("dataset") == ds]
                if not ds_rows:
                    continue

                if method == "screen_space":
                    x_key = "sigma_multiplier"
                    x_label = "Sigma multiplier (relative to base)"
                    x_all = sorted({_fv(r, x_key) for r in ds_rows
                                    if _fv(r, x_key) is not None})
                else:
                    x_key = "sigma_deg"
                    x_label = "Sigma (degrees)"
                    x_all = sorted({_fv(r, x_key) for r in ds_rows
                                    if _fv(r, x_key) is not None})

                xs, means, stds = [], [], []
                for xv in x_all:
                    grp = [r for r in ds_rows if _fv(r, x_key) == xv]
                    vals = [v for r in grp if (v := _fv(r, metric)) is not None]
                    if vals:
                        mn = sum(vals) / len(vals)
                        sd = (sum((v - mn) ** 2 for v in vals) / max(len(vals)-1, 1)) ** 0.5
                        xs.append(xv); means.append(mn); stds.append(sd)

                if not xs:
                    continue
                plotted_any = True
                color = ds_colors.get(ds, None)
                ax.plot(xs, means, marker="o", label=ds_labels.get(ds, ds), color=color)
                ax.fill_between(xs,
                                [m - s for m, s in zip(means, stds)],
                                [m + s for m, s in zip(means, stds)],
                                alpha=0.15, color=color)

            if not plotted_any:
                plt.close(fig)
                continue

            if method == "screen_space":
                ax.axvline(x=1.0, color="gray", linestyle="--", alpha=0.5,
                           label="base sigma (×1.0)")

            ax.set_xlabel(x_label)
            ax.set_ylabel(metric)
            ax.set_title(f"{metric} vs sigma — {method}")
            ax.legend(fontsize=8)
            ax.grid(True, alpha=0.3)

            fname = f"{metric.lower()}_vs_sigma_{method}.png"
            fig.tight_layout()
            fig.savefig(plots_dir / fname, dpi=120)
            plt.close(fig)
            print(f"[sigma_sweep] plot: {plots_dir / fname}")


def aggregate(batch_dir: Path, write_plots_flag: bool = True) -> None:
    jsonl_path = batch_dir / "sigma_sweep_rows.jsonl"
    ok_rows = _load_ok_rows(jsonl_path)
    total_lines = sum(1 for _ in jsonl_path.open()) if jsonl_path.is_file() else 0
    print(f"[sigma_sweep] aggregate: {len(ok_rows)} ok rows (of {total_lines} total lines)")

    write_partial_long(ok_rows,     batch_dir / "sigma_sweep_partial_long.csv")
    write_partial_summary(ok_rows,  batch_dir / "sigma_sweep_partial_summary.csv")
    write_best_so_far(ok_rows,      batch_dir / "sigma_sweep_best_so_far.csv")
    print(f"[sigma_sweep] wrote: partial_long.csv, partial_summary.csv, best_so_far.csv")

    if write_plots_flag and ok_rows:
        try:
            write_plots(ok_rows, batch_dir / "plots")
        except Exception as exc:
            print(f"[sigma_sweep] plot generation error (skipped): {exc}")


# ── argument parsing ──────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Stage-1 sigma sweep (rc3). DO NOT RUN without reviewer/controller approval.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--datasets", nargs="+", default=ALL_DATASETS, choices=ALL_DATASETS)
    p.add_argument("--methods",  nargs="+", default=ALL_METHODS,  choices=ALL_METHODS)
    p.add_argument("--models",   nargs="+", default=None,
                   help="Override model list (skips _25models.json).")
    p.add_argument("--ss-multipliers",    nargs="+", type=float, default=SS_MULTIPLIERS)
    p.add_argument("--cone-sigma-deg",    nargs="+", type=float, default=CONE_SIGMA_DEG)
    p.add_argument("--cone-radius-mult",  type=float, default=CONE_RADIUS_MULT)
    p.add_argument("--fixation-root",     type=Path, default=None)
    p.add_argument("--batch-output-dir",  type=Path,
                   default=REPO_ROOT / "results" / "sigma_sweep_rc3_stage1")
    p.add_argument("--workers",           type=int, default=4)
    p.add_argument("--shard-index",       type=int, default=0, metavar="I")
    p.add_argument("--num-shards",        type=int, default=1, metavar="N")
    p.add_argument("--timeout-seconds",   type=int, default=3600)
    p.add_argument("--dry-run",           action="store_true")
    p.add_argument("--aggregate-only",    action="store_true",
                   help="Read existing JSONL and write partial CSVs + plots.")
    p.add_argument("--no-plots",          action="store_true",
                   help="Skip plot generation during --aggregate-only.")
    p.add_argument("--print-models",      action="store_true",
                   help="Print selected model lists and exit.")
    return p.parse_args()


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    args = parse_args()
    batch_dir = Path(args.batch_output_dir)

    if args.print_models:
        print_model_selections()
        return 0

    if args.aggregate_only:
        batch_dir.mkdir(parents=True, exist_ok=True)
        aggregate(batch_dir, write_plots_flag=not args.no_plots)
        return 0

    batch_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = batch_dir / "sigma_sweep_rows.jsonl"
    jobs = build_job_list(args)
    completed = load_completed_keys(jsonl_path)
    writer = _JsonlWriter(jsonl_path)

    pending = [j for j in jobs if j.key not in completed]
    skipped_resume = len(jobs) - len(pending)

    print(f"[sigma_sweep] jobs: {len(jobs)} total, {skipped_resume} resume-skip, "
          f"{len(pending)} to run", flush=True)
    print(f"[sigma_sweep] workers: {args.workers}  shards: {args.num_shards}  "
          f"shard_index: {args.shard_index}", flush=True)
    print(f"[sigma_sweep] output: {batch_dir}", flush=True)

    if args.dry_run:
        print("[sigma_sweep] DRY RUN — sample commands:", flush=True)
        for job in pending[:3]:
            cmd = build_command(job, args)
            print(f"  {job.key}")
            print(f"    {' '.join(str(x) for x in cmd)}")
        if len(pending) > 3:
            print(f"  ... and {len(pending)-3} more")

    done = ok = failed = 0

    def _run(job: SigmaSweepJob) -> dict[str, Any]:
        return execute_job(job, args)

    if args.workers <= 1 or args.dry_run:
        for job in pending:
            row = _run(job)
            writer.append(row)
            done += 1
            ok     += row["status"] == "ok"
            failed += row["status"] not in ("ok", "skipped")
            if not args.dry_run:
                print(f"[sigma_sweep] {done}/{len(pending)} "
                      f"{job.dataset}/{job.model}/{job.method} {job.sigma_tag} "
                      f"→ {row['status']}", flush=True)
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(_run, job): job for job in pending}
            for fut in as_completed(futures):
                job = futures[fut]
                try:
                    row = fut.result()
                except Exception as exc:
                    row = {"job_key": job.key, "dataset": job.dataset, "model": job.model,
                           "method": job.method, "status": "runtime_error",
                           "error_type": type(exc).__name__, "error_message": str(exc)}
                writer.append(row)
                done += 1
                ok     += row["status"] == "ok"
                failed += row["status"] not in ("ok", "skipped")
                print(f"[sigma_sweep] {done}/{len(pending)} "
                      f"{job.dataset}/{job.model}/{job.method} {job.sigma_tag} "
                      f"→ {row['status']}", flush=True)

    print(f"[sigma_sweep] done: ok={ok} failed={failed} "
          f"resume_skipped={skipped_resume}", flush=True)

    if not args.dry_run:
        try:
            aggregate(batch_dir, write_plots_flag=True)
        except Exception as exc:
            print(f"[sigma_sweep] final aggregation failed: {exc}", flush=True)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
