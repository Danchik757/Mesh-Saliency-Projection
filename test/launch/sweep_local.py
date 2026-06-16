"""Local per-point sweep runner over the ablation aggregation layer (PROTOTYPE).

NON-DESTRUCTIVE, LOCAL ONLY. This enumerates a small parameter grid and, for each
point, obtains per-model 14-metric rows from a provider and records the point
through `ablation_aggregation.record_run(...)`, producing the spec aggregate
layout with one aggregate row + one run directory per grid point.

It is an *orchestration prototype*, NOT the real evaluator-backed runner:
  - it does NOT execute the baseline evaluators per parameter point;
  - metric *values* come from an existing local source (or a caller provider), so
    when the same source is reused across points the metrics are identical and
    only the per-point parameters (e.g. `sigma_deg`) and the run identity vary.
The real runner (future, possibly server-backed) would re-evaluate per point to
produce genuinely different metrics. See the report's "what still separates this"
note.

It imports/modifies no baseline evaluator. It reuses the sibling
`ablation_aggregation.py` and `import_reference_long.py` modules.
"""
from __future__ import annotations

import argparse
import importlib.util
from collections.abc import Callable, Sequence
from pathlib import Path

_DIR = Path(__file__).resolve().parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


imp = _load("import_reference_long")
agg = imp.agg  # the loaded ablation_aggregation module


def enumerate_grid(*, datasets: Sequence[str], methods: Sequence[str],
                   axis: str, values: Sequence) -> list[dict]:
    """Cartesian product -> one point dict per (dataset, method, axis value).
    `cone` and `screen_space` stay separate points (separate aggregate branches)."""
    return [{"dataset": d, "method": m, "axis": axis, "value": v}
            for d in datasets for m in methods for v in values]


def run_sweep(points: Sequence[dict], results_root: Path, *,
              provider: Callable[[dict], list[dict]],
              make_params: Callable[[dict], dict],
              on_duplicate: str = "error") -> list[Path]:
    """For each point: get per-model rows from `provider`, build params with
    `make_params`, and `record_run`. Returns the per-point run directories."""
    run_dirs: list[Path] = []
    for point in points:
        rows = provider(point)
        params = make_params(point)
        run_dirs.append(agg.record_run(
            results_root, params, rows,
            command=str(params.get("command", "")), on_duplicate=on_duplicate))
    return run_dirs


def run_reference_sigma_sweep(source_csv: Path, results_root: Path, *, dataset: str, method: str,
                              sigma_values: Sequence[float], sigma_param: str = "sigma_deg",
                              radius_sigma_mult: float | None = None, stage: str = "sweep_demo_sigma",
                              texture_type: str | None = None, on_duplicate: str = "error") -> list[Path]:
    """Sweep one sigma axis for a single (dataset, method) using rows from an
    accepted reference long CSV. Real rows; identical across points (the prototype
    does not re-evaluate per sigma), so only `sigma_param` and run identity vary."""
    rows = imp.load_reference_long(source_csv, method=method, texture_type=texture_type)
    points = enumerate_grid(datasets=[dataset], methods=[method], axis=sigma_param, values=sigma_values)

    def provider(_point: dict) -> list[dict]:
        return rows

    def make_params(point: dict) -> dict:
        extra = {point["axis"]: point["value"],
                 "command": (f"python3 test/launch/sweep_local.py --source-csv {source_csv} "
                             f"--dataset {dataset} --method {method} --sigma-param {sigma_param} "
                             f"--sigma-values <grid>  # point {point['axis']}={point['value']}")}
        if radius_sigma_mult is not None:
            extra["radius_sigma_mult"] = radius_sigma_mult
        return imp.build_reference_params(source_csv, rows, dataset=point["dataset"],
                                          method=point["method"], stage=stage,
                                          texture_type=texture_type or "", extra=extra)

    return run_sweep(points, results_root, provider=provider, make_params=make_params,
                     on_duplicate=on_duplicate)


def main() -> int:
    ap = argparse.ArgumentParser(description="Local per-point sigma sweep over an accepted reference source.")
    ap.add_argument("--source-csv", type=Path, required=True)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--method", required=True, choices=["cone", "screen_space"])
    ap.add_argument("--sigma-param", default="sigma_deg", choices=["sigma_deg", "sigma_px", "sigma_screen"])
    ap.add_argument("--sigma-values", required=True, help="comma-separated, e.g. 0.8,1.0,2.0")
    ap.add_argument("--radius-sigma-mult", default=None)
    ap.add_argument("--stage", default="sweep_demo_sigma")
    ap.add_argument("--results-root", type=Path, default=Path("results"))
    ap.add_argument("--texture-type", default=None)
    ap.add_argument("--on-duplicate", default="error", choices=["error", "supersede", "allow"])
    args = ap.parse_args()

    values = [float(x) for x in str(args.sigma_values).split(",") if x.strip()]
    rsm = float(args.radius_sigma_mult) if args.radius_sigma_mult else None
    run_dirs = run_reference_sigma_sweep(
        args.source_csv, args.results_root, dataset=args.dataset, method=args.method,
        sigma_values=values, sigma_param=args.sigma_param, radius_sigma_mult=rsm,
        stage=args.stage, texture_type=args.texture_type, on_duplicate=args.on_duplicate)
    for d in run_dirs:
        print(f"[sweep] {d}")
    agg_csv = run_dirs[0].parents[1] / "aggregate" / "ablation_runs.csv"
    print(f"[sweep] {len(run_dirs)} points -> {agg_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
