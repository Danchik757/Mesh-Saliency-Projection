#!/usr/bin/env python3
"""
Export metric JSON outputs to flat CSV rows for spreadsheets/tables.

Supported inputs:
1. 3DVA report JSONs:
   .../<model>/<tag>/<model>_report.json
2. MeshMamba baseline report JSONs:
   .../<model>/<tag>/<model>_report.json
3. MAMBA_GAZE outputs:
   .../<model>/metrics_vs_gt.json + sibling run_summary.json

Typical usage:
  python3 test/tools/export_metrics_csv.py \
      --input /path/to/outputs/3DVA/raycast_cone \
      --input /path/to/outputs/MeshMamba_non_texture/baseline_screen_space \
      --input /path/to/outputs/MeshMamba_non_texture/baseline_cone \
      --input /path/to/outputs/MeshMamba_non_texture/pilot \
      --output-csv /path/to/outputs/metrics_summary.csv
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Flatten metric JSON outputs into a single CSV.")
    parser.add_argument(
        "--input",
        dest="inputs",
        action="append",
        required=True,
        help="Input file or directory. Can be repeated.",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        required=True,
        help="Path to the output CSV file.",
    )
    return parser.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_candidate_jsons(path: Path) -> list[Path]:
    if path.is_file() and path.suffix == ".json":
        return [path]
    if not path.is_dir():
        return []
    candidates = []
    candidates.extend(sorted(path.rglob("*_report.json")))
    candidates.extend(sorted(path.rglob("metrics_vs_gt.json")))
    return candidates


def _scalar_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in metrics.items() if isinstance(v, (int, float, str, bool)) or v is None}


def _flatten_3dva_report(path: Path, payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for method_name, gt_views in payload.get("metrics_vs_gt", {}).items():
        for gt_view, metrics in gt_views.items():
            row = {
                "source_file": str(path),
                "source_type": "3dva_report",
                "dataset": payload.get("dataset", "3DVA"),
                "model": payload.get("model"),
                "tag": payload.get("tag"),
                "method": method_name,
                "variant": "",
                "gt_view": str(gt_view),
            }
            row.update(_scalar_metrics(metrics))
            rows.append(row)
    return rows


def _flatten_meshmamba_baseline_report(path: Path, payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for method_name, metrics in payload.get("metrics_vs_gt", {}).items():
        row = {
            "source_file": str(path),
            "source_type": "meshmamba_baseline_report",
            "dataset": payload.get("dataset", "MeshMamba_non_texture"),
            "model": payload.get("model"),
            "tag": payload.get("tag"),
            "method": method_name,
            "variant": "",
            "gt_view": "",
        }
        row.update(_scalar_metrics(metrics))
        rows.append(row)
    return rows


def _infer_mamba_method_label(run_summary: dict[str, Any]) -> str:
    runtime_cfg = run_summary.get("runtime_config", {})
    smoothing_mode = runtime_cfg.get("smoothing_mode", "")
    if smoothing_mode == "none":
        return "our_pipeline"
    if smoothing_mode:
        return f"our_pipeline+{smoothing_mode}"
    return "our_pipeline"


def _flatten_mamba_metrics(path: Path, payload: dict[str, Any]) -> list[dict[str, Any]]:
    run_summary_path = path.with_name("run_summary.json")
    if not run_summary_path.exists():
        return []
    run_summary = _load_json(run_summary_path)
    method_label = _infer_mamba_method_label(run_summary)
    model = run_summary.get("model")
    dataset = "MeshMamba_non_texture"
    gt_path = run_summary.get("resolved_paths", {}).get("gt_path", "")
    if "rgb_texture" in str(gt_path):
        dataset = "MeshMamba_rgb_texture"

    rows: list[dict[str, Any]] = []
    for variant, metrics in payload.items():
        if not isinstance(metrics, dict):
            continue
        row = {
            "source_file": str(path),
            "source_type": "mamba_gaze_metrics",
            "dataset": dataset,
            "model": model,
            "tag": "",
            "method": method_label,
            "variant": variant,
            "gt_view": "",
        }
        row.update(_scalar_metrics(metrics))
        rows.append(row)
    return rows


def flatten_json(path: Path) -> list[dict[str, Any]]:
    payload = _load_json(path)
    if path.name == "metrics_vs_gt.json":
        return _flatten_mamba_metrics(path, payload)

    dataset = payload.get("dataset")
    if dataset == "3DVA":
        return _flatten_3dva_report(path, payload)
    if dataset and dataset.startswith("MeshMamba"):
        return _flatten_meshmamba_baseline_report(path, payload)
    return []


def main() -> None:
    args = parse_args()
    rows: list[dict[str, Any]] = []
    seen: set[Path] = set()

    for input_value in args.inputs:
        input_path = Path(input_value).expanduser()
        for json_path in _iter_candidate_jsons(input_path):
            json_path = json_path.resolve()
            if json_path in seen:
                continue
            seen.add(json_path)
            rows.extend(flatten_json(json_path))

    if not rows:
        raise SystemExit("No supported metric JSON files found.")

    fixed_prefix = ["dataset", "model", "tag", "method", "variant", "gt_view", "source_type", "source_file"]
    metric_keys = sorted({k for row in rows for k in row.keys() if k not in fixed_prefix})
    fieldnames = fixed_prefix + metric_keys

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})

    print(f"Saved CSV: {args.output_csv}")
    print(f"Rows: {len(rows)}")


if __name__ == "__main__":
    main()
