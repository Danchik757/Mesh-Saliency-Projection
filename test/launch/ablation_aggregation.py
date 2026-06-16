"""Ablation aggregation layer (first implementation of ABLATION_AUTOMATION_SPEC.md).

NON-DESTRUCTIVE. This module consumes already-computed per-model metric rows (the
14-metric long schema the reference / full-metrics runners emit) and writes the
spec layout:

    results/ablation/<stage>/<dataset>/<method>/
      aggregate/ablation_runs.csv      (append one row per run)
      aggregate/ablation_runs.jsonl    (append one object per run)
      runs/<run_id>/
        README.md  params.json  aggregate_row.json
        metrics_long.jsonl  metrics_summary.csv  stdout.log

It does NOT import or modify any baseline evaluator or existing launcher. It is a
pure-stdlib library + a `--demo` CLI. `cone` and `screen_space` are kept in
separate directory branches (method is part of the path).

Relationship to `run_ablation_window_delay.py`: that launcher writes per-model
rows with only six metrics (`CC,SIM,KLD,MSE,AUC_Judd,NSS`). Use
`adapt_timing_ablation_row` to feed those rows in; only `CC/SIM/KLD/MSE` map
directly, and the single `AUC_Judd`/`NSS` are preserved as provenance (they are
NOT the three top-k proxies), so the other ten compact columns stay blank until a
14-metric re-run.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path

# ── schema ─────────────────────────────────────────────────────────────────────

# 14-metric compact block, in contract order (docs/METRIC_RUN_AND_CSV_CONTRACT.md).
METRIC_COLUMNS = (
    "CC", "SIM", "KLD", "MSE", "MAE", "Spearman", "Cosine",
    "AUC_at_10pct", "AUC_at_5pct", "AUC_at_1pct",
    "NSS_at_10pct", "NSS_at_5pct", "NSS_at_1pct", "hit_rate",
)

# evaluator-internal proxy names -> compact names (the launcher rename path).
PROXY_RENAME = {
    "AUC_Judd_gt_top_10pct_proxy": "AUC_at_10pct",
    "AUC_Judd_gt_top_5pct_proxy": "AUC_at_5pct",
    "AUC_Judd_gt_top_1pct_proxy": "AUC_at_1pct",
    "NSS_gt_top_10pct_proxy": "NSS_at_10pct",
    "NSS_gt_top_5pct_proxy": "NSS_at_5pct",
    "NSS_gt_top_1pct_proxy": "NSS_at_1pct",
}

# Parameter columns required by ABLATION_AUTOMATION_SPEC.md, in order.
PARAM_COLUMNS = (
    # run_id = logical run identity (may repeat: a superseded row and its
    # replacement share it). artifact_run_id = the unique physical directory under
    # runs/ for one execution; result_root is its full path. This separation keeps
    # provenance append-only: each execution has its own inspectable directory.
    "run_id", "artifact_run_id", "stage_name", "dataset", "method", "texture_type", "server",
    "host_group", "repo_commit", "branch", "release_tag", "result_root",
    "status", "error_type", "n_ok", "n_failed", "n_total_models",
    "model_subset_name", "model_subset_size", "model_set_signature", "timing_contract", "window_mode",
    "frame_offset", "delay_seconds", "delay_frames", "gaze_start_frame",
    "placement_start_frame", "turn_frame_count", "crop_start_seconds",
    "crop_end_seconds", "fixation_data_tag", "fixation_source_root",
    "placement_json_root", "gt_variant", "gt_domain", "gt_match_type",
    "sigma_px", "sigma_screen", "sigma_multiplier", "sigma_deg", "radius_sigma_mult",
    "gaussian_kernel_mode", "normalization_mode", "projection_fov_mode",
    "horizontal_fov_deg", "vertical_fov_deg", "max_workers", "nice_level",
    "ionice_class", "ionice_level", "timeout_seconds", "started_at",
    "finished_at", "elapsed_seconds", "command", "notes",
)

# Diagnostic columns appended to the aggregate/long outputs (NOT the historical
# compact `metrics_summary.csv`). Per the 2026-06-15 dual-KLD decision:
#   KLD_evaluator = current benchmark output (== historical `KLD`);
#   KLD_trusted   = trusted-module KLD (mathematical reference), present only when
#                   pred/GT inputs were available to compute it (else blank).
DIAGNOSTIC_METRIC_COLUMNS = ("KLD_evaluator", "KLD_trusted")

AGGREGATE_COLUMNS = PARAM_COLUMNS + METRIC_COLUMNS + DIAGNOSTIC_METRIC_COLUMNS

OK_STATUSES = ("ok",)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _to_float(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text == "" or text.lower() == "nan":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _fmt(value, ndigits: int | None = None) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and ndigits is not None:
        return f"{value:.{ndigits}f}"
    return str(value)


def _fmt_cell(column: str, value) -> str:
    """Format an aggregate-CSV cell: metric columns to 6 dp (no float noise),
    everything else verbatim. The JSONL keeps full float precision."""
    if column in METRIC_COLUMNS or column in DIAGNOSTIC_METRIC_COLUMNS:
        number = _to_float(value)
        return "" if number is None else f"{number:.6f}"
    return _fmt(value)


# ── ingestion / aggregation ────────────────────────────────────────────────────

def normalize_metric_row(row: Mapping) -> dict:
    """Map one per-model row to {compact_metric: float|None}, applying the proxy
    rename and float parsing. Accepts compact or evaluator-internal metric names."""
    renamed: dict = {}
    for key, value in row.items():
        renamed[PROXY_RENAME.get(key, key)] = value
    out = {metric: _to_float(renamed.get(metric)) for metric in METRIC_COLUMNS}
    # Dual-KLD diagnostics: KLD_evaluator falls back to the historical `KLD`
    # (evaluator output); KLD_trusted is only present when the producer computed it.
    kld_evaluator = _to_float(renamed.get("KLD_evaluator"))
    out["KLD_evaluator"] = kld_evaluator if kld_evaluator is not None else out.get("KLD")
    out["KLD_trusted"] = _to_float(renamed.get("KLD_trusted"))
    return out


def aggregate_metrics(model_rows: Sequence[Mapping], method: str,
                      ok_statuses: Sequence[str] = OK_STATUSES) -> tuple[dict, dict]:
    """Mean of each compact metric over status-ok rows. Returns (means, counts).
    `hit_rate` is forced empty for `screen_space` (no ray/cone hit stage)."""
    ok_rows = [r for r in model_rows if str(r.get("status", "")) in ok_statuses]
    counts = {
        "n_ok": len(ok_rows),
        "n_failed": len(model_rows) - len(ok_rows),
        "n_total_models": len(model_rows),
    }
    normalized = [normalize_metric_row(r) for r in ok_rows]
    means: dict = {}
    for metric in (*METRIC_COLUMNS, *DIAGNOSTIC_METRIC_COLUMNS):
        if metric == "hit_rate" and method == "screen_space":
            means[metric] = None
            continue
        vals = [n[metric] for n in normalized if n.get(metric) is not None]
        means[metric] = (sum(vals) / len(vals)) if vals else None
    return means, counts


def _sig_val(value) -> str:
    return str(value).replace(".", "p").replace(" ", "")


def model_set_signature(models: Sequence[str]) -> str:
    """Stable identity for an explicit ordered model list."""
    return hashlib.sha1("\n".join(str(m) for m in models).encode()).hexdigest()[:12]


def run_signature(params: Mapping) -> str:
    """Deterministic, collision-safe short signature from the swept parameters,
    for a default run_id when the caller does not supply one. The readable body is
    truncated for filesystem friendliness, but an 8-char hash of the full swept
    parameter set is always appended so distinct parameter sets never collide."""
    abbr = (("w", "window_mode"), ("off", "frame_offset"), ("d", "delay_seconds"),
            ("spx", "sigma_px"), ("ssc", "sigma_screen"), ("smul", "sigma_multiplier"), ("sdeg", "sigma_deg"),
            ("rsm", "radius_sigma_mult"), ("mset", "model_set_signature"))
    parts = [f"{short}{_sig_val(params[key])}" for short, key in abbr
             if params.get(key) not in (None, "")]
    body = "_".join(parts) if parts else "default"
    digest = hashlib.sha1(
        "|".join(f"{key}={params.get(key)}" for _, key in abbr).encode()).hexdigest()[:8]
    return f"{body[:60]}_{digest}"


def build_aggregate_row(params: Mapping, model_rows: Sequence[Mapping], *,
                        run_id: str | None = None) -> dict:
    """Assemble one aggregate row (all PARAM + METRIC columns) for a run."""
    method = str(params.get("method", ""))
    means, counts = aggregate_metrics(model_rows, method)
    run_id = run_id or params.get("run_id") or run_signature(params)

    row = {col: "" for col in AGGREGATE_COLUMNS}
    for col in PARAM_COLUMNS:
        if col in params and params[col] is not None:
            row[col] = params[col]
    row["run_id"] = run_id
    row.update(counts)
    if not row.get("model_subset_size"):
        row["model_subset_size"] = counts["n_total_models"]
    if not row.get("status"):
        if counts["n_ok"] == 0:
            row["status"] = "empty"
        elif counts["n_failed"] == 0:
            row["status"] = "ok"
        else:
            row["status"] = "partial"
    if not row.get("error_type"):
        error_types = sorted({
            str(r.get("error_type")) for r in model_rows
            if str(r.get("status", "")) not in OK_STATUSES and r.get("error_type")
        })
        if len(error_types) == 1:
            row["error_type"] = error_types[0]
        elif len(error_types) > 1:
            row["error_type"] = "mixed:" + ",".join(error_types)
    for metric in (*METRIC_COLUMNS, *DIAGNOSTIC_METRIC_COLUMNS):
        row[metric] = means[metric] if means[metric] is not None else ""
    return row


# ── output writers ─────────────────────────────────────────────────────────────

def _aggregate_dir(results_root: Path, stage: str, dataset: str, method: str) -> Path:
    return Path(results_root) / "ablation" / stage / dataset / method / "aggregate"


def _runs_dir(results_root: Path, stage: str, dataset: str, method: str) -> Path:
    return Path(results_root) / "ablation" / stage / dataset / method / "runs"


def _custom_storage_dirs(results_root: Path, params: Mapping) -> tuple[Path, Path] | None:
    parts = params.get("storage_parts")
    if not parts:
        return None
    if not isinstance(parts, (list, tuple)) or not all(str(p).strip() for p in parts):
        raise ValueError("params.storage_parts must be a non-empty list/tuple of path components")
    base = Path(results_root) / "ablation"
    for part in parts:
        base = base / str(part)
    return base / "aggregate", base / "runs"


def _render_readme(aggregate_row: Mapping, params: Mapping, command: str,
                   aggregate_csv_path: Path) -> str:
    swept = {k: params.get(k) for k in (
        "window_mode", "frame_offset", "delay_seconds", "sigma_px",
        "sigma_screen", "sigma_deg", "radius_sigma_mult") if params.get(k) not in (None, "")}
    timing = {k: aggregate_row.get(k) for k in (
        "timing_contract", "frame_offset", "delay_seconds", "delay_frames",
        "gaze_start_frame", "placement_start_frame", "turn_frame_count")}
    lines = [
        f"# Ablation run `{aggregate_row['run_id']}`",
        "",
        f"- stage: `{aggregate_row.get('stage_name','')}`",
        f"- dataset: `{aggregate_row.get('dataset','')}`  method: `{aggregate_row.get('method','')}`"
        f"  texture_type: `{aggregate_row.get('texture_type','')}`",
        f"- status: `{aggregate_row.get('status','')}`  "
        f"n_ok={aggregate_row.get('n_ok')} n_failed={aggregate_row.get('n_failed')} "
        f"n_total_models={aggregate_row.get('n_total_models')}",
        f"- model_subset: `{aggregate_row.get('model_subset_name','')}` "
        f"(size {aggregate_row.get('model_subset_size','')})",
        f"- repo_commit: `{aggregate_row.get('repo_commit','')}`  branch: `{aggregate_row.get('branch','')}`",
        "",
        "## Exact command",
        "",
        "```bash",
        command or "(not recorded)",
        "```",
        "",
        "## Timing contract",
        "",
        *[f"- {k}: `{v}`" for k, v in timing.items()],
        "",
        "## Swept parameters",
        "",
        *([f"- {k}: `{v}`" for k, v in swept.items()] or ["- (none)"]),
        "",
        "## Aggregate table row",
        "",
        f"- logical run_id: `{aggregate_row['run_id']}`  "
        f"artifact_run_id: `{aggregate_row.get('artifact_run_id', '')}` (this directory)",
        f"- CSV: `{aggregate_csv_path}` (row `artifact_run_id={aggregate_row.get('artifact_run_id', '')}`)",
        f"- JSONL: `{aggregate_csv_path.with_suffix('.jsonl')}`",
        "",
        "Raw provenance in this directory: `params.json`, `aggregate_row.json`, "
        "`metrics_long.jsonl`, `metrics_summary.csv`, `stdout.log`.",
        "",
    ]
    return "\n".join(lines)


def write_run_directory(run_dir: Path, aggregate_row: Mapping, model_rows: Sequence[Mapping],
                        *, params: Mapping, command: str = "", stdout_text: str = "",
                        aggregate_csv_path: Path) -> None:
    # exist_ok=False guards the never-clobber invariant: callers must hand a fresh
    # directory (record_run uses _unique_artifact_dir to guarantee this).
    run_dir.mkdir(parents=True, exist_ok=False)

    (run_dir / "params.json").write_text(json.dumps(dict(params), indent=2, default=str))
    (run_dir / "aggregate_row.json").write_text(json.dumps(dict(aggregate_row), indent=2, default=str))

    with (run_dir / "metrics_long.jsonl").open("w") as fh:
        for r in model_rows:
            record = {"model": r.get("model", ""), "status": r.get("status", "")}
            for key in ("error_type", "error_message", "identity_sha1", "repo_commit"):
                if r.get(key) not in (None, ""):
                    record[key] = r.get(key)
            record.update(normalize_metric_row(r))
            fh.write(json.dumps(record, default=str) + "\n")

    with (run_dir / "metrics_summary.csv").open("w", newline="") as fh:
        header = ["dataset_track", "method", "n_ok", *METRIC_COLUMNS]
        w = csv.writer(fh)
        w.writerow(header)
        w.writerow([
            aggregate_row.get("dataset", ""), aggregate_row.get("method", ""),
            aggregate_row.get("n_ok", 0),
            *[_fmt(_to_float(aggregate_row.get(m)), 4) for m in METRIC_COLUMNS],
        ])

    (run_dir / "stdout.log").write_text(stdout_text)
    models = [str(r.get("model", "")) for r in model_rows if r.get("model")]
    if models:
        (run_dir / "models.txt").write_text("\n".join(models) + "\n")
    (run_dir / "README.md").write_text(
        _render_readme(aggregate_row, params, command, aggregate_csv_path))


def _read_run_ids(jsonl_path: Path) -> list[str]:
    if not jsonl_path.is_file():
        return []
    ids = []
    with jsonl_path.open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                ids.append(json.loads(line).get("run_id"))
    return ids


def append_aggregate_row(aggregate_dir: Path, aggregate_row: Mapping, *,
                         on_duplicate: str = "error") -> None:
    """Append one row to ablation_runs.csv and ablation_runs.jsonl. Never silently
    overwrites: a duplicate run_id raises unless on_duplicate is 'supersede' (mark
    prior rows superseded, then append) or 'allow'."""
    aggregate_dir.mkdir(parents=True, exist_ok=True)
    csv_path = aggregate_dir / "ablation_runs.csv"
    jsonl_path = aggregate_dir / "ablation_runs.jsonl"
    run_id = aggregate_row["run_id"]

    if run_id in _read_run_ids(jsonl_path):
        if on_duplicate == "error":
            raise ValueError(
                f"run_id {run_id!r} already in {jsonl_path}; pass a new run_id or "
                "on_duplicate='supersede'/'allow'")
        if on_duplicate == "supersede":
            _mark_superseded(csv_path, jsonl_path, run_id, aggregate_row["run_id"])

    write_header = not csv_path.exists()
    with csv_path.open("a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=AGGREGATE_COLUMNS, extrasaction="ignore")
        if write_header:
            w.writeheader()
        w.writerow({c: _fmt_cell(c, aggregate_row.get(c, "")) for c in AGGREGATE_COLUMNS})
    with jsonl_path.open("a") as fh:
        fh.write(json.dumps({c: aggregate_row.get(c, "") for c in AGGREGATE_COLUMNS}, default=str) + "\n")


def _mark_superseded(csv_path: Path, jsonl_path: Path, run_id: str, by: str) -> None:
    rows = []
    with jsonl_path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if obj.get("run_id") == run_id:
                obj["status"] = "superseded"
                obj["notes"] = (str(obj.get("notes", "")) + f" superseded_by={by}").strip()
            rows.append(obj)
    with jsonl_path.open("w") as fh:
        for obj in rows:
            fh.write(json.dumps(obj, default=str) + "\n")
    with csv_path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=AGGREGATE_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for obj in rows:
            w.writerow({c: _fmt_cell(c, obj.get(c, "")) for c in AGGREGATE_COLUMNS})


def _unique_artifact_dir(runs_root: Path, run_id: str) -> Path:
    """A physical directory that does not yet exist, so an execution never clobbers
    an earlier one. First execution -> runs/<run_id>; later ones -> <run_id>__rev2,
    __rev3, ... This is the `artifact_run_id` for the execution."""
    candidate = runs_root / run_id
    if not candidate.exists():
        return candidate
    rev = 2
    while (runs_root / f"{run_id}__rev{rev}").exists():
        rev += 1
    return runs_root / f"{run_id}__rev{rev}"


def record_run(results_root: Path, params: Mapping, model_rows: Sequence[Mapping], *,
               run_id: str | None = None, command: str = "", stdout_text: str = "",
               on_duplicate: str = "error") -> Path:
    """End-to-end: build the aggregate row, write the per-run directory, and append
    to the per-(dataset,method) aggregate tables. Returns the per-run directory.

    Append-only / provenance safety: the duplicate policy is resolved BEFORE any
    raw artifact directory is written, and every execution gets its own distinct
    physical directory (`artifact_run_id`). So a rejected duplicate never mutates
    an existing run directory, and a superseded older row keeps pointing at its own
    inspectable raw artifacts."""
    stage = str(params["stage_name"])
    dataset = str(params["dataset"])
    method = str(params["method"])
    aggregate_row = build_aggregate_row(params, model_rows, run_id=run_id)
    run_id = aggregate_row["run_id"]

    custom_dirs = _custom_storage_dirs(results_root, params)
    if custom_dirs is not None:
        aggregate_dir, runs_root = custom_dirs
    else:
        aggregate_dir = _aggregate_dir(results_root, stage, dataset, method)
        runs_root = _runs_dir(results_root, stage, dataset, method)

    # Preflight the duplicate policy before writing any raw artifacts.
    is_duplicate = run_id in _read_run_ids(aggregate_dir / "ablation_runs.jsonl")
    if is_duplicate and on_duplicate == "error":
        raise ValueError(
            f"run_id {run_id!r} already recorded under {aggregate_dir}; pass a new "
            "run_id or on_duplicate='supersede'/'allow' (existing run dir left intact)")

    # Distinct physical directory per execution -> never clobber a prior run.
    artifact_dir = _unique_artifact_dir(runs_root, run_id)
    aggregate_row["artifact_run_id"] = artifact_dir.name
    aggregate_row["result_root"] = str(artifact_dir)

    write_run_directory(artifact_dir, aggregate_row, model_rows, params=params,
                        command=command, stdout_text=stdout_text,
                        aggregate_csv_path=aggregate_dir / "ablation_runs.csv")
    append_aggregate_row(aggregate_dir, aggregate_row, on_duplicate=on_duplicate)
    return artifact_dir


# ── legacy adapter ─────────────────────────────────────────────────────────────

def adapt_timing_ablation_row(row: Mapping) -> dict:
    """Adapt a `run_ablation_window_delay.py` per-model row (6 metrics:
    CC,SIM,KLD,MSE,AUC_Judd,NSS) into a row this layer can ingest. Only the four
    shared metrics populate the 14-metric block; the single AUC_Judd/NSS are kept
    under `notes` as provenance (they are not the three top-k proxies)."""
    out = dict(row)
    note = []
    if row.get("AUC_Judd") not in (None, ""):
        note.append(f"legacy_AUC_Judd={row['AUC_Judd']}")
    if row.get("NSS") not in (None, ""):
        note.append(f"legacy_NSS={row['NSS']}")
    if note:
        out["notes"] = (str(row.get("notes", "")) + " " + "; ".join(note)).strip()
    return out


# ── demo CLI ───────────────────────────────────────────────────────────────────

def _demo_rows(method: str) -> list[dict]:
    base = [
        {"model": "Pear_L3", "status": "ok", "CC": 0.51, "SIM": 0.68, "KLD": 0.40,
         "MSE": 0.033, "MAE": 0.12, "Spearman": 0.55, "Cosine": 0.78,
         "AUC_Judd_gt_top_10pct_proxy": 0.80, "AUC_Judd_gt_top_5pct_proxy": 0.83,
         "AUC_Judd_gt_top_1pct_proxy": 0.88, "NSS_gt_top_10pct_proxy": 1.05,
         "NSS_gt_top_5pct_proxy": 1.30, "NSS_gt_top_1pct_proxy": 1.60, "hit_rate": 0.87},
        {"model": "Starfruit_L3", "status": "ok", "CC": 0.47, "SIM": 0.64, "KLD": 0.52,
         "MSE": 0.041, "MAE": 0.14, "Spearman": 0.49, "Cosine": 0.74,
         "AUC_Judd_gt_top_10pct_proxy": 0.76, "AUC_Judd_gt_top_5pct_proxy": 0.79,
         "AUC_Judd_gt_top_1pct_proxy": 0.85, "NSS_gt_top_10pct_proxy": 0.95,
         "NSS_gt_top_5pct_proxy": 1.15, "NSS_gt_top_1pct_proxy": 1.45, "hit_rate": 0.83},
        {"model": "BrokenMesh_L3", "status": "failed", "error_type": "no_report"},
    ]
    if method == "screen_space":
        for r in base:
            r.pop("hit_rate", None)
    return base


def _demo(out_root: Path) -> None:
    for method in ("cone", "screen_space"):
        params = {
            "stage_name": "stage1_sigma", "dataset": "sal3d", "method": method,
            "texture_type": "", "branch": "orchestra/metric-ablation-lab",
            "repo_commit": "demo", "timing_contract": "one_turn_from_start",
            "window_mode": "one_turn_from_start", "frame_offset": 0,
            "delay_seconds": 0.0, "delay_frames": 0, "gaze_start_frame": 0,
            "placement_start_frame": 0, "turn_frame_count": 660,
            "sigma_deg": 2.0 if method == "cone" else "",
            "radius_sigma_mult": 3.0 if method == "cone" else "",
            "sigma_px": "" if method == "cone" else 39.45,
            "model_subset_name": "demo_2", "nice_level": 19,
            "ionice_class": 2, "ionice_level": 7, "started_at": utc_now_iso(),
            "finished_at": utc_now_iso(), "notes": "synthetic demo",
        }
        run_dir = record_run(
            out_root, params, _demo_rows(method),
            command=f"python3 test/launch/ablation_aggregation.py --demo  # {method}",
            stdout_text="(demo: no real evaluator stdout)\n",
            on_duplicate="supersede")  # rerun-safe: supersede prior demo, keep its raw dir
        print(f"[demo] {method}: {run_dir}")


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Ablation aggregation layer demo/CLI.")
    ap.add_argument("--demo", type=Path, metavar="OUT_ROOT",
                    help="Generate a synthetic example layout under OUT_ROOT/ablation/...")
    args = ap.parse_args()
    if args.demo:
        _demo(args.demo)
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
