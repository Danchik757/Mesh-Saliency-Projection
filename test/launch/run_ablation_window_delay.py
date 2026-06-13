#!/usr/bin/env python3
"""
Window / delay ablation runner.

DO NOT RUN until reviewer/controller grants explicit approval.
Target servers: vg-gml01 (shard 0), vg-gml02 (shard 1).

Architecture
────────────
Global job pool: every combination of (dataset, model, method, window_mode, delay_seconds)
is one job.  All jobs feed into a single ThreadPoolExecutor with --workers N, so fast
datasets (3DVA, MeshMamba) and slow ones (SAL3D cone) compete for the same worker slots
rather than running in separate queues.  This prevents the long-tail problem where SAL3D
runs alone while other dataset slots are idle.

Job identity key (used for sharding and resume) includes release, timing,
fixation-data tag, explicit frame offset, dataset/model/method, window mode,
delay, and sigma configuration. See `AblationJob.key` for the exact format.

Sharding: deterministic by MD5 hash of the job key modulo num_shards.  Both servers
must receive the same sorted job list and use shard-index 0 / 1 respectively.

Resume: on startup the runner loads all existing JSONL rows with status=ok and builds
a set of completed keys.  A job whose key is in the completed set is skipped (status=skipped,
error_type=already_done) without re-invoking the evaluator.

Status labels:
  ok              — evaluator ran, report found, metrics parsed
  skipped         — window_mode not yet evaluator-supported, or job already done (resume)
  failed          — evaluator non-zero exit, timeout, missing report, JSON parse error
  runtime_error   — unexpected exception in the runner itself

Window modes
────────────
  cut_tail  (evaluator-ready)
    gaze[max(0,d) : max(0,d)+N]  →  placement[max(0,-d) : max(0,-d)+N]
    delay=0:    gaze[0:N]   → placement[0:N]
    delay=+0.2: gaze[6:6+N] → placement[0:N]   (gaze leads by 0.2s × 30fps = 6 frames)
    delay=-0.2: gaze[0:N]   → placement[6:6+N]
    Evaluator flag: --timing-contract one_turn_from_start --delay-seconds <value>

  cut_head  (evaluator-ready: --frame-offset <tail>)
    Use the LAST turn_frames frames of gaze and placement, then apply delay.
    Let tail = total_frames − turn_frames  (= 60 for 3DVA/MeshMamba, = 60 for SAL3D).
    delay=0:    gaze[tail : tail+N]     → placement[tail : tail+N]
    delay=+0.2: gaze[tail+6 : tail+6+N] → placement[tail : tail+N]
    delay=-0.2: gaze[tail : tail+N]     → placement[tail+6 : tail+6+N]
    Evaluator flag: --frame-offset <tail> --delay-seconds <value>

  center  (evaluator-ready: --frame-offset <tail//2>)
    Use the center turn_frames frames (head_skip = (total − N) // 2), then apply delay.
    delay=0:    gaze[hs : hs+N]     → placement[hs : hs+N]
    delay=+0.2: gaze[hs+6 : hs+6+N] → placement[hs : hs+N]
    Evaluator flag: --frame-offset <tail//2> --delay-seconds <value>

Explicit frame-offset override
──────────────────────────────
  --frame-offset-override replaces the offset derived from --window-modes.
  This preserves controlled timing experiments that do not use the standard
  0 / tail//2 / tail offsets.  In particular:

    --window-modes cut_head --frame-offset-override 54 --delays 0.2

  produces gaze[60:60+N] → placement[54:54+N] at 30 fps.  The explicit
  offset is recorded in the job key, output path, CSV, and evaluator report
  provenance, so it cannot collide with the standard cut_head offset=60 run.

Delay grid (seconds):  -0.3  -0.2  -0.1  0.0  +0.1  +0.2  +0.3
  delay=+0.2 @ 30fps → d=+6 frames, so gaze[6:6+N] → placement[0:N]

Output layout
─────────────
  <batch_output_dir>/
    ablation_rows.jsonl          — one JSON object per completed job, appended atomically
    ablation_summary.csv         — aggregated at end of run (or via --aggregate-only)
    per_task/<ds>/<model>/<key>/
      report.json                — evaluator output
      stdout.log                 — captured stdout+stderr

Usage
─────
  # Dry-run: see what would run, no evaluator calls
  python3 test/launch/run_ablation_window_delay.py --dry-run \\
      --datasets 3dva --models A380 \\
      --delays -0.1 0.0 0.1 --window-modes cut_tail cut_head center

  # Historical start-crop + response-delay experiment:
  python3 test/launch/run_ablation_window_delay.py --dry-run \\
      --datasets 3dva --models A380 --window-modes cut_head \\
      --frame-offset-override 54 --delays 0.2

  # Real run — shard 0 on vg-gml01 (requires authorization):
  source configs/server_vg_gml01.env
  nice -n 18 ionice -c2 -n7 "$REPROJECT_PYTHON" test/launch/run_ablation_window_delay.py \\
      --workers 32 --shard-index 0 --num-shards 2 \\
      --batch-output-dir "$OUTPUT_ROOT/ablation_window_delay"

  # Real run — shard 1 on vg-gml02 (requires authorization):
  source configs/server_vg_gml02.env
  nice -n 18 ionice -c2 -n7 "$REPROJECT_PYTHON" test/launch/run_ablation_window_delay.py \\
      --workers 32 --shard-index 1 --num-shards 2 \\
      --batch-output-dir "$OUTPUT_ROOT/ablation_window_delay"

  # Aggregate JSONL → CSV after run completes:
  python3 test/launch/run_ablation_window_delay.py --aggregate-only \\
      --batch-output-dir "$OUTPUT_ROOT/ablation_window_delay"
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
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

# ── evaluator scripts ─────────────────────────────────────────────────────────

_EVAL: dict[str, dict[str, Path]] = {
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

_WINDOW_MODE_EVALUATOR_READY: frozenset[str] = frozenset({"cut_tail", "cut_head", "center"})

# ── timing / provenance contract (one_turn_from_start, offset0) ─────────────────
TIMING_CONTRACT = "one_turn_from_start"
FIXATION_DATA_TAG = "processed_fixations_offset0_full_cleaned"
# Environment-driven release tag so an rc4 ablation records correct provenance.
RELEASE_TAG = os.environ.get("REPROJECT_RELEASE_TAG", "v2.0-data-rc4")


def _frame_offset_for(dataset: str, window_mode: str) -> int:
    """Absolute frame offset the evaluator receives for a window mode."""
    info = _DATASET_FRAMES[dataset]
    tail = info["total_frames"] - info["turn_frames"]
    return {"cut_tail": 0, "cut_head": tail, "center": tail // 2}.get(window_mode, 0)


# ── canonical nested metric extraction (shared contract with sigma/full runner) ─

def extract_metrics(report: dict, dataset: str, method: str) -> "dict | None":
    """Descend into the method-keyed metric leaf, trying GT sections in order.

    SAL3D fixed-face GT lives at report["metrics_vs_fixed_face_gt"][method_key];
    a flat report.get("metrics_vs_fixed_face_gt")["CC"] lookup would miss it.
    """
    method_key = "screen_space_gaussian" if method == "screen_space" else "cone_gaussian_on_mesh"

    def _leaf(section, *keys):
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


def _select_report(task_out: Path) -> "Path | None":
    sidecars = {"provenance.json", "metrics_rows.json"}
    candidates = [p for p in sorted(task_out.rglob("*.json")) if p.name not in sidecars]
    if not candidates:
        return None
    preferred = [p for p in candidates if p.name.endswith("_report.json")]
    return preferred[0] if preferred else candidates[0]


def _provenance_mismatches(report: dict, *, frame_offset: int, delay_seconds: float) -> list[str]:
    """Required participant_input fields must be present and match THIS job's contract."""
    prov = report.get("participant_input")
    if not isinstance(prov, dict):
        return ["participant_input missing or not an object"]
    out: list[str] = []
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
            if int(fo) != frame_offset:
                out.append(f"frame_offset={fo!r}!={frame_offset}")
        except (TypeError, ValueError):
            out.append(f"frame_offset={fo!r} not an int")
    tag = prov.get("fixation_data_tag")
    if tag not in (None, "") and tag != FIXATION_DATA_TAG:
        out.append(f"fixation_data_tag={tag!r}!={FIXATION_DATA_TAG!r}")
    df = prov.get("delay_frames")
    fps = prov.get("fps")
    if df not in (None, "") and fps not in (None, ""):
        try:
            if int(df) != round(delay_seconds * float(fps)):
                out.append(f"delay_frames={df!r}!={round(delay_seconds * float(fps))}")
        except (TypeError, ValueError):
            out.append(f"delay_frames={df!r}/fps={fps!r} not numeric")
    return out

_SIGMA_DEFAULTS: dict[str, dict[str, dict[str, Any]]] = {
    "screen_space": {
        "3dva":                  {"sigma_px": 49.0},   # 1920x1080, ~1 deg visual angle
        "meshmamba_non_texture": {"sigma_screen": 0.05},
        "meshmamba_rgb_texture": {"sigma_screen": 0.05},
        "sal3d":                 {"sigma_px": 26.3},   # 1920x1080, 0.5 deg tracker accuracy
    },
    "cone": {
        "3dva":                  {"sigma_deg": 1.0, "radius_sigma_mult": 3.0},
        "meshmamba_non_texture": {"sigma_deg": 1.0, "radius_sigma_mult": 3.0},
        "meshmamba_rgb_texture": {"sigma_deg": 1.0, "radius_sigma_mult": 3.0},
        "sal3d":                 {"sigma_deg": 1.0, "radius_sigma_mult": 3.0},
    },
}

# ── CSV output schema ─────────────────────────────────────────────────────────

CSV_COLUMNS = [
    "job_key",
    "dataset", "model", "method", "window_mode", "delay_seconds", "frame_offset",
    "sigma_px", "sigma_screen", "sigma_deg", "radius_sigma_mult",
    "gaze_start_frame", "placement_start_frame", "turn_frames_used", "fps",
    "CC", "SIM", "KLD", "MSE", "AUC_Judd", "NSS",
    "report_path", "git_commit", "input_type",
    "release_tag", "timing_contract", "fixation_format", "fixation_data_tag",
    "status", "error_type", "error_message",
    "stdout_log_path", "elapsed_sec",
]

# ── job identity and sharding ─────────────────────────────────────────────────

@dataclass
class AblationJob:
    dataset: str
    model: str
    method: str
    window_mode: str
    delay_seconds: float
    frame_offset_override: int | None = None

    @property
    def sigma(self) -> dict[str, Any]:
        return _SIGMA_DEFAULTS[self.method][self.dataset]

    @property
    def sigma_string(self) -> str:
        return "_".join(f"{k}{v}" for k, v in sorted(self.sigma.items()))

    @property
    def frame_offset(self) -> int:
        if self.frame_offset_override is not None:
            return self.frame_offset_override
        return _frame_offset_for(self.dataset, self.window_mode)

    @property
    def key(self) -> str:
        # Identity embeds the timing/release/fixation contract and frame_offset so a
        # resume cannot collide jobs run under a different configuration.
        return (
            f"{RELEASE_TAG}:{TIMING_CONTRACT}:{FIXATION_DATA_TAG}:fo{self.frame_offset}:"
            f"{self.dataset}:{self.model}:{self.method}:"
            f"{self.window_mode}:{self.delay_seconds:.3f}:{self.sigma_string}"
        )

    def shard(self, num_shards: int) -> int:
        """Deterministic shard assignment via MD5 hash of job key."""
        digest = hashlib.md5(self.key.encode()).hexdigest()
        return int(digest, 16) % num_shards


def build_job_list(args: argparse.Namespace) -> list[AblationJob]:
    jobs: list[AblationJob] = []
    for dataset in args.datasets:
        models = _enumerate_models(dataset, args)
        for model in models:
            for method in args.methods:
                for wm in args.window_modes:
                    for delay in args.delays:
                        jobs.append(AblationJob(
                            dataset,
                            model,
                            method,
                            wm,
                            delay,
                            getattr(args, "frame_offset_override", None),
                        ))
    if args.num_shards > 1:
        jobs = [j for j in jobs if j.shard(args.num_shards) == args.shard_index]
    return jobs


def _enumerate_models(dataset: str, args: argparse.Namespace) -> list[str]:
    if args.model_list_file:
        text = Path(args.model_list_file).read_text()
        return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    if args.models:
        return list(args.models)
    ds_map = {
        "3dva": "3dva_models.json",
        "meshmamba_non_texture": "meshmamba_non_texture_models.json",
        "meshmamba_rgb_texture": "meshmamba_rgb_texture_models.json",
        "sal3d": "sal3d_models.json",
    }
    json_path = REPO_ROOT / "jsons" / "dataset_model_info" / ds_map[dataset]
    if not json_path.is_file():
        raise FileNotFoundError(f"model info JSON not found: {json_path}")
    data = json.loads(json_path.read_text())
    return [m["model"] for m in data["models"]]


# ── resume: load completed jobs from JSONL ────────────────────────────────────

def load_completed_keys(jsonl_path: Path) -> set[str]:
    """Return job keys from JSONL rows where status == 'ok'."""
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


# ── pairing description ───────────────────────────────────────────────────────

def describe_pairing(job: AblationJob) -> str:
    info = _DATASET_FRAMES[job.dataset]
    N = info["turn_frames"]
    fps = info["fps"]
    d = round(job.delay_seconds * fps)
    base = job.frame_offset
    gs = base + max(0, d)
    ps = base + max(0, -d)
    override = ", explicit_override" if job.frame_offset_override is not None else ""
    return (
        f"gaze[{gs}:{gs+N}] → placement[{ps}:{ps+N}]  "
        f"(frame_offset={base}{override}, d={job.delay_seconds:+.1f}s={d:+d}fr)"
    )


# ── per-job frame offset fields ───────────────────────────────────────────────

def frame_offsets(job: AblationJob) -> dict[str, int]:
    info = _DATASET_FRAMES[job.dataset]
    N = info["turn_frames"]
    fps = info["fps"]
    d = round(job.delay_seconds * fps)
    base = job.frame_offset
    return {
        "gaze_start_frame": base + max(0, d),
        "placement_start_frame": base + max(0, -d),
        "turn_frames_used": N,
        "fps": fps,
    }


def job_feasibility(job: AblationJob) -> tuple[bool, str]:
    """Return (feasible, reason). A job is infeasible when its window+delay would
    require frames outside [0, total_frames) for gaze or placement.

    Both gaze[gs:gs+N] and placement[ps:ps+N] must fit inside the available
    frames; negative starts or end indices past total_frames are rejected
    *before* the job is launched.
    """
    if job.window_mode not in ALL_WINDOW_MODES:
        return False, f"unknown window_mode={job.window_mode!r}"
    info = _DATASET_FRAMES[job.dataset]
    total = info["total_frames"]
    N = info["turn_frames"]
    off = frame_offsets(job)
    gs = off["gaze_start_frame"]
    ps = off["placement_start_frame"]
    if gs < 0 or ps < 0:
        return False, (
            f"negative window start (gaze_start={gs}, placement_start={ps}) "
            f"for {job.window_mode} d={job.delay_seconds:+.3f}"
        )
    if gs + N > total:
        return False, (
            f"gaze window [{gs}:{gs + N}] exceeds total_frames={total} "
            f"({job.dataset} {job.window_mode} d={job.delay_seconds:+.3f})"
        )
    if ps + N > total:
        return False, (
            f"placement window [{ps}:{ps + N}] exceeds total_frames={total} "
            f"({job.dataset} {job.window_mode} d={job.delay_seconds:+.3f})"
        )
    return True, ""


# ── command building ──────────────────────────────────────────────────────────

def build_command(job: AblationJob, args: argparse.Namespace) -> list[str]:
    script = _EVAL[job.dataset][job.method]
    python = os.environ.get("REPROJECT_PYTHON", sys.executable)
    cmd = [python, str(script), "--model", job.model]
    cmd += ["--timing-contract", TIMING_CONTRACT, "--delay-seconds", str(job.delay_seconds)]
    cmd += ["--frame-offset", str(job.frame_offset)]

    fixation_root = getattr(args, "fixation_root", None) or _env_first(
        "FIXATION_ROOT", "REPROJECT_PROCESSED_FIXATIONS_ROOT"
    )
    if fixation_root:
        cmd += ["--fixation-root", str(fixation_root)]
    # Canonical, single-sourced provenance tag (matches the full-run launcher).
    cmd += ["--fixation-data-tag", FIXATION_DATA_TAG]

    # Env → evaluator flags, mirroring run_full_metrics_optimized_sigma.build_command.
    # The evaluators accept --json-root / --dataset-root / --combined-gt-dir /
    # --fixed-gt-dir / --smooth-gaze-dir / --sal3d-manifest — NOT --obj-root/--gt-root.
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
            "SAL3D_JSON_ROOT":       "--json-root",
            "SAL3D_DATASET_ROOT":    "--dataset-root",
            "SAL3D_FIXED_GT_DIR":    "--fixed-gt-dir",
            "SAL3D_SMOOTH_GAZE_DIR": "--smooth-gaze-dir",
            "SAL3D_MANIFEST":        "--sal3d-manifest",
        })

    sigma = job.sigma
    if job.method == "screen_space":
        if "sigma_px" in sigma:
            cmd += ["--sigma-px", str(sigma["sigma_px"])]
        elif "sigma_screen" in sigma:
            cmd += ["--sigma-screen", str(sigma["sigma_screen"])]
    elif job.method == "cone":
        cmd += ["--sigma-deg", str(sigma["sigma_deg"]),
                "--radius-sigma-mult", str(sigma["radius_sigma_mult"])]

    task_out = _task_output_dir(job, args)
    cmd += ["--output-dir", str(task_out)]
    delay_tag = (
        f"wm{job.window_mode}_fo{job.frame_offset}_d{job.delay_seconds:+.3f}"
        .replace("+", "p").replace("-", "m").replace(".", "")
    )
    cmd += ["--tag", f"ablation_{delay_tag}"]
    return cmd


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


def _task_output_dir(job: AblationJob, args: argparse.Namespace) -> Path:
    d_str = f"d{job.delay_seconds:+.3f}".replace("+", "p").replace("-", "m").replace(".", "")
    return (
        Path(args.batch_output_dir)
        / "per_task"
        / job.dataset
        / job.model
        / f"{job.method}_wm{job.window_mode}_fo{job.frame_offset}_{d_str}"
    )


# ── job execution ─────────────────────────────────────────────────────────────

def execute_job(job: AblationJob, args: argparse.Namespace) -> dict[str, Any]:
    """Run one job and return a fully-populated row dict."""
    row: dict[str, Any] = {col: "" for col in CSV_COLUMNS}
    row.update({
        "job_key": job.key,
        "dataset": job.dataset, "model": job.model,
        "method": job.method, "window_mode": job.window_mode,
        "delay_seconds": job.delay_seconds,
        "frame_offset": job.frame_offset,
        "release_tag": RELEASE_TAG,
        "timing_contract": TIMING_CONTRACT,
        "fixation_data_tag": FIXATION_DATA_TAG,
    })
    row.update(job.sigma)
    row.update(frame_offsets(job))

    # Not yet supported window modes
    if job.window_mode not in _WINDOW_MODE_EVALUATOR_READY:
        row["status"] = "skipped"
        row["error_type"] = "window_mode_not_implemented"
        row["error_message"] = (
            f"window_mode={job.window_mode!r} requires --window-mode evaluator flag "
            f"(not yet implemented). Pairing: {describe_pairing(job)}"
        )
        return row

    cmd = build_command(job, args)
    task_out = _task_output_dir(job, args)
    task_out.mkdir(parents=True, exist_ok=True)
    log_path = task_out / "stdout.log"
    row["stdout_log_path"] = str(log_path)

    if args.dry_run:
        row["status"] = "ok"
        row["error_type"] = "dry_run"
        row["error_message"] = " ".join(cmd)
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

    report_path = _select_report(task_out)
    if report_path is None:
        row["status"] = "failed"
        row["error_type"] = "missing_report"
        return row

    row["report_path"] = str(report_path)
    try:
        report = json.loads(report_path.read_text())
    except Exception as exc:
        row["status"] = "failed"
        row["error_type"] = "report_parse_error"
        row["error_message"] = str(exc)
        return row

    prov_problems = _provenance_mismatches(
        report, frame_offset=job.frame_offset, delay_seconds=job.delay_seconds)
    if prov_problems:
        row["status"] = "failed"
        row["error_type"] = "provenance_mismatch"
        row["error_message"] = "; ".join(prov_problems)
        return row

    metrics = extract_metrics(report, job.dataset, job.method) or {}
    for metric in ("CC", "SIM", "KLD", "MSE", "AUC_Judd", "NSS"):
        row[metric] = metrics.get(metric, "")
    if not row["NSS"]:
        row["NSS"] = metrics.get("NSS_gt_top_10pct_proxy", "")
    if not row["AUC_Judd"]:
        row["AUC_Judd"] = metrics.get("AUC_Judd_gt_top_10pct_proxy", "")

    prov = report.get("participant_input", {})
    row["input_type"] = prov.get("input_mode", "")
    row["fixation_format"] = prov.get("fixation_format", "")
    row["fixation_data_tag"] = prov.get("fixation_data_tag", "")
    row["git_commit"] = report.get("git_commit", "")
    row["status"] = "ok"
    return row


# ── thread-safe JSONL writer ──────────────────────────────────────────────────

class _JsonlWriter:
    """Appends one JSON row per line under a lock (safe for multi-threaded use)."""

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
    """Read ablation_rows.jsonl and write ablation_summary.csv."""
    jsonl_path = batch_dir / "ablation_rows.jsonl"
    csv_path = batch_dir / "ablation_summary.csv"
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
    rows.sort(key=lambda r: (r.get("dataset", ""), r.get("model", ""), r.get("method", ""),
                              r.get("window_mode", ""), r.get("delay_seconds", 0.0)))
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in CSV_COLUMNS})
    return csv_path


# ── argument parsing ──────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Window/delay ablation runner (global job pool). DO NOT RUN without approval.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--datasets", nargs="+", default=ALL_DATASETS, choices=ALL_DATASETS)
    parser.add_argument("--methods", nargs="+", default=ALL_METHODS, choices=ALL_METHODS)
    parser.add_argument(
        "--window-modes", nargs="+", default=["cut_tail"], choices=ALL_WINDOW_MODES,
        help="Window label used to derive frame offset: cut_tail=0, center=30, cut_head=60.",
    )
    parser.add_argument(
        "--frame-offset-override",
        type=int,
        default=None,
        metavar="FRAMES",
        help=(
            "Explicitly replace the offset derived from --window-modes. "
            "Example: 54 with --delays 0.2 pairs gaze[60:] with placement[54:]."
        ),
    )
    parser.add_argument("--delays", nargs="+", type=float, default=ALL_DELAYS, metavar="SEC")
    parser.add_argument("--models", nargs="+", default=None)
    parser.add_argument("--model-list-file", type=Path, default=None, metavar="FILE")
    parser.add_argument("--fixation-root", type=Path, default=None)
    parser.add_argument(
        "--batch-output-dir",
        type=Path,
        default=REPO_ROOT / "results" / "ablation_window_delay",
    )
    parser.add_argument("--workers", type=int, default=4,
                        help="Number of parallel worker slots (--workers 32 for server).")
    parser.add_argument("--shard-index", type=int, default=0, metavar="I",
                        help="Zero-based shard index (0 on vg-gml01, 1 on vg-gml02).")
    parser.add_argument("--num-shards", type=int, default=1, metavar="N",
                        help="Total shards. Sharding uses MD5 hash of job key.")
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    parser.add_argument("--dry-run", action="store_true",
                        help="Log commands without executing evaluators. JSONL status=ok with error_type=dry_run.")
    parser.add_argument("--aggregate-only", action="store_true",
                        help="Read existing ablation_rows.jsonl and write ablation_summary.csv, then exit.")
    return parser.parse_args()


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    args = parse_args()
    batch_dir = Path(args.batch_output_dir)
    batch_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = batch_dir / "ablation_rows.jsonl"

    if args.aggregate_only:
        csv_path = aggregate_csv(batch_dir)
        print(f"[ablation] aggregated → {csv_path}")
        return 0

    jobs = build_job_list(args)
    completed_keys = load_completed_keys(jsonl_path)
    writer = _JsonlWriter(jsonl_path)

    # Reject window/delay combinations that cannot fit in the available frames
    # BEFORE launching anything.  Infeasible jobs are recorded (status=rejected)
    # with a reason and never invoke the evaluator.
    infeasible = 0
    pending: list[AblationJob] = []
    for job in jobs:
        feasible, reason = job_feasibility(job)
        if not feasible:
            infeasible += 1
            row = {col: "" for col in CSV_COLUMNS}
            row.update({
                "job_key": job.key,
                "dataset": job.dataset, "model": job.model,
                "method": job.method, "window_mode": job.window_mode,
                "delay_seconds": job.delay_seconds,
                "frame_offset": job.frame_offset,
                "status": "rejected",
                "error_type": "infeasible_window_delay",
                "error_message": reason,
            })
            row.update(frame_offsets(job))
            writer.append(row)
            print(f"[ablation] REJECT (infeasible): {job.dataset}/{job.model}/{job.method} "
                  f"wm={job.window_mode} d={job.delay_seconds:+.1f} — {reason}", flush=True)
            continue
        if job.key in completed_keys:
            print(f"[ablation] resume-skip: {job.dataset}/{job.model}/{job.method} wm={job.window_mode} d={job.delay_seconds:+.1f}", flush=True)
        else:
            pending.append(job)

    total = len(jobs)
    skipped_resume = total - len(pending) - infeasible
    print(f"[ablation] jobs: {total} total, {infeasible} rejected-infeasible, "
          f"{skipped_resume} resume-skipped, {len(pending)} to run", flush=True)
    print(f"[ablation] workers: {args.workers}  shards: {args.num_shards}  shard_index: {args.shard_index}", flush=True)
    print(f"[ablation] output: {batch_dir}", flush=True)

    if args.dry_run:
        print(f"[ablation] DRY RUN — no evaluator calls", flush=True)
        for job in pending[:3]:
            if job.window_mode in _WINDOW_MODE_EVALUATOR_READY:
                cmd = build_command(job, args)
                print(f"  {job.dataset}/{job.model}/{job.method} wm={job.window_mode} d={job.delay_seconds:+.1f}")
                print(f"    pairing: {describe_pairing(job)}")
                print(f"    cmd: {' '.join(cmd)}")
            else:
                print(f"  {job.dataset}/{job.model}/{job.method} wm={job.window_mode} d={job.delay_seconds:+.1f} → skipped (not implemented)")
        if len(pending) > 3:
            print(f"  ... and {len(pending) - 3} more")
        print()

    done = 0
    ok = 0
    failed = 0
    skipped_wm = 0

    def _run(job: AblationJob) -> dict[str, Any]:
        return execute_job(job, args)

    if args.workers <= 1 or args.dry_run:
        for job in pending:
            row = execute_job(job, args)
            writer.append(row)
            done += 1
            if row["status"] == "ok":
                ok += 1
            elif row["status"] == "skipped":
                skipped_wm += 1
            else:
                failed += 1
            if not args.dry_run or job.window_mode in _WINDOW_MODE_EVALUATOR_READY:
                print(
                    f"[ablation] {done}/{len(pending)} {job.dataset}/{job.model}/{job.method}"
                    f" wm={job.window_mode} d={job.delay_seconds:+.1f} → {row['status']}",
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
                        "job_key": job.key,
                        "dataset": job.dataset, "model": job.model,
                        "method": job.method, "window_mode": job.window_mode,
                        "delay_seconds": job.delay_seconds,
                        "status": "runtime_error",
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    })
                writer.append(row)
                done += 1
                if row["status"] == "ok":
                    ok += 1
                elif row["status"] == "skipped":
                    skipped_wm += 1
                else:
                    failed += 1
                print(
                    f"[ablation] {done}/{len(pending)} {job.dataset}/{job.model}/{job.method}"
                    f" wm={job.window_mode} d={job.delay_seconds:+.1f} → {row['status']}",
                    flush=True,
                )

    print(f"[ablation] done: ok={ok} skipped={skipped_wm} failed={failed} resume_skipped={skipped_resume}", flush=True)

    try:
        csv_path = aggregate_csv(batch_dir)
        print(f"[ablation] aggregated → {csv_path}", flush=True)
    except Exception as exc:
        print(f"[ablation] aggregation failed: {exc}", flush=True)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
