"""Bridge: ingest an accepted reference *long* CSV into the ablation aggregation layer.

NON-DESTRUCTIVE. This reads an existing per-model long-metrics CSV (the schema the
reference / full-metrics runners already emit, e.g. the rc3 baseline
`*_reference_long.csv` / `3dva_combined_long.csv`) and feeds its rows through
`ablation_aggregation.record_run(...)` to produce one real per-run / aggregate
layout. It imports/modifies no baseline evaluator or launcher.

It only maps SOURCE fields it can see:
  - per-model: `model`, `status`, the 14-metric block (proxy names renamed by the
    aggregation layer);
  - run-level provenance present in the source: `gt_domain`, `gt_match_type`,
    `projection_fov_mode`.
Run metadata not present in the long CSV (sigma, timing) is supplied by the caller
via `extra` / CLI flags and recorded as such (e.g. sigma comes from
`docs/METRIC_RUN_AND_CSV_CONTRACT.md`, not from the source rows).

Usage:
    python3 test/launch/import_reference_long.py \
      --source-csv results/csv/rc3_baseline/benchmark_runs/rc3_full_metrics_20260611_004003/csv_only/sal3d_reference_long.csv \
      --dataset sal3d --method cone --stage reference_rc3_baseline \
      --sigma-deg 1.0 --radius-sigma-mult 3.0 --results-root results
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import subprocess
from pathlib import Path

_AGG_PATH = Path(__file__).resolve().parent / "ablation_aggregation.py"
_spec = importlib.util.spec_from_file_location("ablation_aggregation", _AGG_PATH)
agg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(agg)

CORE_SOURCE_METRICS = ("CC", "SIM", "KLD", "MSE", "MAE", "Spearman", "Cosine")
PROXY_SOURCE_METRICS = (
    "AUC_Judd_gt_top_10pct_proxy", "AUC_Judd_gt_top_5pct_proxy",
    "AUC_Judd_gt_top_1pct_proxy", "NSS_gt_top_10pct_proxy",
    "NSS_gt_top_5pct_proxy", "NSS_gt_top_1pct_proxy",
)
# Fields the source long CSV MUST contain to be a valid 14-metric reference source.
REQUIRED_SOURCE_FIELDS = ("model", "method", "status", *CORE_SOURCE_METRICS, *PROXY_SOURCE_METRICS)

# Provenance fields mapped straight through when present in the source.
PASSTHROUGH_PROVENANCE = ("gt_domain", "gt_match_type", "projection_fov_mode")

# One full turn per dataset (docs/METRIC_RUN_AND_CSV_CONTRACT.md).
TURN_FRAMES = {"3dva": 450, "meshmamba_non_texture": 450,
               "meshmamba_rgb_texture": 450, "sal3d": 660}


def load_reference_long(csv_path: Path, *, method: str, texture_type: str | None = None) -> list[dict]:
    """Read the long CSV, validate the required-field schema, and return the rows
    for one (method[, texture_type]). Raises ValueError on a schema/empty mismatch.

    Strict validation (no silent data loss):
    - `hit_rate` is required for `cone` imports (it is a ray/cone hit statistic and
      must not be silently dropped); `screen_space` legitimately may lack it.
    - if `texture_type` is requested but the source has no `texture_type` column,
      raise rather than silently returning unscoped, mixed-track rows.
    """
    csv_path = Path(csv_path)
    with csv_path.open() as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        required = list(REQUIRED_SOURCE_FIELDS)
        if method == "cone":
            required.append("hit_rate")
        missing = [f for f in required if f not in fieldnames]
        if missing:
            raise ValueError(
                f"{csv_path}: missing required source fields for method={method!r}: {missing}")
        rows = list(reader)

    has_texture = "texture_type" in fieldnames
    if texture_type is not None and not has_texture:
        raise ValueError(
            f"{csv_path}: texture_type={texture_type!r} requested but the source has no "
            "'texture_type' column; cannot scope the import to one track")

    selected = []
    for r in rows:
        if r.get("method") != method:
            continue
        if texture_type is not None and r.get("texture_type") != texture_type:
            continue
        selected.append(r)
    if not selected:
        raise ValueError(
            f"{csv_path}: no rows for method={method!r} texture_type={texture_type!r}")
    return selected


def _consistent_ok_value(rows: list[dict], key: str) -> tuple[str, bool]:
    """The single value of `key` across status-ok rows, or ('mixed'/'' , True)."""
    values = {r.get(key) for r in rows if r.get("status") == "ok" and r.get(key) not in (None, "")}
    if len(values) == 1:
        return str(next(iter(values))), False
    if not values:
        return "", False
    return "mixed", True


def build_reference_params(source_csv: Path, rows: list[dict], *, dataset: str, method: str,
                           stage: str, texture_type: str = "", extra: dict | None = None) -> dict:
    """Assemble run-level params from source-derived provenance + caller metadata."""
    command = (f"python3 test/launch/import_reference_long.py --source-csv {source_csv} "
               f"--dataset {dataset} --method {method} --stage {stage}"
               + (f" --texture-type {texture_type}" if texture_type else ""))
    params: dict = {
        "stage_name": stage, "dataset": dataset, "method": method,
        "texture_type": texture_type, "timing_contract": "one_turn_from_start",
        "window_mode": "one_turn_from_start", "frame_offset": 0, "delay_seconds": 0.0,
        "delay_frames": 0, "gaze_start_frame": 0, "placement_start_frame": 0,
        "turn_frame_count": TURN_FRAMES.get(dataset, ""),
        "model_subset_name": f"{dataset}_{method}_reference_ok",
        "command": command,
        "notes": f"imported from accepted reference long CSV: {source_csv}",
    }
    for key in PASSTHROUGH_PROVENANCE:
        if any(key in r for r in rows):
            value, mixed = _consistent_ok_value(rows, key)
            params[key] = value
            if mixed:
                params["notes"] += f"; {key} mixed across models"
    if extra:
        params.update({k: v for k, v in extra.items() if v not in (None, "")})
    return params


def import_reference_run(source_csv: Path, results_root: Path, *, dataset: str, method: str,
                         stage: str, texture_type: str | None = None, extra: dict | None = None,
                         run_id: str | None = None, on_duplicate: str = "error") -> Path:
    rows = load_reference_long(source_csv, method=method, texture_type=texture_type)
    params = build_reference_params(source_csv, rows, dataset=dataset, method=method,
                                    stage=stage, texture_type=texture_type or "", extra=extra)
    return agg.record_run(results_root, params, rows, run_id=run_id, command=params["command"],
                          stdout_text=f"imported {len(rows)} per-model rows from {source_csv}\n",
                          on_duplicate=on_duplicate)


def _git(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=_AGG_PATH.parents[2],
                                       stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return ""


def main() -> int:
    ap = argparse.ArgumentParser(description="Import an accepted reference long CSV into the ablation layer.")
    ap.add_argument("--source-csv", type=Path, required=True)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--method", required=True, choices=["cone", "screen_space"])
    ap.add_argument("--stage", default="reference_rc3_baseline")
    ap.add_argument("--results-root", type=Path, default=Path("results"))
    ap.add_argument("--texture-type", default=None)
    ap.add_argument("--sigma-deg", default="")
    ap.add_argument("--sigma-px", default="")
    ap.add_argument("--sigma-screen", default="")
    ap.add_argument("--radius-sigma-mult", default="")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--on-duplicate", default="error", choices=["error", "supersede", "allow"])
    args = ap.parse_args()

    extra = {
        "sigma_deg": args.sigma_deg, "sigma_px": args.sigma_px,
        "sigma_screen": args.sigma_screen, "radius_sigma_mult": args.radius_sigma_mult,
        "repo_commit": _git("rev-parse", "HEAD"), "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
    }
    if any(extra[k] for k in ("sigma_deg", "sigma_px", "sigma_screen", "radius_sigma_mult")):
        extra["notes_sigma"] = "sigma from docs/METRIC_RUN_AND_CSV_CONTRACT.md baseline (not in source long CSV)"

    run_dir = import_reference_run(
        args.source_csv, args.results_root, dataset=args.dataset, method=args.method,
        stage=args.stage, texture_type=args.texture_type, extra=extra,
        run_id=args.run_id, on_duplicate=args.on_duplicate)
    print(f"[import] wrote {run_dir}")
    print(f"[import] aggregate: {run_dir.parents[1] / 'aggregate' / 'ablation_runs.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
