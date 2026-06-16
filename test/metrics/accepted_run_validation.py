"""Read-only validation of an accepted compact CSV against its own long CSVs.

Stage-1 task: confirm that the accepted compact ``*_summary_all_metrics.csv`` is
reproducible by re-aggregating (mean over status==ok models) the per-model long
CSVs for the SAME run, on a common model set. This validates the
compact-from-long extraction/rename path WITHOUT re-running any evaluator and
WITHOUT touching baseline code or servers.

It does NOT recompute metrics from raw meshes/gaze (that would need data + heavy
compute). It also does NOT decide which KLD is authoritative: the ``KLD`` column
here is the *evaluator KLD (current benchmark output)*; the *trusted-module KLD
(mathematical reference)* differs by preprocessing and is characterised
separately in ``test/metrics/test_evaluator_metric_parity.py``.

Usage:
    python3 test/metrics/accepted_run_validation.py \
        --run-dir results/csv/rc3_baseline/benchmark_runs/rc3_full_metrics_20260611_004003 \
        --out-csv /path/to/artifact.csv
"""
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

# Compact contract metric order (docs/METRIC_RUN_AND_CSV_CONTRACT.md).
COMPACT_METRICS = (
    "CC", "SIM", "KLD", "MSE", "MAE", "Spearman", "Cosine",
    "AUC_at_10pct", "AUC_at_5pct", "AUC_at_1pct",
    "NSS_at_10pct", "NSS_at_5pct", "NSS_at_1pct", "hit_rate",
)

# Compact column -> internal long-CSV column. The proxy AUC/NSS are renamed by the
# launchers; the rest share names.
COMPACT_TO_LONG = {
    "AUC_at_10pct": "AUC_Judd_gt_top_10pct_proxy",
    "AUC_at_5pct": "AUC_Judd_gt_top_5pct_proxy",
    "AUC_at_1pct": "AUC_Judd_gt_top_1pct_proxy",
    "NSS_at_10pct": "NSS_gt_top_10pct_proxy",
    "NSS_at_5pct": "NSS_gt_top_5pct_proxy",
    "NSS_at_1pct": "NSS_gt_top_1pct_proxy",
}

# Long file -> function mapping a row to its compact dataset_track value.
LONG_FILES = {
    "3dva_combined_long.csv": lambda r: "3dva",
    "meshmamba_reference_long.csv": lambda r: f"meshmamba_{r['texture_type']}",
    "sal3d_reference_long.csv": lambda r: "sal3d",
}

ROUNDING_TOL = 5e-5  # compact is rounded to 4 dp -> |round(mean,4) - mean| <= 5e-5


def _to_float(value: str):
    if value is None:
        return None
    value = value.strip()
    if value == "" or value.lower() == "nan":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def load_ok_rows(run_dir: Path) -> list[dict]:
    rows: list[dict] = []
    for fname, track_fn in LONG_FILES.items():
        path = run_dir / "csv_only" / fname
        with path.open() as fh:
            for r in csv.DictReader(fh):
                if r.get("status") != "ok":
                    continue
                r["_dataset_track"] = track_fn(r)
                rows.append(r)
    return rows


def recompute_compact(ok_rows: list[dict]) -> dict[tuple[str, str], dict]:
    """Mean of each compact metric over status==ok rows, keyed by (track, method)."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in ok_rows:
        groups.setdefault((r["_dataset_track"], r["method"]), []).append(r)

    out: dict[tuple[str, str], dict] = {}
    for key, group in groups.items():
        rec = {"model_count_used": len(group)}
        for metric in COMPACT_METRICS:
            col = COMPACT_TO_LONG.get(metric, metric)
            vals = [v for v in (_to_float(row.get(col, "")) for row in group) if v is not None]
            rec[metric] = (sum(vals) / len(vals)) if vals else None
        out[key] = rec
    return out


def load_accepted_compact(summary_csv: Path) -> dict[tuple[str, str], dict]:
    out: dict[tuple[str, str], dict] = {}
    with summary_csv.open() as fh:
        for r in csv.DictReader(fh):
            key = (r["dataset_track"], r["method"])
            out[key] = {m: _to_float(r.get(m, "")) for m in COMPACT_METRICS}
            out[key]["n_ok"] = _to_float(r.get("n_ok", ""))
    return out


def _explain(metric: str, method: str, accepted, recomputed, delta) -> str:
    if metric == "hit_rate" and method == "screen_space":
        return "n/a: screen_space has no ray/cone hit stage (blank by contract)"
    if accepted is None and recomputed is None:
        return "both empty (n/a)"
    if accepted is None or recomputed is None:
        return "PROVENANCE/EXTRACTION: value present on only one side"
    if delta <= ROUNDING_TOL:
        base = "float-noise only (compact rounded to 4dp)"
    else:
        base = "MISMATCH > rounding: investigate extraction/provenance"
    if metric == "KLD":
        base += " | label=evaluator KLD (current benchmark output); trusted-module KLD is the mathematical reference"
    return base


def build_diff(run_dir: Path) -> list[dict]:
    ok_rows = load_ok_rows(run_dir)
    recomputed = recompute_compact(ok_rows)
    accepted = load_accepted_compact(run_dir.parent / f"{run_dir.name}_summary_all_metrics.csv")

    diff: list[dict] = []
    for key in accepted:
        track, method = key
        rec = recomputed.get(key, {})
        for metric in COMPACT_METRICS:
            a = accepted[key].get(metric)
            r = rec.get(metric)
            delta = abs(a - r) if (a is not None and r is not None) else None
            diff.append({
                "dataset_track": track,
                "method": method,
                "metric": metric,
                "model_count_used": rec.get("model_count_used", 0),
                "accepted_value": "" if a is None else f"{a:.6f}",
                "recomputed_value": "" if r is None else f"{r:.6f}",
                "absolute_delta": "" if delta is None else f"{delta:.2e}",
                "explanation": _explain(metric, method, a, r, delta),
            })
    return diff


def main() -> None:
    repo = Path(__file__).resolve().parents[2]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--run-dir", type=Path,
        default=repo / "results/csv/rc3_baseline/benchmark_runs/rc3_full_metrics_20260611_004003",
        help="Accepted run dir containing csv_only/*_long.csv and a sibling *_summary_all_metrics.csv",
    )
    ap.add_argument("--out-csv", type=Path, required=True)
    args = ap.parse_args()

    diff = build_diff(args.run_dir)
    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    fields = ["dataset_track", "method", "metric", "model_count_used",
              "accepted_value", "recomputed_value", "absolute_delta", "explanation"]
    with args.out_csv.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(diff)

    mism = [d for d in diff if d["explanation"].startswith("MISMATCH")]
    maxd = max((float(d["absolute_delta"]) for d in diff if d["absolute_delta"]), default=0.0)
    print(f"[validate] rows={len(diff)} max_abs_delta={maxd:.2e} mismatches_over_rounding={len(mism)}")
    for d in mism:
        print(f"  MISMATCH {d['dataset_track']}/{d['method']}/{d['metric']}: "
              f"accepted={d['accepted_value']} recomputed={d['recomputed_value']} delta={d['absolute_delta']}")
    print(f"[validate] artifact -> {args.out_csv}")


if __name__ == "__main__":
    main()
