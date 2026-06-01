#!/usr/bin/env python3
"""
Run screen_space v1 and v2 on one model and print a side-by-side metrics table.

Usage (on vg-intellect, after sourcing configs/server_vg_intellect.env):

  source configs/server_vg_intellect.env
  $REPROJECT_PYTHON trash/compare_v1_v2_screenspace.py \
      --model Rubber_Duck_v1_L3 \
      --texture-type non_texture

All dataset paths are read from env vars set by server_vg_intellect.env.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
V1 = REPO_ROOT / "reprojection_methods" / "screen_space_gaussian" / "eval_meshmamba_screen_space.py"
V2 = REPO_ROOT / "reprojection_methods" / "screen_space_gaussian" / "eval_meshmamba_screen_space_v2.py"

METRICS = ["CC", "Spearman", "SIM", "KLD", "NSS_gt_top_10pct_proxy", "AUC_Judd_gt_top_10pct_proxy"]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="Rubber_Duck_v1_L3")
    p.add_argument("--texture-type", default="non_texture")
    p.add_argument("--python", default=os.environ.get("REPROJECT_PYTHON", sys.executable))
    return p.parse_args()


def env_path(key: str) -> str:
    v = os.environ.get(key, "")
    if not v:
        raise SystemExit(f"Env var {key} not set. Did you source configs/server_vg_intellect.env?")
    return v


def run_version(label: str, script: Path, extra_args: list[str], output_dir: Path, model: str) -> dict:
    cmd = [
        args.python, str(script),
        "--model", model,
        "--texture-type", args.texture_type,
        "--dataset-root", env_path("MESHMAMBA_NON_TEXTURE_ROOT" if args.texture_type == "non_texture" else "MESHMAMBA_RGB_TEXTURE_ROOT"),
        "--csv-root",     env_path("MESHMAMBA_CSV_ROOT" if args.texture_type == "non_texture" else "MESHMAMBA_RGB_TEXTURE_CSV_ROOT"),
        "--json-root",    env_path("MESHMAMBA_JSON_ROOT" if args.texture_type == "non_texture" else "MESHMAMBA_RGB_TEXTURE_JSON_ROOT"),
        "--output-dir",   str(output_dir),
        "--recenter-to-bbox-center",
        "--extra-rotate-x-deg", "90",
        "--projection-fov-mode", "horizontal_to_vertical",
        "--transform-order", "blender_rig",
    ] + extra_args

    print(f"\n{'='*60}")
    print(f"  Running {label} ...")
    print(f"  {' '.join(cmd)}")
    print(f"{'='*60}")

    result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=False, text=True)
    if result.returncode != 0:
        raise SystemExit(f"{label} failed with exit code {result.returncode}")

    # Find the report JSON written by the script
    report_files = sorted(output_dir.rglob(f"{model}_report.json"))
    if not report_files:
        raise SystemExit(f"No report JSON found under {output_dir}")
    return json.loads(report_files[-1].read_text(encoding="utf-8"))


def extract_metrics(report: dict) -> dict[str, float]:
    for key in ("screen_space_gaussian",):
        metrics = report.get("metrics_vs_gt", {}).get(key, {})
        if metrics:
            return metrics
    return {}


def print_table(model: str, texture_type: str, m1: dict, m2: dict) -> None:
    print(f"\n{'='*65}")
    print(f"  Model: {model}  |  Texture: {texture_type}")
    print(f"  v1: sigma_screen=0.05 → 12.8px @ 256×144")
    print(f"  v2: sigma_px=26.3    → 26.3px @ 1920×1080  (bilinear deposition)")
    print(f"{'='*65}")
    print(f"  {'Metric':<35} {'v1':>10} {'v2':>10} {'Δ':>10}")
    print(f"  {'-'*63}")
    for m in METRICS:
        v1 = m1.get(m)
        v2 = m2.get(m)
        if v1 is None or v2 is None:
            print(f"  {m:<35} {'N/A':>10} {'N/A':>10}")
            continue
        delta = v2 - v1
        sign = "+" if delta >= 0 else ""
        print(f"  {m:<35} {v1:>10.4f} {v2:>10.4f} {sign}{delta:>9.4f}")
    print()


if __name__ == "__main__":
    args = parse_args()

    with tempfile.TemporaryDirectory(prefix="ss_compare_") as tmpdir:
        out_v1 = Path(tmpdir) / "v1"
        out_v2 = Path(tmpdir) / "v2"

        report_v1 = run_version("v1 (original)", V1, ["--sigma-screen", "0.05"], out_v1, args.model)
        report_v2 = run_version("v2 (corrected)", V2, ["--sigma-px", "26.3"],    out_v2, args.model)

    m1 = extract_metrics(report_v1)
    m2 = extract_metrics(report_v2)
    print_table(args.model, args.texture_type, m1, m2)
