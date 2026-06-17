"""Build a timing or frame_offset branch request from an upstream branch_best.json.

Usage pattern:

  # After sigma completes → build timing request:
  python3 test/launch/build_downstream_request.py timing \
    --sigma-best results/ablation/.../branch_best.json \
    --out-dir coordination/requests/dmlab/vg_iai \
    --host vg-iai \
    --checkout-root /mnt/ssd1/... --request-root-on-server /mnt/... --results-root /mnt/...

  # After timing completes → build frame_offset request:
  python3 test/launch/build_downstream_request.py frame_offset \
    --sigma-best results/ablation/.../screen_space_sigma_dmlab/.../branch_best.json \
    --timing-best results/ablation/.../screen_space_timing_dmlab/.../branch_best.json \
    --out-dir ... ...

The script reads best_params from the upstream branch_best.json files, derives the
fixed sigma (and delay for frame_offset), applies the canonical downstream grid, and
emits a request JSON + server manifest that can be submitted immediately.
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


builder = _load("build_dataset_ablation_request")
server = _load("dataset_ablation_server")


# Canonical downstream grids — same as the family launchers.
TIMING_GRID: tuple[float, ...] = (
    -3.0, -2.5, -1.5, -0.5, -0.2, -0.1, 0.0, 0.1, 0.2, 0.5, 1.5, 2.5, 3.0
)
FRAME_OFFSET_GRID: tuple[int, ...] = (0, 15, 30, 54, 90, 120)


class DownstreamBuildError(ValueError):
    """Raised when a downstream request cannot be built from the given inputs."""


def _load_best(path: Path, *, expected_stage: str | None = None) -> dict:
    if not path.is_file():
        raise DownstreamBuildError(f"branch_best not found: {path}")
    data = json.loads(path.read_text())
    if expected_stage and data.get("stage") != expected_stage:
        raise DownstreamBuildError(
            f"{path}: expected stage={expected_stage!r}, got {data.get('stage')!r}")
    if "best_params" not in data:
        raise DownstreamBuildError(f"{path}: missing 'best_params'")
    return data


def _sigma_value(best: dict, method: str) -> float:
    bp = best["best_params"]
    if method == "cone":
        if "sigma_deg" not in bp:
            raise DownstreamBuildError(f"cone best_params missing 'sigma_deg': {bp}")
        return float(bp["sigma_deg"])
    if method == "screen_space":
        if "sigma_multiplier" not in bp:
            raise DownstreamBuildError(f"screen_space best_params missing 'sigma_multiplier': {bp}")
        return float(bp["sigma_multiplier"])
    raise DownstreamBuildError(f"unsupported method {method!r}")


def _delay_value(best: dict) -> float:
    bp = best["best_params"]
    if "delay_seconds" not in bp:
        raise DownstreamBuildError(f"timing best_params missing 'delay_seconds': {bp}")
    return float(bp["delay_seconds"])


def build_timing_request(sigma_best_path: Path, args) -> tuple[Path, Path]:
    sigma_best = _load_best(sigma_best_path, expected_stage="sigma")
    method = sigma_best["method"]
    dataset = sigma_best["dataset"]
    sigma_val = _sigma_value(sigma_best, method)
    fixed_fo = int(sigma_best["best_params"].get("frame_offset", 0))

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = f"{dataset}_{method}_timing"
    req_path = out_dir / f"{stem}.json"

    req_args = argparse.Namespace(
        dataset=dataset,
        method=method,
        stage="timing",
        out=req_path,
        subset_name=args.subset_name or sigma_best.get("subset_name") or f"{dataset}_all_models_rc4",
        models=None,
        limit_models=None,
        repo_commit=args.repo_commit or sigma_best.get("repo_commit"),
        release_tag=args.release_tag,
        fixation_data_tag=args.fixation_data_tag,
        timing_contract=args.timing_contract,
        window_mode=args.window_mode,
        fixed_delay_seconds=0.0,
        fixed_frame_offset=fixed_fo,
        fixed_sigma_value=sigma_val,
        axis_values=[str(v) for v in (args.timing_grid or list(TIMING_GRID))],
        no_refined=False,
        resolved_env=[],
        python=None,
        timeout_seconds_per_invocation=None,
        checkout_root=None,
    )
    request = builder.build_request(req_args)
    req_path.write_text(json.dumps(request, indent=2))

    manifest = server.build_server_manifest(
        request,
        host=args.host,
        results_root=args.results_root,
        request_path=str(Path(args.request_root_on_server) / req_path.name),
        checkout_root=args.checkout_root,
        repo_url=getattr(args, "repo_url", None),
        python=getattr(args, "python", "python3") or "python3",
    )
    manifest_path = out_dir / f"{stem}.server_manifest.json"
    server.write_server_manifest(manifest, manifest_path)
    return req_path, manifest_path


def build_frame_offset_request(sigma_best_path: Path, timing_best_path: Path, args) -> tuple[Path, Path]:
    sigma_best = _load_best(sigma_best_path, expected_stage="sigma")
    timing_best = _load_best(timing_best_path, expected_stage="timing")
    method = sigma_best["method"]
    dataset = sigma_best["dataset"]

    if timing_best["method"] != method or timing_best["dataset"] != dataset:
        raise DownstreamBuildError(
            f"sigma and timing branch_best mismatch: "
            f"sigma=({sigma_best['dataset']}/{sigma_best['method']}) "
            f"timing=({timing_best['dataset']}/{timing_best['method']})"
        )

    sigma_val = _sigma_value(sigma_best, method)
    delay_val = _delay_value(timing_best)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = f"{dataset}_{method}_frame_offset"
    req_path = out_dir / f"{stem}.json"

    req_args = argparse.Namespace(
        dataset=dataset,
        method=method,
        stage="frame_offset",
        out=req_path,
        subset_name=args.subset_name or sigma_best.get("subset_name") or f"{dataset}_all_models_rc4",
        models=None,
        limit_models=None,
        repo_commit=args.repo_commit or sigma_best.get("repo_commit"),
        release_tag=args.release_tag,
        fixation_data_tag=args.fixation_data_tag,
        timing_contract=args.timing_contract,
        window_mode=args.window_mode,
        fixed_delay_seconds=delay_val,
        fixed_frame_offset=0,
        fixed_sigma_value=sigma_val,
        axis_values=[str(v) for v in (args.frame_offset_grid or list(FRAME_OFFSET_GRID))],
        no_refined=False,
        resolved_env=[],
        python=None,
        timeout_seconds_per_invocation=None,
        checkout_root=None,
    )
    request = builder.build_request(req_args)
    req_path.write_text(json.dumps(request, indent=2))

    manifest = server.build_server_manifest(
        request,
        host=args.host,
        results_root=args.results_root,
        request_path=str(Path(args.request_root_on_server) / req_path.name),
        checkout_root=args.checkout_root,
        repo_url=getattr(args, "repo_url", None),
        python=getattr(args, "python", "python3") or "python3",
    )
    manifest_path = out_dir / f"{stem}.server_manifest.json"
    server.write_server_manifest(manifest, manifest_path)
    return req_path, manifest_path


def _common_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--host", required=True, choices=server.APPROVED_HOSTS)
    ap.add_argument("--checkout-root", required=True)
    ap.add_argument("--request-root-on-server", required=True)
    ap.add_argument("--results-root", required=True)
    ap.add_argument("--repo-url", default=None)
    ap.add_argument("--python", default="python3")
    ap.add_argument("--repo-commit", default=None,
                    help="override repo_commit; defaults to the value in sigma_best")
    ap.add_argument("--subset-name", default=None,
                    help="override subset_name; defaults to the value in sigma_best")
    ap.add_argument("--release-tag", default="v2.0-data-rc4")
    ap.add_argument("--fixation-data-tag", default="processed_fixations_offset0_full_cleaned")
    ap.add_argument("--timing-contract", default="one_turn_from_start")
    ap.add_argument("--window-mode", default="one_turn_from_start")


def main() -> int:
    ap = argparse.ArgumentParser(description="Build a downstream stage request from upstream branch_best.json.")
    sub = ap.add_subparsers(dest="stage", required=True)

    pt = sub.add_parser("timing", help="build timing request from sigma branch_best")
    pt.add_argument("--sigma-best", type=Path, required=True, metavar="BRANCH_BEST_JSON")
    pt.add_argument("--timing-grid", nargs="*", type=float, default=None,
                    help=f"delay_seconds sweep; default: {list(TIMING_GRID)}")
    _common_args(pt)

    pf = sub.add_parser("frame_offset", help="build frame_offset request from sigma+timing branch_bests")
    pf.add_argument("--sigma-best", type=Path, required=True, metavar="BRANCH_BEST_JSON")
    pf.add_argument("--timing-best", type=Path, required=True, metavar="BRANCH_BEST_JSON")
    pf.add_argument("--frame-offset-grid", nargs="*", type=int, default=None,
                    help=f"frame_offset sweep; default: {list(FRAME_OFFSET_GRID)}")
    _common_args(pf)

    args = ap.parse_args()

    try:
        if args.stage == "timing":
            req, manifest = build_timing_request(args.sigma_best, args)
            _print_result(args.stage, req, manifest)
        else:
            req, manifest = build_frame_offset_request(args.sigma_best, args.timing_best, args)
            _print_result(args.stage, req, manifest)
    except (DownstreamBuildError, builder.RequestBuildError, server.ServerError) as exc:
        print(f"[dmlab-downstream] BUILD FAILED: {exc}", file=sys.stderr)
        return 2
    return 0


def _print_result(stage: str, req: Path, manifest: Path) -> None:
    print(f"[dmlab-downstream] stage={stage}")
    print(f"[dmlab-downstream] request : {req}")
    print(f"[dmlab-downstream] manifest: {manifest}")
    data = json.loads(manifest.read_text())
    print(f"[dmlab-downstream] RUN ON SERVER:\n  {data['command_str']}")


if __name__ == "__main__":
    raise SystemExit(main())
