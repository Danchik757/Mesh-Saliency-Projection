"""Dataset-method ablation launcher for `cone`.

Selects sigma_deg per (dataset, method) on the common model set (NOT per model),
then can run timing / frame_offset on the chosen sigma. Thin wrapper over
`dataset_ablation_core`; grids + sigma handling reuse `cone_sigma_launcher` so the
grids stay single-sourced.

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
cs = _load("cone_sigma_launcher")

METHOD = "cone"
SIGMA_PARAM = "sigma_deg"


def _expand_sigma(dataset: str, sigma_deg: float) -> dict:
    """sigma_deg -> {sigma_deg, radius_sigma_mult}; dataset-independent for cone."""
    return {"sigma_deg": float(sigma_deg), "radius_sigma_mult": float(cs.RADIUS_SIGMA_MULT)}


def build_spec() -> "core.MethodSpec":
    return core.MethodSpec(
        method=METHOD,
        sigma_param=SIGMA_PARAM,
        coarse_grid=tuple(cs.COARSE_GRID),
        refined_coefs=tuple(cs.REFINED_COEFS),
        expand_sigma=_expand_sigma,
        refined_grid=lambda s: cs.refined_grid(s),
    )


def run(request: dict, *, results_root: Path, invoke, update_table: bool = True) -> dict:
    return core.run_branch(request, build_spec(), results_root=results_root,
                           invoke=invoke, update_table=update_table)


def main() -> int:
    ap = argparse.ArgumentParser(description="cone dataset-method ablation launcher.")
    ap.add_argument("--request", type=Path, required=True, help="path to a branch request JSON")
    ap.add_argument("--results-root", type=Path, default=Path("results"))
    ap.add_argument("--mock", action="store_true", help="use the deterministic mock invoke")
    ap.add_argument("--validate-only", action="store_true",
                    help="validate the request only; do not execute")
    ap.add_argument("--dry-run", action="store_true",
                    help="validate + plan candidates and print, run nothing")
    ap.add_argument("--skip-runtime-check", action="store_true",
                    help="skip repo/runtime gate in non-mock mode (review/dev only)")
    args = ap.parse_args()

    request = json.loads(args.request.read_text())
    spec = build_spec()
    try:
        core.validate_request(request)
    except core.BranchError as exc:
        print(f"[cone-dmlab] REQUEST INVALID: {exc}", file=sys.stderr)
        return 2

    if args.validate_only:
        print("[cone-dmlab] request OK")
        return 0

    if args.dry_run:
        cands = core.plan_candidates(request, spec)
        ctx = core.comparability_context(request)
        print(f"[cone-dmlab] dataset={request['dataset']} method={METHOD} stage={request['stage']}")
        print(f"[cone-dmlab] comparability_signature={core.comparability_signature(ctx)}")
        print(f"[cone-dmlab] {len(cands)} candidate(s): "
              + ", ".join(c.candidate_id for c in cands))
        print(f"[cone-dmlab] subset={request['subset_name']} size={len(request['models'])}")
        return 0

    if args.mock:
        invoke = ev.make_mock_invoke()
    else:
        try:
            if not args.skip_runtime_check:
                core._require_current_checkout_commit(request)
                core._require_request_runtime(request, spec)
        except (core.RuntimeGateError, core.pf.PreflightError, core.BranchError) as exc:
            print(f"[cone-dmlab] RUNTIME GATE FAILED: {exc}", file=sys.stderr)
            return 2
        invoke = core._real_invoke_for_request(request, spec, results_root=args.results_root)

    result = run(request, results_root=args.results_root, invoke=invoke)
    verdict = "PROMOTED" if result["promoted"] else "HELD"
    print(f"[cone-dmlab] {verdict} branch_dir={result['branch_dir']}")
    print(f"[cone-dmlab] dataset_method_table={result['dataset_method_table_path']}")
    return 0 if result["promoted"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
