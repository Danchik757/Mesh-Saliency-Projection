#!/usr/bin/env python3
"""
Merge multiple metrics_rows.jsonl files from the RC3 optimized full run
into a single deduplicated metrics_long.csv and metrics_compact.csv.

Safety guarantees
-----------------
1. Configuration compatibility (refuses to mix incompatible runs).
   All ``ok`` rows must agree on the run-wide timing/provenance contract
   (``release_tag``, ``timing_contract``, ``fixation_data_tag``,
   ``frame_offset``, ``delay_seconds``).  Within each ``(dataset, method)``
   group the sigma configuration (``sigma_deg``, ``radius_sigma_mult``,
   ``sigma_px``, ``sigma_screen``) must also agree.  Any divergence is an
   error: the merge aborts and prints every incompatibility it found rather
   than silently averaging across contracts.  ``--allow-incompatible`` downgrades
   the abort to a warning (use only when you know the inputs are comparable).

2. NaN / Inf exclusion.  Non-finite metric values (Python ``json`` round-trips
   ``NaN``/``Infinity``) are dropped from every mean instead of poisoning the
   aggregate to ``NaN``.

Deduplication rule (per job_key):
  1. Prefer ok rows over failed/error rows.
  2. If multiple ok rows exist, keep the one that was written first
     (lowest file index in --jsonl-files order, then earliest in that file).

Usage
-----
  python3 test/launch/merge_rc3_final.py \\
    --jsonl-files path/to/main/metrics_rows.jsonl \\
                  path/to/gml01/metrics_rows.jsonl \\
                  path/to/blade200k_followup/metrics_rows.jsonl \\
    --output-dir  results/rc3_final_merged

Outputs
-------
  <output-dir>/metrics_long.csv
  <output-dir>/metrics_compact.csv
  <output-dir>/merge_summary.txt
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

# ── column definitions (must match run_full_metrics_optimized_sigma.py) ────────

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

# ── configuration-compatibility contract ───────────────────────────────────────
# Run-wide fields: every ok row in the merge must agree on these.
_CONFIG_GLOBAL_FIELDS = [
    "release_tag", "timing_contract", "fixation_data_tag",
    "frame_offset", "delay_seconds",
]
# Sigma fields: must agree within each (dataset, method) group.
_CONFIG_SIGMA_FIELDS = ["sigma_deg", "radius_sigma_mult", "sigma_px", "sigma_screen"]


class IncompatibleMergeError(RuntimeError):
    """Raised when ok rows from incompatible runs would be merged together."""


# ── numeric helpers ─────────────────────────────────────────────────────────────

def finite_float(v: Any) -> float | None:
    """Parse v as a float, returning None for non-numeric AND non-finite values.

    json.dumps emits NaN/Infinity and json.loads reads them back as floats, so a
    bare float() would let a single non-finite metric poison a whole mean.
    """
    try:
        f = float(v)
    except (ValueError, TypeError):
        return None
    return f if math.isfinite(f) else None


def _norm(v: Any) -> str:
    """Normalize a config value for comparison (numeric-aware, blank-tolerant)."""
    if v is None or v == "":
        return ""
    f = finite_float(v)
    if f is not None:
        # 0 and 0.0 and "0.0" collapse to one representation.
        return repr(round(f, 9))
    return str(v)


# ── merge ──────────────────────────────────────────────────────────────────────

def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def check_merge_compatibility(rows: list[dict]) -> list[str]:
    """Return a list of human-readable incompatibility messages (empty == compatible).

    Only ``ok`` rows are checked — failed/error rows carry blank config fields.
    """
    ok_rows = [r for r in rows if r.get("status") == "ok"
               and r.get("error_type", "") != "dry_run"]
    problems: list[str] = []

    # Run-wide fields: one value across the whole merge.
    for field in _CONFIG_GLOBAL_FIELDS:
        seen: dict[str, list[str]] = defaultdict(list)
        for r in ok_rows:
            seen[_norm(r.get(field))].append(r.get("job_key", "?"))
        present = {k: v for k, v in seen.items() if k != ""}
        if len(present) > 1:
            detail = "; ".join(
                f"{val!r} (e.g. {keys[0]}, n={len(keys)})"
                for val, keys in sorted(present.items())
            )
            problems.append(f"conflicting {field} across runs: {detail}")

    # Sigma fields: one value per (dataset, method) group.
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in ok_rows:
        groups[(r.get("dataset", "?"), r.get("method", "?"))].append(r)
    for (ds, method), grp in sorted(groups.items()):
        for field in _CONFIG_SIGMA_FIELDS:
            vals = {_norm(r.get(field)) for r in grp}
            vals.discard("")
            if len(vals) > 1:
                problems.append(
                    f"conflicting {field} for {ds}/{method}: {sorted(vals)}"
                )
    return problems


def merge_rows(jsonl_files: list[Path]) -> list[dict]:
    """
    Load all JSONL files and deduplicate by job_key.
    Priority: ok > failed; within same status, earlier source wins.
    """
    # best_row[job_key] = (priority, row)
    # priority: 0=ok (lower is better), 1=non-ok
    best: dict[str, tuple[int, dict]] = {}

    for fpath in jsonl_files:
        if not fpath.is_file():
            print(f"[warn] file not found, skipping: {fpath}", file=sys.stderr)
            continue
        rows = load_jsonl(fpath)
        print(f"  {fpath.name}: {len(rows)} rows", file=sys.stderr)
        for row in rows:
            key = row.get("job_key", "")
            if not key:
                continue
            status = row.get("status", "")
            prio = 0 if status == "ok" else 1
            if key not in best or prio < best[key][0]:
                best[key] = (prio, row)

    return [row for _, row in best.values()]


def load_all_rows(jsonl_files: list[Path]) -> list[dict]:
    """Flatten every row from every input file (no dedup) for compatibility checks."""
    all_rows: list[dict] = []
    for fpath in jsonl_files:
        if fpath.is_file():
            all_rows.extend(load_jsonl(fpath))
    return all_rows


# ── CSV writers ────────────────────────────────────────────────────────────────

def write_long_csv(rows: list[dict], path: Path) -> None:
    rows_sorted = sorted(rows, key=lambda r: (
        r.get("dataset", ""), r.get("model", ""), r.get("method", "")))
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_LONG_COLS, extrasaction="ignore")
        w.writeheader()
        for r in rows_sorted:
            w.writerow({c: r.get(c, "") for c in _LONG_COLS})


def write_compact_csv(rows: list[dict], path: Path) -> dict[str, int]:
    """Write the compact per-(dataset,method) means.

    Returns a count of dropped non-finite values per metric column.
    """
    dropped: dict[str, int] = defaultdict(int)

    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("status") == "ok" and r.get("error_type", "") != "dry_run":
            groups[(r["dataset"], r["method"])].append(r)

    proxy_map = {
        "AUC_at_10pct": "AUC_Judd_gt_top_10pct_proxy",
        "AUC_at_5pct":  "AUC_Judd_gt_top_5pct_proxy",
        "AUC_at_1pct":  "AUC_Judd_gt_top_1pct_proxy",
        "NSS_at_10pct": "NSS_gt_top_10pct_proxy",
        "NSS_at_5pct":  "NSS_gt_top_5pct_proxy",
        "NSS_at_1pct":  "NSS_gt_top_1pct_proxy",
    }

    header = ["dataset_track", "method", "n_ok"] + _COMPACT_METRICS
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for ds, method in _COMPACT_ROW_ORDER:
            grp = groups.get((ds, method), [])
            if not grp:
                continue
            out: dict[str, Any] = {"dataset_track": ds, "method": method, "n_ok": len(grp)}
            for metric in _COMPACT_METRICS:
                col = proxy_map.get(metric, metric)
                vals = []
                for r in grp:
                    raw = r.get(col)
                    fv = finite_float(raw)
                    if fv is not None:
                        vals.append(fv)
                    elif raw not in (None, ""):
                        dropped[col] += 1
                out[metric] = f"{sum(vals)/len(vals):.4f}" if vals else ""
            w.writerow([out.get(c, "") for c in header])
    return dict(dropped)


# ── summary ────────────────────────────────────────────────────────────────────

def write_summary(rows: list[dict], jsonl_files: list[Path], path: Path,
                  dropped_non_finite: dict[str, int] | None = None) -> None:
    ok_rows = [r for r in rows if r.get("status") == "ok"]
    fail_rows = [r for r in rows if r.get("status") != "ok"]

    from collections import Counter
    ok_by_ds_method = Counter((r["dataset"], r["method"]) for r in ok_rows)
    fail_by_model = Counter(
        (r.get("dataset", "?"), r.get("model", "?"), r.get("method", "?"))
        for r in fail_rows
    )

    lines = [
        "RC3 Final Merged Metrics — Summary",
        "=" * 60,
        "",
        f"Source JSONL files ({len(jsonl_files)}):",
    ]
    for f in jsonl_files:
        lines.append(f"  {f}")
    lines += [
        "",
        f"Total rows after dedup: {len(rows)}",
        f"  ok:     {len(ok_rows)}",
        f"  failed: {len(fail_rows)}",
        "",
        "n_ok by dataset/method:",
    ]
    for ds, method in _COMPACT_ROW_ORDER:
        n = ok_by_ds_method.get((ds, method), 0)
        lines.append(f"  {ds:30s}  {method:15s}  n_ok={n}")
    if dropped_non_finite:
        lines += ["", "Non-finite metric values dropped from means:"]
        for col, n in sorted(dropped_non_finite.items()):
            lines.append(f"  {col}: {n}")
    if fail_rows:
        lines += ["", "Failed jobs:"]
        for (ds, model, method), cnt in sorted(fail_by_model.items()):
            err = next((r.get("error_message", "") for r in fail_rows
                        if r.get("dataset") == ds and r.get("model") == model
                        and r.get("method") == method), "")[:80]
            lines.append(f"  {ds}/{model}/{method}  — {err}")
    lines.append("")

    text = "\n".join(lines)
    path.write_text(text)
    print(text)


# ── main ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--jsonl-files", nargs="+", required=True, type=Path,
                   help="One or more metrics_rows.jsonl files to merge (in priority order).")
    p.add_argument("--output-dir", required=True, type=Path,
                   help="Directory to write merged CSVs and summary.")
    p.add_argument("--allow-incompatible", action="store_true",
                   help="Downgrade configuration-mismatch errors to warnings (use with care).")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    print(f"[merge] loading {len(args.jsonl_files)} JSONL files...", file=sys.stderr)

    # Compatibility check runs over EVERY ok row (pre-dedup) so a stray
    # incompatible file is caught even if its rows would lose dedup.
    all_rows = load_all_rows(args.jsonl_files)
    problems = check_merge_compatibility(all_rows)
    if problems:
        print("[merge] INCOMPATIBLE INPUTS — refusing to mix metric runs:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        if not args.allow_incompatible:
            raise IncompatibleMergeError(
                f"{len(problems)} configuration incompatibilit"
                f"{'y' if len(problems) == 1 else 'ies'} found; "
                "pass --allow-incompatible only if the inputs are truly comparable."
            )
        print("[merge] --allow-incompatible set: continuing despite mismatches.",
              file=sys.stderr)

    merged = merge_rows(args.jsonl_files)
    print(f"[merge] {len(merged)} unique job_keys after dedup", file=sys.stderr)

    long_path    = out / "metrics_long.csv"
    compact_path = out / "metrics_compact.csv"
    summary_path = out / "merge_summary.txt"

    write_long_csv(merged, long_path)
    print(f"[merge] wrote {long_path}")

    dropped = write_compact_csv(merged, compact_path)
    print(f"[merge] wrote {compact_path}")

    write_summary(merged, args.jsonl_files, summary_path, dropped)
    print(f"[merge] wrote {summary_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
