#!/usr/bin/env python3
"""
RC3 full metric run with optimized sigmas selected from sigma sweep stage-1.

Runs all 4 dataset tracks × 2 methods using sigma values chosen to maximize
mean CC on the 25-model sweep subset.  Timing and release are locked at the
rc3 baseline contract (one_turn_from_start, delay=0, frame_offset=0).

Selected sigmas (from results/sigma_sweep_rc3/final/selected_sigmas_for_full_run.md):

  3DVA           cone          sigma_deg=2.0
  3DVA           screen_space  sigma_px=34.3  (0.70 × 49.0)
  MeshMamba nt   cone          sigma_deg=0.8
  MeshMamba nt   screen_space  sigma_screen=0.025  (0.50 × 0.05)
  MeshMamba rgb  cone          sigma_deg=1.0
  MeshMamba rgb  screen_space  sigma_screen=0.025  (0.50 × 0.05)
  SAL3D          cone          sigma_deg=2.0
  SAL3D          screen_space  sigma_px=39.45  (1.50 × 26.3)

Boundary-risk cases (curve was at sweep edge — may not be global optimum):
  3DVA cone, MeshMamba ss, SAL3D ss

Model lists
-----------
Full run uses ALL models from jsons/dataset_model_info/{dataset}_models.json,
minus known exclusions:
  3DVA:  exclude "jessi"
  SAL3D: exclude models without fixation JSON (determined at runtime)

Override:
  --models MODEL [MODEL ...]    explicit list (all datasets)
  --model-list-file FILE        one model per line, comments with #

Environment variables (set in configs/server_vg_intellect.env or equivalent):
  FIXATION_ROOT
  THREE_DVA_JSON_ROOT
  THREE_DVA_COMBINED_GT_DIR
  MESHMAMBA_JSON_ROOT
  MESHMAMBA_NON_TEXTURE_ROOT
  MESHMAMBA_RGB_TEXTURE_ROOT
  MESHMAMBA_RGB_TEXTURE_JSON_ROOT
  SAL3D_JSON_ROOT
  SAL3D_DATASET_ROOT
  SAL3D_FIXED_GT_DIR
  SAL3D_SMOOTH_GAZE_DIR   (optional, for GT smoothing)
  REPROJECT_PYTHON        (defaults to sys.executable)
  OUTPUT_ROOT             (defaults to repo/results/)

Usage
-----
  # Dry-run — print job counts AND sample commands (no execution):
  python3 test/launch/run_full_metrics_optimized_sigma.py --dry-run

  # Print counts only (no commands, no output dir created):
  python3 test/launch/run_full_metrics_optimized_sigma.py --print-counts

  # Smoke run — 1 model per dataset/method pair:
  python3 test/launch/run_full_metrics_optimized_sigma.py \\
      --smoke \\
      --batch-output-dir /tmp/rc3_opt_smoke_$(date +%Y%m%d_%H%M%S)

  # Full run (DO NOT launch without reviewer/controller approval):
  python3 test/launch/run_full_metrics_optimized_sigma.py \\
      --workers 8 \\
      --batch-output-dir "$OUTPUT_ROOT/rc3_full_metrics_optimized_sigmas_$(date +%Y%m%d_%H%M%S)"

DO NOT LAUNCH FULL RUN without reviewer/controller approval.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

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

# ── optimized sigma values ────────────────────────────────────────────────────
# Selected from rc3_sigma_sweep_20260611_stage1_fix3 by best mean CC.
# See: results/sigma_sweep_rc3/final/selected_sigmas_for_full_run.md

_SIGMA_CONE_DEG: dict[str, float] = {
    "3dva":                  2.0,
    "meshmamba_non_texture": 0.8,
    "meshmamba_rgb_texture": 1.0,
    "sal3d":                 2.0,
}
_SIGMA_RADIUS_MULT: float = 3.0

# Screen-space: sigma_px for 1920-wide datasets, sigma_screen for 256-wide
_SIGMA_SS_PX: dict[str, float] = {
    "3dva":  34.3,   # 0.70 × 49.0 baseline
    "sal3d": 39.45,  # 1.50 × 26.3 baseline
}
_SIGMA_SS_SCREEN: dict[str, float] = {
    "meshmamba_non_texture": 0.025,  # 0.50 × 0.05 baseline
    "meshmamba_rgb_texture": 0.025,
}

# ── fixed rc3 timing ──────────────────────────────────────────────────────────

TIMING_CONTRACT   = "one_turn_from_start"
DELAY_SECONDS     = 0.0
FRAME_OFFSET      = 0
# Release tag is environment-driven so an rc4 (or later) run records the right
# provenance without editing this file; defaults to rc3 for backward compatibility.
RELEASE_TAG       = os.environ.get("REPROJECT_RELEASE_TAG", "v2.0-data-rc3")
FIXATION_DATA_TAG = "processed_fixations_offset0_full_cleaned"

# ── model exclusions ──────────────────────────────────────────────────────────
# Models known to be invalid or consistently missing data across all sigmas.

_EXCLUDED_MODELS: dict[str, list[str]] = {
    "3dva":  ["jessi"],  # participant data unavailable
    "sal3d": [],         # runtime exclusions handled by inventory_models()
}

# ── smoke models (1 per dataset — representative + historically tricky) ───────

_SMOKE_MODELS: dict[str, str] = {
    "3dva":                  "A380",
    "meshmamba_non_texture": "Watermelon_V1_L3",
    "meshmamba_rgb_texture": "Watermelon_V1_L3",
    "sal3d":                 "alien2",
}


# ── model discovery ───────────────────────────────────────────────────────────

def load_full_model_list(dataset: str) -> list[str]:
    """Load full model list from jsons/dataset_model_info/{dataset}_models.json."""
    info_file = REPO_ROOT / "jsons" / "dataset_model_info" / f"{dataset}_models.json"
    if not info_file.is_file():
        raise FileNotFoundError(f"Model info file not found: {info_file}")
    data = json.loads(info_file.read_text())
    models = data.get("models", [])
    # items may be strings or dicts with a "model" key
    names = [m if isinstance(m, str) else m["model"] for m in models]
    excluded = _EXCLUDED_MODELS.get(dataset, [])
    return [n for n in names if n not in excluded]


def inventory_sal3d_models(candidate_models: list[str]) -> list[str]:
    """
    Filter SAL3D candidates to those with a valid fixation JSON.
    Falls back to returning all candidates if FIXATION_ROOT is not set.
    """
    fixation_root_str = os.environ.get("FIXATION_ROOT", "") or \
                        os.environ.get("REPROJECT_PROCESSED_FIXATIONS_ROOT", "")
    if not fixation_root_str:
        print("[warn] FIXATION_ROOT not set; skipping SAL3D fixation filter")
        return candidate_models
    fixation_root = Path(fixation_root_str)
    valid = []
    for m in candidate_models:
        fj = fixation_root / f"SAL3D_{m}" / "fixations.json"
        if fj.is_file():
            valid.append(m)
        else:
            print(f"[skip] sal3d/{m}: fixation JSON not found — {fj}")
    return valid


def resolve_model_list(
    dataset: str,
    explicit_models: list[str] | None,
    smoke: bool,
) -> list[str]:
    if explicit_models:
        return list(explicit_models)
    if smoke:
        sm = _SMOKE_MODELS.get(dataset)
        if sm:
            return [sm]
        raise ValueError(f"No smoke model defined for {dataset}")
    models = load_full_model_list(dataset)
    if dataset == "sal3d":
        models = inventory_sal3d_models(models)
    return models


# ── environment helpers ───────────────────────────────────────────────────────

def _env(*keys: str) -> str:
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


# ── command building ──────────────────────────────────────────────────────────

def build_command(
    dataset: str,
    method: str,
    model: str,
    task_out: Path,
    args: argparse.Namespace,
) -> list[str]:
    script = _EVAL[dataset][method]
    python = _env("REPROJECT_PYTHON") or sys.executable
    nice_n = getattr(args, "nice", 0)

    cmd: list[str] = []
    if nice_n != 0:
        cmd += ["nice", "-n", str(nice_n)]
    cmd += [python, str(script), "--model", model]
    cmd += ["--timing-contract", TIMING_CONTRACT,
            "--delay-seconds",   str(DELAY_SECONDS),
            "--frame-offset",    str(FRAME_OFFSET)]

    fixation_root = _env("FIXATION_ROOT", "REPROJECT_PROCESSED_FIXATIONS_ROOT")
    if fixation_root:
        cmd += ["--fixation-root", fixation_root]
    # Canonical, single-sourced provenance tag: the launcher dictates the tag the
    # evaluator records, instead of letting the evaluator derive it from the
    # fixation-root basename (which could disagree with what the launcher logs).
    cmd += ["--fixation-data-tag", FIXATION_DATA_TAG]

    if dataset == "3dva":
        _env_flags(cmd, {
            "THREE_DVA_JSON_ROOT":       "--json-root",
            "THREE_DVA_COMBINED_GT_DIR": "--combined-gt-dir",
        })
    elif dataset == "meshmamba_non_texture":
        _env_flags(cmd, {
            "MESHMAMBA_JSON_ROOT":        "--json-root",
            "MESHMAMBA_NON_TEXTURE_ROOT": "--dataset-root",
        })
        cmd += ["--texture-type", "non_texture"]
    elif dataset == "meshmamba_rgb_texture":
        _env_flags(cmd, {
            "MESHMAMBA_RGB_TEXTURE_JSON_ROOT": "--json-root",
            "MESHMAMBA_RGB_TEXTURE_ROOT":      "--dataset-root",
        })
        cmd += ["--texture-type", "rgb_texture"]
    elif dataset == "sal3d":
        _env_flags(cmd, {
            "SAL3D_JSON_ROOT":       "--json-root",
            "SAL3D_DATASET_ROOT":    "--dataset-root",
            "SAL3D_FIXED_GT_DIR":    "--fixed-gt-dir",
            "SAL3D_SMOOTH_GAZE_DIR": "--smooth-gaze-dir",
            "SAL3D_MANIFEST":        "--sal3d-manifest",
        })

    if method == "screen_space":
        if dataset in _SIGMA_SS_PX:
            cmd += ["--sigma-px", str(_SIGMA_SS_PX[dataset])]
        else:
            cmd += ["--sigma-screen", str(_SIGMA_SS_SCREEN[dataset])]
    else:
        cmd += ["--sigma-deg", str(_SIGMA_CONE_DEG[dataset]),
                "--radius-sigma-mult", str(_SIGMA_RADIUS_MULT)]

    tag = _build_tag(dataset, method)
    cmd += ["--output-dir", str(task_out), "--tag", tag]
    return cmd


def _build_tag(dataset: str, method: str) -> str:
    if method == "screen_space":
        if dataset in _SIGMA_SS_PX:
            px = _SIGMA_SS_PX[dataset]
            return f"opt_sigpx{str(px).replace('.','p')}_rc3_timing"
        else:
            sc = _SIGMA_SS_SCREEN[dataset]
            return f"opt_sigsc{str(sc).replace('.','p')}_rc3_timing"
    else:
        deg = _SIGMA_CONE_DEG[dataset]
        return f"opt_sigdeg{str(deg).replace('.','p')}_r3p0_rc3_timing"


def _task_output_dir(dataset: str, method: str, model: str, batch_dir: Path) -> Path:
    return batch_dir / "per_task" / dataset / model / method


def _select_report(task_out: Path) -> Path | None:
    """Deterministically choose the evaluator report from a task directory.

    Prefer a ``*_report.json`` (the canonical evaluator output), excluding our own
    sidecar files.  Fall back to the lexicographically-first remaining ``*.json``.
    Sorting makes the choice reproducible regardless of filesystem iteration order.
    """
    sidecars = {"provenance.json", "metrics_rows.json"}
    candidates = [p for p in sorted(task_out.rglob("*.json")) if p.name not in sidecars]
    if not candidates:
        return None
    preferred = [p for p in candidates if p.name.endswith("_report.json")]
    return preferred[0] if preferred else candidates[0]


def _provenance_mismatches(report: dict) -> list[str]:
    """List provenance problems: a required participant_input field that is missing
    is a mismatch, as is any present field that disagrees with the run contract.
    """
    prov = report.get("participant_input")
    if not isinstance(prov, dict):
        return ["participant_input missing or not an object"]

    out: list[str] = []
    # Required fields must be present.
    for field in ("timing_contract", "frame_offset", "fixation_data_tag",
                  "delay_frames", "fps"):
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
    df = prov.get("delay_frames")
    fps = prov.get("fps")
    if df not in (None, "") and fps not in (None, ""):
        try:
            expected_df = round(DELAY_SECONDS * float(fps))
            if int(df) != expected_df:
                out.append(f"delay_frames={df!r}!={expected_df}")
        except (TypeError, ValueError):
            out.append(f"delay_frames={df!r}/fps={fps!r} not numeric")
    return out


# ── metric extraction ─────────────────────────────────────────────────────────

def extract_metrics(report: dict, dataset: str, method: str) -> dict | None:
    method_key = "screen_space_gaussian" if method == "screen_space" else "cone_gaussian_on_mesh"

    def _leaf(section: Any, *keys: str) -> dict | None:
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


def _load_and_dedup_jsonl(jsonl_path: Path) -> list[dict]:
    """Load every JSONL row and deduplicate by job_key (ok preferred over failed).

    Used to build the final CSVs so that a resumed run aggregates prior rows with
    this run's rows instead of emitting only its own partial slice.
    """
    if not jsonl_path.is_file():
        return []
    best: dict[str, tuple[int, dict]] = {}
    order: list[str] = []
    with jsonl_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = row.get("job_key", "")
            if not key:
                continue
            prio = 0 if (row.get("status") == "ok"
                         and row.get("error_type", "") != "dry_run") else 1
            if key not in best:
                order.append(key)
                best[key] = (prio, row)
            elif prio < best[key][0]:
                best[key] = (prio, row)
    return [best[k][1] for k in order]


def _sigma_signature(dataset: str, method: str) -> str:
    """Stable string capturing the sigma config for one (dataset, method)."""
    if method == "cone":
        return f"cone_sd{_SIGMA_CONE_DEG[dataset]}_r{_SIGMA_RADIUS_MULT}"
    if dataset in _SIGMA_SS_PX:
        return f"ss_px{_SIGMA_SS_PX[dataset]}"
    return f"ss_sc{_SIGMA_SS_SCREEN[dataset]}"


def _config_signature(dataset: str, method: str) -> str:
    """Run-wide timing/release/fixation contract plus this job's sigma config.

    Folded into the resume key so resuming into a directory built under a
    different timing/fixation/sigma/release configuration cannot silently skip
    jobs that carry an incompatible (but same dataset/model/method) identity.
    """
    return (
        f"{RELEASE_TAG}|{TIMING_CONTRACT}|{FIXATION_DATA_TAG}"
        f"|fo{FRAME_OFFSET}|dl{DELAY_SECONDS}|{_sigma_signature(dataset, method)}"
    )


def _job_key(dataset: str, method: str, model: str) -> str:
    return f"optrun:{_config_signature(dataset, method)}:{dataset}:{model}:{method}"


# ── job execution ─────────────────────────────────────────────────────────────

def execute_job(
    dataset: str,
    method: str,
    model: str,
    batch_dir: Path,
    args: argparse.Namespace,
) -> dict[str, Any]:
    key      = _job_key(dataset, method, model)
    task_out = _task_output_dir(dataset, method, model, batch_dir)
    task_out.mkdir(parents=True, exist_ok=True)
    log_path = task_out / "stdout.log"

    row: dict[str, Any] = {
        "job_key":          key,
        "dataset":          dataset,
        "texture_type":     "non_texture" if "non_texture" in dataset
                            else "rgb_texture" if "rgb_texture" in dataset
                            else "",
        "model":            model,
        "method":           method,
        "timing_contract":  TIMING_CONTRACT,
        "delay_seconds":    DELAY_SECONDS,
        "frame_offset":     FRAME_OFFSET,
        "fixation_data_tag": FIXATION_DATA_TAG,
        "release_tag":      RELEASE_TAG,
        "sigma_deg":        _SIGMA_CONE_DEG[dataset] if method == "cone" else "",
        "radius_sigma_mult": _SIGMA_RADIUS_MULT if method == "cone" else "",
        "sigma_px":         _SIGMA_SS_PX.get(dataset, "") if method == "screen_space" else "",
        "sigma_screen":     _SIGMA_SS_SCREEN.get(dataset, "") if method == "screen_space" else "",
        "stdout_log_path":  str(log_path),
    }

    cmd = build_command(dataset, method, model, task_out, args)

    if args.dry_run:
        row["status"]        = "ok"
        row["error_type"]    = "dry_run"
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

    # Verify the report was produced under this run's timing/provenance contract
    # before trusting its metrics (guards against a stale report in the task dir).
    prov_problems = _provenance_mismatches(report)
    if prov_problems:
        row.update(status="failed", error_type="provenance_mismatch",
                   error_message="; ".join(prov_problems))
        return row

    metrics = extract_metrics(report, dataset, method)
    if metrics is None:
        row.update(status="failed", error_type="missing_metrics",
                   error_message=f"keys: {list(report.keys())}")
        return row

    for key_m in ("CC", "SIM", "KLD", "NSS", "AUC_Judd", "Spearman", "MSE",
                  "MAE", "Cosine",
                  "AUC_Judd_gt_top_10pct_proxy", "AUC_Judd_gt_top_5pct_proxy",
                  "AUC_Judd_gt_top_1pct_proxy",
                  "NSS_gt_top_10pct_proxy", "NSS_gt_top_5pct_proxy",
                  "NSS_gt_top_1pct_proxy"):
        row[key_m] = metrics.get(key_m, "")
    # fallbacks for proxy names
    if not row.get("NSS"):
        row["NSS"] = metrics.get("NSS_gt_top_10pct_proxy", "")
    if not row.get("AUC_Judd"):
        row["AUC_Judd"] = metrics.get("AUC_Judd_gt_top_10pct_proxy", "")
    # hit_rate: reports store this in run_stats, not inside the metrics leaf
    run_stats = report.get("run_stats", {})
    row["hit_rate"] = (
        run_stats.get("hit_rate", "")
        or metrics.get("hit_rate", "")
    )

    prov = report.get("participant_input", {})
    row["gaze_start_frame"]      = prov.get("gaze_start_frame", "")
    row["placement_start_frame"] = prov.get("placement_start_frame", "")
    row["turn_frames_used"]      = prov.get("turn_frame_count", "")
    row["repo_commit"]           = report.get("git_commit", "")
    row["status"] = "ok"
    return row


# ── CSV output ────────────────────────────────────────────────────────────────

_LONG_COLS = [
    "job_key", "dataset", "texture_type", "model", "method",
    "sigma_deg", "radius_sigma_mult", "sigma_px", "sigma_screen",
    "CC", "SIM", "KLD", "MSE", "MAE", "Spearman", "Cosine",
    "AUC_Judd", "NSS",
    "AUC_Judd_gt_top_10pct_proxy", "AUC_Judd_gt_top_5pct_proxy",
    "AUC_Judd_gt_top_1pct_proxy",
    "NSS_gt_top_10pct_proxy", "NSS_gt_top_5pct_proxy", "NSS_gt_top_1pct_proxy",
    "hit_rate",
    "timing_contract", "delay_seconds", "frame_offset",
    "fixation_data_tag", "release_tag", "repo_commit",
    "gaze_start_frame", "placement_start_frame", "turn_frames_used",
    "report_path", "stdout_log_path",
    "status", "error_type", "error_message", "elapsed_sec",
]


def write_long_csv(rows: list[dict], path: Path) -> None:
    rows_sorted = sorted(rows, key=lambda r: (
        r.get("dataset", ""), r.get("model", ""), r.get("method", "")))
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_LONG_COLS, extrasaction="ignore")
        w.writeheader()
        for r in rows_sorted:
            w.writerow({c: r.get(c, "") for c in _LONG_COLS})


_COMPACT_ROW_ORDER = [
    ("3dva",                  "cone"),
    ("3dva",                  "screen_space"),
    ("meshmamba_non_texture", "cone"),
    ("meshmamba_non_texture", "screen_space"),
    ("meshmamba_rgb_texture", "cone"),
    ("meshmamba_rgb_texture", "screen_space"),
    ("sal3d",                 "cone"),
    ("sal3d",                 "screen_space"),
]
_COMPACT_METRICS = [
    "CC", "SIM", "KLD", "MSE", "MAE", "Spearman", "Cosine",
    "AUC_at_10pct", "AUC_at_5pct", "AUC_at_1pct",
    "NSS_at_10pct", "NSS_at_5pct", "NSS_at_1pct",
    "hit_rate",
]


def write_compact_csv(rows: list[dict], path: Path) -> None:
    def _fv(v: Any) -> float | None:
        # Drop non-finite values (json round-trips NaN/Infinity) so a single bad
        # metric cannot poison the mean.
        try:
            f = float(v)
        except (ValueError, TypeError):
            return None
        return f if math.isfinite(f) else None

    from collections import defaultdict
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("status") == "ok" and r.get("error_type", "") != "dry_run":
            groups[(r["dataset"], r["method"])].append(r)

    header = ["dataset_track", "method", "n_ok"] + _COMPACT_METRICS
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for ds, method in _COMPACT_ROW_ORDER:
            grp = groups.get((ds, method), [])
            if not grp:
                continue
            out: dict[str, Any] = {"dataset_track": ds, "method": method, "n_ok": len(grp)}
            proxy_map = {
                "AUC_at_10pct": "AUC_Judd_gt_top_10pct_proxy",
                "AUC_at_5pct":  "AUC_Judd_gt_top_5pct_proxy",
                "AUC_at_1pct":  "AUC_Judd_gt_top_1pct_proxy",
                "NSS_at_10pct": "NSS_gt_top_10pct_proxy",
                "NSS_at_5pct":  "NSS_gt_top_5pct_proxy",
                "NSS_at_1pct":  "NSS_gt_top_1pct_proxy",
            }
            for metric in _COMPACT_METRICS:
                col = proxy_map.get(metric, metric)
                vals = [v for r in grp if (v := _fv(r.get(col))) is not None]
                out[metric] = f"{sum(vals)/len(vals):.4f}" if vals else ""
            w.writerow([out.get(c, "") for c in header])


# ── provenance ────────────────────────────────────────────────────────────────

def write_provenance(batch_dir: Path, args: argparse.Namespace,
                     job_plan: dict[str, list[str]]) -> None:
    import datetime
    try:
        commit = subprocess.check_output(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        commit = "unknown"

    ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    prov = {
        "run_id":         batch_dir.name,
        "run_timestamp":  ts,
        "repo_commit":    commit,
        "release_tag":    RELEASE_TAG,
        "timing_contract": TIMING_CONTRACT,
        "delay_seconds":  DELAY_SECONDS,
        "frame_offset":   FRAME_OFFSET,
        "fixation_data_tag": FIXATION_DATA_TAG,
        "selected_sigmas": {
            "3dva_cone":                 {"sigma_deg": _SIGMA_CONE_DEG["3dva"],
                                          "radius_sigma_mult": _SIGMA_RADIUS_MULT},
            "3dva_screen_space":         {"sigma_px": _SIGMA_SS_PX["3dva"]},
            "meshmamba_non_texture_cone": {"sigma_deg": _SIGMA_CONE_DEG["meshmamba_non_texture"],
                                           "radius_sigma_mult": _SIGMA_RADIUS_MULT},
            "meshmamba_non_texture_ss":   {"sigma_screen": _SIGMA_SS_SCREEN["meshmamba_non_texture"]},
            "meshmamba_rgb_texture_cone": {"sigma_deg": _SIGMA_CONE_DEG["meshmamba_rgb_texture"],
                                           "radius_sigma_mult": _SIGMA_RADIUS_MULT},
            "meshmamba_rgb_texture_ss":   {"sigma_screen": _SIGMA_SS_SCREEN["meshmamba_rgb_texture"]},
            "sal3d_cone":                 {"sigma_deg": _SIGMA_CONE_DEG["sal3d"],
                                           "radius_sigma_mult": _SIGMA_RADIUS_MULT},
            "sal3d_screen_space":         {"sigma_px": _SIGMA_SS_PX["sal3d"]},
        },
        "sigma_source":    "rc3_sigma_sweep_20260611_stage1_fix3",
        "sigma_selection": "results/sigma_sweep_rc3/final/selected_sigmas_for_full_run.md",
        "boundary_risk_cases": [
            "3dva_cone (upper boundary — sigma_deg=2.0)",
            "meshmamba_non_texture_screen_space (lower boundary — sigma_screen=0.025)",
            "meshmamba_rgb_texture_screen_space (lower boundary — sigma_screen=0.025)",
            "sal3d_screen_space (upper boundary — sigma_px=39.45)",
        ],
        "job_counts": {ds: len(ms) for ds, ms in job_plan.items()},
        "workers": args.workers,
        "timeout_seconds": args.timeout_seconds,
        "nice": getattr(args, "nice", 0),
        "smoke": args.smoke,
        "dry_run": args.dry_run,
    }
    out_path = batch_dir / "provenance.json"
    out_path.write_text(json.dumps(prov, indent=2))
    print(f"[provenance] {out_path}")


# ── argument parsing ──────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--datasets",  nargs="+", default=ALL_DATASETS, choices=ALL_DATASETS)
    p.add_argument("--methods",   nargs="+", default=ALL_METHODS,  choices=ALL_METHODS)
    p.add_argument("--models",    nargs="+", default=None,
                   help="Explicit model list (applied to ALL datasets in --datasets).")
    p.add_argument("--model-list-file", type=Path, default=None,
                   help="Text file with one model per line (# = comment).")
    p.add_argument("--smoke",     action="store_true",
                   help="Run 1 control model per dataset/method.")
    p.add_argument("--workers",   type=int, default=4)
    p.add_argument("--nice",      type=int, default=0)
    p.add_argument("--timeout-seconds", type=int, default=3600)
    p.add_argument("--batch-output-dir", type=Path,
                   default=REPO_ROOT / "results" / "rc3_optimized_sigma_run")
    p.add_argument("--dry-run",   action="store_true",
                   help="Print commands without executing.")
    p.add_argument("--print-counts", action="store_true",
                   help="Print expected job counts and exit.")
    return p.parse_args()


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    args = parse_args()
    batch_dir = Path(args.batch_output_dir)

    # explicit model override from file
    explicit_models: list[str] | None = list(args.models) if args.models else None
    if args.model_list_file:
        lines = args.model_list_file.read_text().splitlines()
        file_models = [ln.strip() for ln in lines
                       if ln.strip() and not ln.lstrip().startswith("#")]
        explicit_models = (explicit_models or []) + file_models
        explicit_models = list(dict.fromkeys(explicit_models))  # dedup

    # build model lists per dataset
    job_plan: dict[str, list[str]] = {}
    for ds in args.datasets:
        job_plan[ds] = resolve_model_list(ds, explicit_models, args.smoke)

    # count summary — always printed for --print-counts; also printed inside --dry-run
    def _print_counts() -> None:
        total = 0
        for ds in args.datasets:
            n_models = len(job_plan[ds])
            n_methods = len(args.methods)
            n_jobs = n_models * n_methods
            total += n_jobs
            print(f"  {ds:35s}  {n_models:4d} models × {n_methods} methods = {n_jobs} jobs")
        print(f"  {'TOTAL':35s}  {total} jobs")

    if args.print_counts and not args.dry_run:
        _print_counts()
        return 0

    # build flat job list
    all_jobs: list[tuple[str, str, str]] = []
    for ds in args.datasets:
        for model in job_plan[ds]:
            for method in args.methods:
                all_jobs.append((ds, method, model))

    batch_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = batch_dir / "metrics_rows.jsonl"
    completed  = load_completed_keys(jsonl_path)
    writer     = _JsonlWriter(jsonl_path)

    pending = [(ds, meth, mdl) for (ds, meth, mdl) in all_jobs
               if _job_key(ds, meth, mdl) not in completed]
    skipped_resume = len(all_jobs) - len(pending)

    print(f"[run] jobs total={len(all_jobs)} resume_skip={skipped_resume} pending={len(pending)}")
    print(f"[run] workers={args.workers}  nice={args.nice}  timeout={args.timeout_seconds}s")
    print(f"[run] batch_dir={batch_dir}")
    print(f"[run] smoke={args.smoke}  dry_run={args.dry_run}")

    # per-dataset job breakdown
    for ds in args.datasets:
        ds_pending = [j for j in pending if j[0] == ds]
        print(f"  {ds:35s} {len(ds_pending):4d} pending")

    if args.dry_run:
        print("\n[dry-run] expected job counts:")
        _print_counts()
        print("\n[dry-run] sample commands:")
        for ds, method, model in pending[:4]:
            task_out = _task_output_dir(ds, method, model, batch_dir)
            cmd = build_command(ds, method, model, task_out, args)
            print(f"  {ds}/{model}/{method}")
            print(f"    {' '.join(str(x) for x in cmd)}")
        if len(pending) > 4:
            print(f"  ... and {len(pending)-4} more")
        write_provenance(batch_dir, args, job_plan)
        return 0

    write_provenance(batch_dir, args, job_plan)

    done = ok = failed = 0

    def _run(triple: tuple[str, str, str]) -> dict[str, Any]:
        ds, method, model = triple
        return execute_job(ds, method, model, batch_dir, args)

    rows: list[dict] = []

    if args.workers <= 1:
        for triple in pending:
            row = _run(triple)
            writer.append(row)
            rows.append(row)
            done += 1
            ok     += row["status"] == "ok"
            failed += row["status"] not in ("ok", "skipped")
            ds, method, model = triple
            print(f"[{done}/{len(pending)}] {ds}/{model}/{method} → {row['status']}")
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(_run, triple): triple for triple in pending}
            for fut in as_completed(futures):
                triple = futures[fut]
                try:
                    row = fut.result()
                except Exception as exc:
                    ds, method, model = triple
                    row = {"job_key": _job_key(ds, method, model),
                           "dataset": ds, "model": model, "method": method,
                           "status": "runtime_error",
                           "error_type": type(exc).__name__,
                           "error_message": str(exc)}
                writer.append(row)
                rows.append(row)
                done += 1
                ok     += row["status"] == "ok"
                failed += row["status"] not in ("ok", "skipped")
                ds, method, model = triple
                print(f"[{done}/{len(pending)}] {ds}/{model}/{method} → {row['status']}", flush=True)

    print(f"\n[run] done: ok={ok} failed={failed} resume_skipped={skipped_resume}")

    # Build the final CSVs from the FULL JSONL (resume-skipped rows from prior
    # runs + this run's rows), deduplicated by job_key, so a resumed run never
    # overwrites the CSV with only its own partial slice.
    all_rows = _load_and_dedup_jsonl(jsonl_path)
    long_csv    = batch_dir / "metrics_long.csv"
    compact_csv = batch_dir / "metrics_compact.csv"
    write_long_csv(all_rows, long_csv)
    write_compact_csv(all_rows, compact_csv)
    print(f"[run] aggregated {len(all_rows)} rows from {jsonl_path.name}")
    print(f"[run] long_csv:    {long_csv}")
    print(f"[run] compact_csv: {compact_csv}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
