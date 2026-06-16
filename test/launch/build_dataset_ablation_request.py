"""Build dataset-level ablation request JSONs from canonical model indexes.

This avoids hand-written branch requests for the dmlab launchers. It does not
launch anything; it only materializes the request payload that
`screen_space_dataset_ablation.py` / `cone_dataset_ablation.py` consume.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _DIR.parents[1]


def _load(name: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


core = _load("dataset_ablation_core")
ss = _load("screen_space_dataset_ablation")
cone = _load("cone_dataset_ablation")

MODEL_INDEX = {
    "3dva": _REPO_ROOT / "jsons" / "dataset_model_info" / "3dva_models.json",
    "meshmamba_non_texture": _REPO_ROOT / "jsons" / "dataset_model_info" / "meshmamba_non_texture_models.json",
    "meshmamba_rgb_texture": _REPO_ROOT / "jsons" / "dataset_model_info" / "meshmamba_rgb_texture_models.json",
    "sal3d": _REPO_ROOT / "jsons" / "dataset_model_info" / "sal3d_models.json",
}


class RequestBuildError(ValueError):
    """Raised when the branch request CLI inputs are inconsistent."""


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=_REPO_ROOT, stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception as exc:  # pragma: no cover - defensive
        raise RequestBuildError("unable to resolve current git HEAD") from exc


def _parse_env_pairs(pairs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in pairs:
        if "=" not in raw:
            raise RequestBuildError(f"--resolved-env expects KEY=VALUE, got {raw!r}")
        k, v = raw.split("=", 1)
        k = k.strip()
        v = v.strip()
        if not k or not v:
            raise RequestBuildError(f"--resolved-env expects non-empty KEY and VALUE, got {raw!r}")
        out[k] = v
    return out


def _load_models(dataset: str) -> list[str]:
    path = MODEL_INDEX[dataset]
    payload = json.loads(path.read_text())
    if isinstance(payload, dict):
        rows = payload.get("models")
    else:
        rows = payload
    if not isinstance(rows, list):
        raise RequestBuildError(f"{path} has no top-level models list")
    models = [str(row["model"]) for row in rows]
    if len(set(models)) != len(models):
        raise RequestBuildError(f"duplicate model names in {path}")
    return models


def _select_models(dataset: str, *, models: list[str] | None, limit: int | None) -> list[str]:
    available = _load_models(dataset)
    if models:
        missing = [m for m in models if m not in available]
        if missing:
            raise RequestBuildError(f"unknown models for {dataset}: {missing}")
        return models
    if limit is not None:
        if limit <= 0:
            raise RequestBuildError("--limit-models must be > 0")
        return available[:limit]
    return available


def _spec_for(method: str):
    if method == "screen_space":
        return ss.build_spec()
    if method == "cone":
        return cone.build_spec()
    raise RequestBuildError(f"unsupported method {method!r}")


def _fmt_num(v) -> str:
    f = float(v)
    return str(int(f)) if f.is_integer() else str(f)


def _fmt_delay(v: float) -> str:
    return str(float(v))


def _fmt_frame_offset(v: int) -> str:
    return str(int(v))


def _fixed_policy(name: str, value, *, kind: str) -> str:
    if kind == "delay":
        return f"{name}:{_fmt_delay(value)}"
    if kind == "frame_offset":
        return f"{name}:{_fmt_frame_offset(value)}"
    raise RequestBuildError(f"unsupported policy kind {kind!r}")


def _sweep_policy(name: str, values: list[float | int], *, kind: str) -> str:
    if kind == "delay":
        parts = [_fmt_delay(v) for v in values]
    elif kind == "frame_offset":
        parts = [_fmt_frame_offset(v) for v in values]
    else:
        raise RequestBuildError(f"unsupported policy kind {kind!r}")
    return f"{name}:{','.join(parts)}"


def _parse_axis_values(stage: str, raw_values: list[str] | None) -> list[float | int] | None:
    if stage == "sigma":
        return None
    if not raw_values:
        raise RequestBuildError(f"stage {stage!r} requires --axis-values")
    if stage == "timing":
        vals = [float(v) for v in raw_values]
    else:
        vals = [int(v) for v in raw_values]
    if len(set(vals)) != len(vals):
        raise RequestBuildError("--axis-values must be unique")
    return vals


def build_request(args) -> dict:
    spec = _spec_for(args.method)
    models = _select_models(args.dataset, models=args.models, limit=args.limit_models)
    repo_commit = args.repo_commit or _git_head()

    request = {
        "dataset": args.dataset,
        "method": args.method,
        "stage": args.stage,
        "models": models,
        "subset_name": args.subset_name or f"{args.dataset}_all_models",
        "repo_commit": repo_commit,
        "release_tag": args.release_tag,
        "fixation_data_tag": args.fixation_data_tag,
        "timing_contract": args.timing_contract,
        "window_mode": args.window_mode,
        "fixed": {
            "delay_seconds": float(args.fixed_delay_seconds),
            "frame_offset": int(args.fixed_frame_offset),
        },
    }

    if args.checkout_root:
        request["checkout_root"] = args.checkout_root
    if args.python:
        request["python"] = args.python
    if args.timeout_seconds_per_invocation is not None:
        request["timeout_seconds_per_invocation"] = int(args.timeout_seconds_per_invocation)
    if args.resolved_env:
        request["resolved_env"] = _parse_env_pairs(args.resolved_env)

    axis_values = _parse_axis_values(args.stage, args.axis_values)
    if args.stage == "sigma":
        request["frame_offset_policy"] = _fixed_policy("fixed", args.fixed_frame_offset, kind="frame_offset")
        request["delay_policy"] = _fixed_policy("fixed", args.fixed_delay_seconds, kind="delay")
        request["sigma"] = {"refined": not args.no_refined}
    elif args.stage == "timing":
        if args.fixed_sigma_value is None:
            raise RequestBuildError("stage 'timing' requires --fixed-sigma-value")
        request["frame_offset_policy"] = _fixed_policy("fixed", args.fixed_frame_offset, kind="frame_offset")
        request["delay_policy"] = _sweep_policy("sweep", axis_values, kind="delay")
        request["fixed_sigma"] = spec.expand_sigma(args.dataset, float(args.fixed_sigma_value))
        request["axis_values"] = axis_values
    else:
        if args.fixed_sigma_value is None:
            raise RequestBuildError("stage 'frame_offset' requires --fixed-sigma-value")
        request["frame_offset_policy"] = _sweep_policy("sweep", axis_values, kind="frame_offset")
        request["delay_policy"] = _fixed_policy("fixed", args.fixed_delay_seconds, kind="delay")
        request["fixed_sigma"] = spec.expand_sigma(args.dataset, float(args.fixed_sigma_value))
        request["axis_values"] = axis_values

    core.validate_request(request)
    return request


def main() -> int:
    ap = argparse.ArgumentParser(description="Build a dataset-level ablation request JSON.")
    ap.add_argument("--dataset", required=True, choices=sorted(MODEL_INDEX))
    ap.add_argument("--method", required=True, choices=("screen_space", "cone"))
    ap.add_argument("--stage", required=True, choices=("sigma", "timing", "frame_offset"))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--subset-name", default=None)
    ap.add_argument("--models", nargs="*", default=None,
                    help="explicit model list; defaults to all models from dataset_model_info")
    ap.add_argument("--limit-models", type=int, default=None,
                    help="take the first N models from the canonical dataset index")
    ap.add_argument("--repo-commit", default=None)
    ap.add_argument("--release-tag", default="v2.0-data-rc4")
    ap.add_argument("--fixation-data-tag", default="processed_fixations_offset0_full_cleaned")
    ap.add_argument("--timing-contract", default="one_turn_from_start")
    ap.add_argument("--window-mode", default="one_turn_from_start")
    ap.add_argument("--fixed-delay-seconds", type=float, default=0.0)
    ap.add_argument("--fixed-frame-offset", type=int, default=0)
    ap.add_argument("--fixed-sigma-value", type=float, default=None,
                    help="required for timing/frame_offset branches; method-native sigma magnitude")
    ap.add_argument("--axis-values", nargs="+", default=None,
                    help="required for timing/frame_offset branches")
    ap.add_argument("--no-refined", action="store_true",
                    help="disable the refined sigma stage for stage=sigma")
    ap.add_argument("--resolved-env", action="append", default=[],
                    help="repeat KEY=VALUE to pin runtime roots in the request")
    ap.add_argument("--python", default=None)
    ap.add_argument("--timeout-seconds-per-invocation", type=int, default=None)
    ap.add_argument("--checkout-root", default=None)
    args = ap.parse_args()

    try:
        request = build_request(args)
    except RequestBuildError as exc:
        print(f"[dmlab-request] BUILD FAILED: {exc}", file=sys.stderr)
        return 2

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(request, indent=2))
    print(f"[dmlab-request] wrote {args.out}")
    print(f"[dmlab-request] dataset={request['dataset']} method={request['method']} "
          f"stage={request['stage']} subset={request['subset_name']} size={len(request['models'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
