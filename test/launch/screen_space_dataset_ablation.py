"""Dataset-method ablation launcher for `screen_space`.

Selects sigma_multiplier per (dataset, method) on the common model set (NOT per
model), then can run timing / frame_offset on the chosen sigma. Thin wrapper over
`dataset_ablation_core`; the per-method knobs (grid, sigma expansion) are reused
from the existing `screen_space_sigma_launcher` so the grids stay single-sourced.

Local / dry-run by default. No server launch. No evaluator formula is changed.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent


def _load(name: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


core = _load("dataset_ablation_core")
ev = _load("run_evaluator_sweep")
ss = _load("screen_space_sigma_launcher")

METHOD = "screen_space"
SIGMA_PARAM = "sigma_multiplier"


def _expand_sigma(dataset: str, sigma_multiplier: float) -> dict:
    """multiplier -> {sigma_multiplier, sigma_px|sigma_screen} for the dataset."""
    absolute = ss._absolute_sigma_mapping(dataset, float(sigma_multiplier))
    out = {"sigma_multiplier": float(sigma_multiplier)}
    out.update(absolute)
    return out


def build_spec() -> "core.MethodSpec":
    return core.MethodSpec(
        method=METHOD,
        sigma_param=SIGMA_PARAM,
        coarse_grid=tuple(ss.COARSE_GRID),
        refined_coefs=tuple(ss.REFINED_COEFS),
        expand_sigma=_expand_sigma,
        refined_grid=lambda s: ss.refined_grid(s),
    )


def run(request: dict, *, results_root: Path, invoke, update_table: bool = True) -> dict:
    return core.run_branch(request, build_spec(), results_root=results_root,
                           invoke=invoke, update_table=update_table)


def main() -> int:
    ap = argparse.ArgumentParser(description="screen_space dataset-method ablation launcher.")
    ap.add_argument("--request", type=Path, required=True, help="path to a branch request JSON")
    ap.add_argument("--results-root", type=Path, default=Path("results"))
    ap.add_argument("--mock", action="store_true", help="use the deterministic mock invoke")
    ap.add_argument("--dry-run", action="store_true",
                    help="validate + plan candidates and print, run nothing")
    args = ap.parse_args()

    request = json.loads(args.request.read_text())
    spec = build_spec()
    try:
        core.validate_request(request)
    except core.BranchError as exc:
        print(f"[ss-dmlab] REQUEST INVALID: {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        cands = core.plan_candidates(request, spec)
        ctx = core.comparability_context(request)
        print(f"[ss-dmlab] dataset={request['dataset']} method={METHOD} stage={request['stage']}")
        print(f"[ss-dmlab] comparability_signature={core.comparability_signature(ctx)}")
        print(f"[ss-dmlab] {len(cands)} candidate(s): "
              + ", ".join(c.candidate_id for c in cands))
        print(f"[ss-dmlab] subset={request['subset_name']} size={len(request['models'])}")
        return 0

    if not args.mock:
        print("[ss-dmlab] real evaluator runs need assets + explicit approval; "
              "use --mock for a local dry execution", file=sys.stderr)
        return 2

    result = run(request, results_root=args.results_root, invoke=ev.make_mock_invoke())
    verdict = "PROMOTED" if result["promoted"] else "HELD"
    print(f"[ss-dmlab] {verdict} branch_dir={result['branch_dir']}")
    print(f"[ss-dmlab] dataset_method_table={result['dataset_method_table_path']}")
    return 0 if result["promoted"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
