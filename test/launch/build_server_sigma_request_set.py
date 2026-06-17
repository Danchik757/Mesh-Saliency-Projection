"""Build a reproducible set of sigma-branch request + server-manifest files.

This is a thin batch wrapper over:
  - build_dataset_ablation_request.py
  - dataset_ablation_server.py

It is intentionally conservative:
  - sigma stage only;
  - one request per (dataset, method);
  - subset = full canonical dataset_model_info inventory;
  - low-priority server contract only (emit manifests, never launch).
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

ALL_DATASETS = ("3dva", "meshmamba_non_texture", "meshmamba_rgb_texture", "sal3d")
ALL_METHODS = ("screen_space", "cone")


def _request_filename(dataset: str, method: str) -> str:
    return f"{dataset}_{method}_sigma.json"


def _manifest_filename(dataset: str, method: str) -> str:
    return f"{dataset}_{method}_sigma.server_manifest.json"


def _subset_name(dataset: str) -> str:
    return f"{dataset}_all_models_rc4"


def _resolved_env_pairs(args, dataset: str) -> list[str]:
    base = [f"FIXATION_ROOT={args.fixation_root}"]
    if dataset == "3dva":
        return [
            *base,
            f"THREE_DVA_JSON_ROOT={args.three_dva_json_root}",
            f"THREE_DVA_COMBINED_GT_DIR={args.three_dva_combined_gt_dir}",
        ]
    if dataset == "meshmamba_non_texture":
        return [
            *base,
            f"MESHMAMBA_JSON_ROOT={args.meshmamba_json_root}",
            f"MESHMAMBA_NON_TEXTURE_ROOT={args.meshmamba_non_texture_root}",
        ]
    if dataset == "meshmamba_rgb_texture":
        return [
            *base,
            f"MESHMAMBA_RGB_TEXTURE_JSON_ROOT={args.meshmamba_rgb_json_root}",
            f"MESHMAMBA_RGB_TEXTURE_ROOT={args.meshmamba_rgb_texture_root}",
        ]
    if dataset == "sal3d":
        return [
            *base,
            f"SAL3D_JSON_ROOT={args.sal3d_json_root}",
            f"SAL3D_DATASET_ROOT={args.sal3d_dataset_root}",
            f"SAL3D_FIXED_GT_DIR={args.sal3d_fixed_gt_dir}",
            f"SAL3D_MANIFEST={args.sal3d_manifest}",
        ]
    raise ValueError(f"unsupported dataset {dataset!r}")


def _request_args(args, *, dataset: str, method: str, out: Path):
    return argparse.Namespace(
        dataset=dataset,
        method=method,
        stage="sigma",
        out=out,
        subset_name=_subset_name(dataset),
        models=None,
        limit_models=None,
        repo_commit=args.repo_commit,
        release_tag=args.release_tag,
        fixation_data_tag=args.fixation_data_tag,
        timing_contract=args.timing_contract,
        window_mode=args.window_mode,
        fixed_delay_seconds=args.fixed_delay_seconds,
        fixed_frame_offset=args.fixed_frame_offset,
        fixed_sigma_value=None,
        axis_values=None,
        no_refined=args.no_refined,
        resolved_env=_resolved_env_pairs(args, dataset),
        python=args.python,
        timeout_seconds_per_invocation=args.timeout_seconds_per_invocation,
        checkout_root=args.checkout_root,
    )


def build_request_and_manifest(args, *, dataset: str, method: str) -> tuple[Path, Path]:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    request_path = out_dir / _request_filename(dataset, method)
    request = builder.build_request(_request_args(args, dataset=dataset, method=method, out=request_path))
    request_path.write_text(json.dumps(request, indent=2))

    manifest = server.build_server_manifest(
        request,
        host=args.host,
        results_root=args.results_root,
        request_path=str(Path(args.request_root_on_server) / request_path.name),
        checkout_root=args.checkout_root,
        repo_url=args.repo_url,
        python=args.python,
    )
    manifest_path = out_dir / _manifest_filename(dataset, method)
    server.write_server_manifest(manifest, manifest_path)
    return request_path, manifest_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the full sigma request/manifest set for one server preset.")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--host", required=True, choices=server.APPROVED_HOSTS)
    ap.add_argument("--checkout-root", required=True)
    ap.add_argument("--request-root-on-server", required=True,
                    help="server-side directory that will contain the emitted request JSONs")
    ap.add_argument("--results-root", required=True)
    ap.add_argument("--repo-url", default=None)
    ap.add_argument("--python", default="python3")
    ap.add_argument("--timeout-seconds-per-invocation", type=int, default=3600)
    ap.add_argument("--repo-commit", default=None)
    ap.add_argument("--release-tag", default="v2.0-data-rc4")
    ap.add_argument("--fixation-data-tag", default="processed_fixations_offset0_full_cleaned")
    ap.add_argument("--timing-contract", default="one_turn_from_start")
    ap.add_argument("--window-mode", default="one_turn_from_start")
    ap.add_argument("--fixed-delay-seconds", type=float, default=0.0)
    ap.add_argument("--fixed-frame-offset", type=int, default=0)
    ap.add_argument("--fixation-root", required=True)
    ap.add_argument("--three-dva-json-root", required=True)
    ap.add_argument("--three-dva-combined-gt-dir", required=True)
    ap.add_argument("--meshmamba-json-root", required=True)
    ap.add_argument("--meshmamba-rgb-json-root", required=True)
    ap.add_argument("--meshmamba-non-texture-root", required=True)
    ap.add_argument("--meshmamba-rgb-texture-root", required=True)
    ap.add_argument("--sal3d-json-root", required=True)
    ap.add_argument("--sal3d-dataset-root", required=True)
    ap.add_argument("--sal3d-fixed-gt-dir", required=True)
    ap.add_argument("--sal3d-manifest", required=True)
    ap.add_argument("--no-refined", action="store_true")
    ap.add_argument("--datasets", nargs="*", choices=ALL_DATASETS, default=list(ALL_DATASETS))
    ap.add_argument("--methods", nargs="*", choices=ALL_METHODS, default=list(ALL_METHODS))
    args = ap.parse_args()

    built: list[tuple[str, str, Path, Path]] = []
    for dataset in args.datasets:
        for method in args.methods:
            req, manifest = build_request_and_manifest(args, dataset=dataset, method=method)
            built.append((dataset, method, req, manifest))

    print(f"[dmlab-sigma-set] built {len(built)} branch contracts in {args.out_dir}")
    for dataset, method, req, manifest in built:
        print(f"[dmlab-sigma-set] {dataset}/{method}")
        print(f"  request : {req}")
        print(f"  manifest: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
