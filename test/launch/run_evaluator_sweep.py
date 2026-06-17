"""Evaluator-backed local per-point sweep runner (first real-invocation version).

LOCAL ONLY, NON-DESTRUCTIVE. Unlike `sweep_local.py` (which reuses one static
accepted source for every point), this runner produces genuinely point-dependent
per-model rows by *invoking the real evaluator entrypoint per point* and parsing
its report, then records each point through `ablation_aggregation.record_run(...)`.

The evaluator invocation is **injectable** (`invoke`): the default
`subprocess_evaluator_invoke` builds the real CLI (sigma-aware) and parses the
report; unit tests inject a mock, because real evaluation needs the external
mesh/gaze/GT assets (distributed via GitHub Releases) that are not in the checkout.

Reuses, without modifying: `run_ablation_window_delay.py` (`_EVAL`,
`TIMING_CONTRACT`, `FIXATION_DATA_TAG`, `_frame_offset_for`, `extract_metrics`,
`_select_report`) and `ablation_aggregation.py` (`record_run`). It imports no
baseline evaluator.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

_DIR = Path(__file__).resolve().parent


def _load(name: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # register before exec so @dataclass can resolve __module__
    spec.loader.exec_module(mod)
    return mod


import numpy as np

rawd = _load("run_ablation_window_delay")   # proven command-build + report parsing
agg = _load("ablation_aggregation")
pf = _load("evaluator_preflight")           # asset-discovery / fail-fast preflight
dk = _load("dual_kld")                       # evaluator vs trusted KLD enrichment

# Metric keys to pull from the evaluator report leaf (internal names; the
# aggregation layer renames the proxies to the compact AUC_at_*/NSS_at_*).
_SOURCE_METRIC_KEYS = (
    "CC", "SIM", "KLD", "MSE", "MAE", "Spearman", "Cosine",
    "AUC_Judd_gt_top_10pct_proxy", "AUC_Judd_gt_top_5pct_proxy", "AUC_Judd_gt_top_1pct_proxy",
    "NSS_gt_top_10pct_proxy", "NSS_gt_top_5pct_proxy", "NSS_gt_top_1pct_proxy",
)

EvaluatorInvoke = Callable[[dict, str], dict]


def make_sigma_grid(dataset: str, method: str, *, sigma_param: str, sigma_values: Sequence[float],
                    radius_sigma_mult: float | None = None, delay_seconds: float = 0.0,
                    window_mode: str = "one_turn_from_start") -> list[dict]:
    """Tiny grid: one point per sigma value, carrying the explicit sigma key plus
    fixed timing params so each point fully specifies the evaluator invocation."""
    points = []
    for value in sigma_values:
        point = {"dataset": dataset, "method": method, "axis": sigma_param, "value": value,
                 sigma_param: value, "delay_seconds": delay_seconds, "window_mode": window_mode}
        if radius_sigma_mult is not None:
            point["radius_sigma_mult"] = radius_sigma_mult
        points.append(point)
    return points


def build_evaluator_command(point: dict, model: str, *, output_dir: Path,
                            fixation_root: str | None = None, python: str | None = None) -> list[str]:
    """Real, sigma-aware argv for the evaluator entrypoint. Mirrors
    `run_ablation_window_delay.build_command` flag-for-flag but takes the swept
    sigma from the point (the launcher uses fixed default sigma)."""
    dataset, method = point["dataset"], point["method"]
    script = rawd._EVAL[dataset][method]
    python = python or os.environ.get("REPROJECT_PYTHON", sys.executable)
    frame_offset = point.get("frame_offset",
                             rawd._frame_offset_for(dataset, point.get("window_mode", "one_turn_from_start")))
    cmd = [python, str(script), "--model", model,
           "--timing-contract", rawd.TIMING_CONTRACT,
           "--delay-seconds", str(point.get("delay_seconds", 0.0)),
           "--frame-offset", str(frame_offset)]
    if fixation_root:
        cmd += ["--fixation-root", str(fixation_root)]
    cmd += ["--fixation-data-tag", rawd.FIXATION_DATA_TAG]
    if dataset.startswith("meshmamba"):
        cmd += ["--texture-type", "non_texture" if dataset.endswith("non_texture") else "rgb_texture"]
    if method == "cone":
        cmd += ["--sigma-deg", str(point["sigma_deg"])]
        if point.get("radius_sigma_mult") is not None:
            cmd += ["--radius-sigma-mult", str(point["radius_sigma_mult"])]
    else:
        if point.get("sigma_px") not in (None, ""):
            cmd += ["--sigma-px", str(point["sigma_px"])]
        elif point.get("sigma_screen") not in (None, ""):
            cmd += ["--sigma-screen", str(point["sigma_screen"])]
    tag = f"sweep_{point['axis']}{point['value']}".replace(".", "p")
    cmd += ["--output-dir", str(output_dir), "--tag", tag]
    return cmd


def _extract_hit_rate(report: dict, leaf: dict | None, method: str):
    if method == "screen_space":
        return None
    for src in (leaf, report):
        if isinstance(src, dict) and src.get("hit_rate") not in (None, ""):
            return src["hit_rate"]
    section = report.get("metrics_vs_gt")
    if isinstance(section, dict):
        node = section.get("cone_gaussian_on_mesh")
        if isinstance(node, dict) and node.get("hit_rate") not in (None, ""):
            return node["hit_rate"]
    return None


def _task_dir_leaf(point: dict) -> str:
    raw = point.get("task_tag")
    if raw in (None, ""):
        raw = f"{point['method']}_{point['axis']}{point['value']}"
    return re.sub(r"[^A-Za-z0-9._=-]+", "_", str(raw))


def subprocess_evaluator_invoke(point: dict, model: str, *, work_dir: Path,
                                fixation_root: str | None = None, timeout: int | None = None,
                                preflight: bool = True, env: dict | None = None,
                                python: str | None = None,
                                nice_prefix: list[str] | None = None) -> dict:
    """Default REAL invoke: run the evaluator CLI for (point, model), parse its
    report, and return a per-model 14-metric row. Requires the external dataset
    assets to actually run; on any subprocess failure returns a status='failed'
    row. With `preflight=True` (default) it FAILS FAST with a `PreflightError`
    (actionable, listing missing roots/env vars) before invoking anything."""
    python = python or os.environ.get("REPROJECT_PYTHON", sys.executable)
    injected_env = dict(env or {})
    preflight_env = dict(os.environ, **injected_env)
    resolved_env = dict(injected_env)
    if preflight:
        resolved_env = pf.resolved_env(
            pf.require(
                point["dataset"], point["method"],
                fixation_root=fixation_root, env=preflight_env,
            )
        )
        pf.require_runtime_dependencies(point["method"], python=python)
    out_dir = (Path(work_dir) / "per_task" / point["dataset"] / model / _task_dir_leaf(point))
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = build_evaluator_command(
        point, model, output_dir=out_dir, fixation_root=fixation_root, python=python,
    )
    if nice_prefix:
        cmd = list(nice_prefix) + cmd
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            env=dict(os.environ, **resolved_env),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"model": model, "status": "failed", "error_type": type(exc).__name__,
                "error_message": str(exc)[:500]}
    if proc.returncode != 0:
        return {"model": model, "status": "failed", "error_type": "evaluator_nonzero",
                "error_message": (proc.stderr or "")[-500:]}
    report_path = rawd._select_report(out_dir)
    if report_path is None:
        return {"model": model, "status": "failed", "error_type": "no_report"}
    report = json.loads(report_path.read_text())
    leaf = rawd.extract_metrics(report, point["dataset"], point["method"])
    if leaf is None:
        return {"model": model, "status": "failed", "error_type": "no_metrics"}
    row = {"model": model, "status": "ok"}
    row.update({k: leaf.get(k) for k in _SOURCE_METRIC_KEYS})
    hit = _extract_hit_rate(report, leaf, point["method"])
    if hit is not None:
        row["hit_rate"] = hit
    return row


def _default_make_params(point: dict, stage: str, base_params: dict | None) -> dict:
    params = {
        "stage_name": stage, "dataset": point["dataset"], "method": point["method"],
        "timing_contract": "one_turn_from_start", "window_mode": point.get("window_mode", "one_turn_from_start"),
        "delay_seconds": point.get("delay_seconds", 0.0),
        point["axis"]: point["value"],
        "command": f"python3 test/launch/run_evaluator_sweep.py  # {point['axis']}={point['value']}",
        "notes": "evaluator-backed per-point run",
    }
    if point.get("radius_sigma_mult") is not None:
        params["radius_sigma_mult"] = point["radius_sigma_mult"]
    if base_params:
        params.update(base_params)
    return params


def run_evaluator_sweep(points: Sequence[dict], models: Sequence[str], results_root: Path, *,
                        invoke: EvaluatorInvoke, stage: str = "evaluator_sweep",
                        base_params: dict | None = None, make_params: Callable[[dict], dict] | None = None,
                        on_duplicate: str = "error", enrich_kld: bool = True) -> list[Path]:
    """For each point: invoke the evaluator per model, collect per-model rows, and
    record the point through the aggregation layer. Returns per-point run dirs.

    When `enrich_kld` (default), each per-model row is passed through
    `dual_kld.enrich_row_with_dual_kld`: rows that carry pred/GT arrays get both
    `KLD_evaluator` and `KLD_trusted` computed from those same inputs; rows without
    arrays keep `KLD_evaluator` = their stored `KLD` and leave `KLD_trusted` absent.
    This is the real local producer path that propagates both KLDs end-to-end."""
    run_dirs: list[Path] = []
    for point in points:
        rows = [invoke(point, model) for model in models]
        if enrich_kld:
            rows = [dk.enrich_row_with_dual_kld(r) for r in rows]
        params = make_params(point) if make_params else _default_make_params(point, stage, base_params)
        run_dirs.append(agg.record_run(results_root, params, rows,
                                       command=str(params.get("command", "")), on_duplicate=on_duplicate))
    return run_dirs


def make_mock_invoke() -> EvaluatorInvoke:
    """Deterministic NON-STATIC mock: metrics depend on the point's sigma value (and
    model), so different points yield different aggregate metrics — without needing
    the external dataset. Used by tests and the `--mock` CLI example."""
    def invoke(point: dict, model: str) -> dict:
        v = float(point["value"])
        # Process-STABLE per-model perturbation (sha1, not the salted built-in hash())
        # so two separate interpreter runs produce identical metrics for the same args.
        bump = (int(hashlib.sha1(model.encode()).hexdigest(), 16) % 5) * 0.01
        cc = round(0.30 + 0.10 * v + bump, 4)
        # Deterministic synthetic pred/GT arrays (seed from sha1(model,sigma), not
        # the salted hash()) so the dual-KLD enrichment can compute BOTH KLDs from
        # real arrays. `KLD` itself is intentionally not fabricated here — the
        # enrichment derives KLD/KLD_evaluator/KLD_trusted from these inputs.
        seed = int(hashlib.sha1(f"{model}:{v}".encode()).hexdigest(), 16) % (2 ** 32)
        rng = np.random.default_rng(seed)
        pred = rng.normal(0.3, 1.0, size=512)
        gt = (0.5 + 0.1 * v) * pred + rng.normal(0.0, 0.8, size=512)
        row = {
            "model": model, "status": "ok",
            "CC": cc, "SIM": round(0.50 + 0.05 * v, 4),
            "MSE": round(0.05 - 0.005 * v, 4), "MAE": 0.12, "Spearman": round(cc - 0.05, 4),
            "Cosine": round(cc + 0.10, 4),
            "AUC_Judd_gt_top_10pct_proxy": round(0.70 + 0.02 * v, 4),
            "AUC_Judd_gt_top_5pct_proxy": round(0.74 + 0.02 * v, 4),
            "AUC_Judd_gt_top_1pct_proxy": round(0.80 + 0.02 * v, 4),
            "NSS_gt_top_10pct_proxy": round(0.90 + 0.05 * v, 4),
            "NSS_gt_top_5pct_proxy": round(1.10 + 0.05 * v, 4),
            "NSS_gt_top_1pct_proxy": round(1.40 + 0.05 * v, 4),
            "pred": pred, "gt": gt,
        }
        if point["method"] == "cone":
            row["hit_rate"] = round(0.85 + 0.01 * v, 4)
        return row
    return invoke


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluator-backed local per-point sigma sweep.")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--method", required=True, choices=["cone", "screen_space"])
    ap.add_argument("--models", required=True, help="comma-separated model names")
    ap.add_argument("--sigma-param", default="sigma_deg", choices=["sigma_deg", "sigma_px", "sigma_screen"])
    ap.add_argument("--sigma-values", required=True, help="comma-separated, e.g. 0.8,1.0,2.0")
    ap.add_argument("--radius-sigma-mult", default=None)
    ap.add_argument("--stage", default="evaluator_sweep")
    ap.add_argument("--results-root", type=Path, default=Path("results"))
    ap.add_argument("--fixation-root", default=None)
    ap.add_argument("--on-duplicate", default="error", choices=["error", "supersede", "allow"])
    ap.add_argument("--mock", action="store_true",
                    help="Use the deterministic non-static mock invoke (no real evaluator run; "
                         "for local demonstration without the external dataset assets).")
    args = ap.parse_args()

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    values = [float(x) for x in str(args.sigma_values).split(",") if x.strip()]
    rsm = float(args.radius_sigma_mult) if args.radius_sigma_mult else None
    points = make_sigma_grid(args.dataset, args.method, sigma_param=args.sigma_param,
                             sigma_values=values, radius_sigma_mult=rsm)

    if args.mock:
        invoke: EvaluatorInvoke = make_mock_invoke()
    else:
        try:  # fail fast with an actionable message before doing any work
            pf.require(args.dataset, args.method, fixation_root=args.fixation_root)
        except pf.PreflightError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        work = args.results_root / "ablation" / "_work" / args.stage
        def invoke(point, model):  # type: ignore[misc]
            return subprocess_evaluator_invoke(point, model, work_dir=work, fixation_root=args.fixation_root)

    run_dirs = run_evaluator_sweep(points, models, args.results_root, invoke=invoke,
                                   stage=args.stage, on_duplicate=args.on_duplicate)
    for d in run_dirs:
        print(f"[eval-sweep] {d}")
    print(f"[eval-sweep] {len(run_dirs)} points -> {run_dirs[0].parents[1] / 'aggregate' / 'ablation_runs.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
