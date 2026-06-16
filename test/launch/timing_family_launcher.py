"""Stage-2 timing family launcher for cone_timing and screen_space_timing.

NON-DESTRUCTIVE, LOCAL ONLY by default. One family branch = one
(dataset, method) pair; one stage only. The launcher consumes the authoritative
upstream sigma `branch_best.json`, fixes sigma at that value, and sweeps the
delay grid for the same branch.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

_DIR = Path(__file__).resolve().parent


def _load(name: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ev = _load("run_evaluator_sweep")
agg = _load("ablation_aggregation")
pf = _load("evaluator_preflight")
rawd = _load("run_ablation_window_delay")

FAMILY_METHOD = {
    "cone_timing": "cone",
    "screen_space_timing": "screen_space",
}
UPSTREAM_FAMILY = {
    "cone_timing": "cone_sigma",
    "screen_space_timing": "screen_space_sigma",
}
DEFAULT_DELAY_GRID: tuple[float, ...] = tuple(rawd.LARGE_ABLATION_DELAYS)

COVERAGE_THRESHOLD = 0.70
ERROR_TYPE_MAX_SHARE = 0.30
NOISE_FLOOR_MULT = 0.5


class ManifestError(ValueError):
    """Raised when a timing-family manifest fails validation."""


class RuntimeGateError(RuntimeError):
    """Raised when the local checkout/runtime is incompatible with a submission."""


def _require(d: dict, *keys: str) -> Any:
    node: Any = d
    for k in keys:
        if not isinstance(node, dict) or k not in node:
            raise ManifestError(f"manifest missing required field: {'.'.join(keys)}")
        node = node[k]
    return node


def _family_method(family: str) -> str:
    if family not in FAMILY_METHOD:
        raise ManifestError(f"unsupported timing family {family!r}; known: {sorted(FAMILY_METHOD)}")
    return FAMILY_METHOD[family]


def _upstream_family(family: str) -> str:
    return UPSTREAM_FAMILY[family]


def _timing_best_params_from_source(source: dict) -> dict:
    best = dict(source["best_params"])
    return best


def _validate_smoke(manifest: dict, smoke_path: Path) -> dict:
    try:
        smoke = json.loads(smoke_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"smoke_artifact unreadable: {smoke_path} ({exc})")
    if not (smoke.get("verdict", {}).get("ok") and smoke["verdict"].get("reason") == "green"):
        raise ManifestError(f"smoke_artifact is not GREEN: {smoke_path}")
    sub = manifest["submission"]
    if smoke.get("repo_commit") != sub["repo_commit"]:
        raise ManifestError(
            f"repo_commit drift: manifest {sub['repo_commit']!r} vs smoke {smoke.get('repo_commit')!r}"
        )
    point = smoke.get("point", {})
    if point.get("dataset") not in (None, "", sub["dataset"]):
        raise ManifestError(
            f"smoke dataset mismatch: {point.get('dataset')!r} != {sub['dataset']!r}"
        )
    if point.get("method") not in (None, "", sub["method"]):
        raise ManifestError(
            f"smoke method mismatch: {point.get('method')!r} != {sub['method']!r}"
        )
    summary = smoke.get("metrics_summary_csv", "")
    if not summary or not Path(summary).exists():
        raise ManifestError(f"smoke's metrics_summary_csv missing on disk: {summary!r}")
    return smoke


def _load_consumed_branch_best(manifest: dict) -> dict:
    source_path = manifest.get("consumes", {}).get("sigma_branch_best")
    if not source_path:
        raise ManifestError("timing family requires consumes.sigma_branch_best")
    path = Path(source_path)
    if path.name != "branch_best.json":
        raise ManifestError("timing family must consume upstream branch_best.json, not a sub-stage marker")
    try:
        source = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"sigma_branch_best unreadable: {source_path} ({exc})")
    return source


def validate_manifest(manifest: dict, *, check_smoke: bool = True) -> dict:
    sub = _require(manifest, "submission")
    sweep = _require(manifest, "sweep")
    models = _require(manifest, "models")

    for field in (
        "family", "dataset", "method", "texture_type", "repo_commit", "smoke_artifact",
        "fixation_data_tag", "window_mode", "delay_seconds", "frame_offset",
    ):
        if field not in sub:
            raise ManifestError(f"submission.{field} missing")

    expected_method = _family_method(sub["family"])
    if sub["method"] != expected_method:
        raise ManifestError(f"submission.method must be {expected_method!r}, got {sub['method']!r}")
    if not isinstance(sub["repo_commit"], str) or len(sub["repo_commit"]) != 40:
        raise ManifestError("submission.repo_commit must be a 40-char sha")
    if not isinstance(sub.get("resolved_env"), dict):
        raise ManifestError("submission.resolved_env must be a dict")
    if not isinstance(sub.get("python"), str) or not sub["python"].strip():
        raise ManifestError("submission.python must be a non-empty string")
    if int(sub.get("timeout_seconds_per_invocation") or 0) <= 0:
        raise ManifestError("submission.timeout_seconds_per_invocation must be > 0")
    if int(sub.get("max_workers") or 0) <= 0:
        raise ManifestError("submission.max_workers must be > 0")

    if sweep.get("axis") != "delay_seconds":
        raise ManifestError("sweep.axis must be 'delay_seconds'")
    delay_values = sweep.get("delay_values")
    if not (
        isinstance(delay_values, list)
        and delay_values
        and all(isinstance(v, (int, float)) for v in delay_values)
    ):
        raise ManifestError("sweep.delay_values must be a non-empty list of numbers")

    source = _load_consumed_branch_best(manifest)
    if source.get("family") != _upstream_family(sub["family"]):
        raise ManifestError(
            f"upstream family mismatch: expected {_upstream_family(sub['family'])!r}, got {source.get('family')!r}"
        )
    if source.get("dataset") != sub["dataset"]:
        raise ManifestError("upstream dataset mismatch")
    if source.get("method") != sub["method"]:
        raise ManifestError("upstream method mismatch")
    if source.get("repo_commit") != sub["repo_commit"]:
        raise ManifestError("upstream repo_commit mismatch")
    if not source.get("points_to"):
        raise ManifestError("upstream branch_best.json missing points_to")
    if source.get("common_model_set") != models.get("subset_name"):
        raise ManifestError(
            f"models.subset_name must equal upstream common_model_set {source.get('common_model_set')!r}"
        )
    if not isinstance(models.get("list"), list) or not models["list"]:
        raise ManifestError("models.list must be non-empty")

    if check_smoke:
        _validate_smoke(manifest, Path(sub["smoke_artifact"]))
    return manifest


def _git(*args: str) -> str:
    repo_root = _DIR.parents[1]
    try:
        return subprocess.check_output(
            ["git", *args], cwd=repo_root, stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return ""


def _submission_env(manifest: dict) -> dict[str, str]:
    env = manifest["submission"].get("resolved_env") or {}
    return {str(k): str(v) for k, v in env.items() if str(k).strip() and str(v).strip()}


def _submission_fixation_root(manifest: dict) -> str | None:
    env = _submission_env(manifest)
    return env.get("FIXATION_ROOT") or env.get("REPROJECT_PROCESSED_FIXATIONS_ROOT")


def _require_current_checkout_commit(manifest: dict) -> None:
    expected = manifest["submission"]["repo_commit"]
    actual = _git("rev-parse", "HEAD")
    if not actual:
        raise RuntimeGateError("unable to resolve current git HEAD for repo-commit gate")
    if actual != expected:
        raise RuntimeGateError(
            f"current checkout HEAD {actual!r} does not match submission.repo_commit {expected!r}"
        )


def _require_manifest_runtime(manifest: dict) -> None:
    sub = manifest["submission"]
    pf.require(
        sub["dataset"], sub["method"],
        fixation_root=_submission_fixation_root(manifest),
        env=_submission_env(manifest),
    )
    pf.require_runtime_dependencies(sub["method"], python=sub["python"])


_IDENTITY_FIELDS = (
    "repo_commit", "family", "dataset", "method", "texture_type",
    "axis", "axis_value", "fixed_sigma_signature", "window_mode",
    "frame_offset", "fixation_data_tag", "model",
)


def identity_sha1(**fields) -> str:
    missing = [f for f in _IDENTITY_FIELDS if f not in fields]
    if missing:
        raise ValueError(f"identity_sha1 missing fields: {missing}")
    payload = "|".join(f"{k}={fields[k]}" for k in _IDENTITY_FIELDS)
    return hashlib.sha1(payload.encode()).hexdigest()


def _fixed_sigma_signature(method: str, best_params: dict) -> str:
    if method == "cone":
        return f"sdeg={best_params['sigma_deg']};rsm={best_params['radius_sigma_mult']}"
    if "sigma_px" in best_params:
        return f"smul={best_params['sigma_multiplier']};spx={best_params['sigma_px']}"
    return f"smul={best_params['sigma_multiplier']};ssc={best_params['sigma_screen']}"


def _task_tag_for_timing_point(method: str, point: dict, sigma_sig: str) -> str:
    delay = agg._sig_val(float(point["delay_seconds"]))
    frame_offset = int(point["frame_offset"])
    sigma_tag = sigma_sig.replace(";", "_")
    return f"{method}_delay_seconds{delay}_{sigma_tag}_fo{frame_offset}"


def load_resume_ok_rows(branch_dir: Path) -> dict[str, dict]:
    reusable: dict[str, dict] = {}
    runs = branch_dir / "runs"
    if not runs.is_dir():
        return reusable
    for long_jsonl in runs.glob("*/metrics_long.jsonl"):
        for line in long_jsonl.read_text().splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("status") != "ok":
                continue
            sha = rec.get("identity_sha1")
            if sha:
                reusable[sha] = rec
    return reusable


def _aggregate_rows(branch_dir: Path) -> list[dict]:
    path = branch_dir / "aggregate" / "ablation_runs.jsonl"
    if not path.is_file():
        return []
    out = []
    for line in path.read_text().splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("status") == "superseded":
            continue
        out.append(row)
    return out


def _existing_run_ids(branch_dir: Path) -> set[str]:
    return {r.get("run_id") for r in _aggregate_rows(branch_dir) if r.get("run_id")}


def evaluate_stage(rows: list[dict], expected_points: int) -> dict:
    if expected_points <= 0:
        raise ValueError("expected_points must be > 0")
    statuses = {r.get("delay_seconds"): _row_status(r) for r in rows}
    non_red = [s for s in statuses.values() if s != "RED"]
    coverage = len(non_red) / expected_points if expected_points else 0.0
    has_green = any(s == "GREEN" for s in statuses.values())

    failures_by_type: dict[str, int] = {}
    total_failures = 0
    for row in rows:
        error_type = (row.get("error_type") or "").strip()
        n_failed = int(row.get("n_failed") or 0)
        if n_failed:
            total_failures += n_failed
            if error_type:
                failures_by_type[error_type] = failures_by_type.get(error_type, 0) + n_failed

    dominant_share = 0.0
    dominant_type = ""
    if total_failures:
        dominant_type = max(failures_by_type, key=failures_by_type.get, default="")
        dominant_share = (failures_by_type.get(dominant_type, 0) / total_failures) if dominant_type else 0.0

    failed_gates: list[str] = []
    if coverage < COVERAGE_THRESHOLD:
        failed_gates.append("coverage")
    if not has_green:
        failed_gates.append("at_least_one_green")
    if dominant_share > ERROR_TYPE_MAX_SHARE:
        failed_gates.append("error_type_budget")

    details = {
        "coverage_observed": round(coverage, 4),
        "coverage_required": COVERAGE_THRESHOLD,
        "has_green": has_green,
        "dominant_error_type": dominant_type,
        "dominant_error_share": round(dominant_share, 4),
        "error_type_max_share": ERROR_TYPE_MAX_SHARE,
        "n_rows": len(rows),
        "expected_points": expected_points,
    }
    if failed_gates:
        return {"promoted": False, "failed_gates": failed_gates, "gate_details": details}

    rankable = [r for r in rows if _row_status(r) != "RED" and r.get("CC") not in (None, "")]
    rankable.sort(key=lambda r: float(r["CC"]), reverse=True)
    if not rankable:
        return {"promoted": False, "failed_gates": ["no_rankable_row"], "gate_details": details}

    top3_cc = [float(r["CC"]) for r in rankable[:3]]
    noise_floor = (NOISE_FLOOR_MULT * statistics.stdev(top3_cc)) if len(top3_cc) >= 2 else 0.0
    best = rankable[0]
    second = rankable[1] if len(rankable) >= 2 else None
    third = rankable[2] if len(rankable) >= 3 else None
    return {
        "promoted": True,
        "failed_gates": [],
        "gate_details": details,
        "best": best,
        "second": second,
        "third": third,
        "best_CC": float(best["CC"]),
        "second_best_CC": (float(second["CC"]) if second else None),
        "third_best_CC": (float(third["CC"]) if third else None),
        "noise_floor_CC": round(noise_floor, 6),
    }


def _row_status(row: dict) -> str:
    n_ok = int(row.get("n_ok") or 0)
    n_total = int(row.get("n_total_models") or 0)
    if n_ok == 0:
        return "RED"
    if n_ok == n_total:
        return "GREEN"
    return "AMBER"


def _write_branch_best(branch_dir: Path, *, family: str, source_row: dict, gate: dict,
                       best_params: dict, common_model_set: str, n_models_used: int) -> Path:
    payload = {
        "family": family,
        "dataset": source_row["dataset"],
        "method": source_row["method"],
        "stage": "sweep",
        "points_to": f"aggregate/ablation_runs.jsonl#run_id={source_row['run_id']}",
        "repo_commit": source_row["repo_commit"],
        "promoted_at_utc": agg.utc_now_iso(),
        "best_params": best_params,
        "common_model_set": common_model_set,
        "n_models_used": n_models_used,
        "noise_floor_CC": gate["noise_floor_CC"],
        "best_CC": gate["best_CC"],
        "second_best_CC": gate.get("second_best_CC"),
        "third_best_CC": gate.get("third_best_CC"),
        "artifact_run_id": source_row.get("artifact_run_id", ""),
    }
    out = branch_dir / "branch_best.json"
    _atomic_write_json(out, payload)
    return out


def _write_held(branch_dir: Path, *, family: str, branch: str,
                failed_gates: list[str], gate_details: dict) -> Path:
    payload = {
        "family": family,
        "stage": "sweep",
        "branch": branch,
        "held_at_utc": agg.utc_now_iso(),
        "failed_gates": failed_gates,
        "gate_details": gate_details,
        "next_action_suggestion": "review timing sweep gates and resubmit",
    }
    out = branch_dir / "_held.json"
    _atomic_write_json(out, payload)
    return out


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(payload, fh, indent=2, default=str)
        Path(tmp_name).replace(path)
    except Exception:
        try:
            Path(tmp_name).unlink()
        except OSError:
            pass
        raise


def _stage_points(manifest: dict, consumed_best: dict) -> list[dict]:
    sub = manifest["submission"]
    family = sub["family"]
    method = sub["method"]
    best_params = _timing_best_params_from_source(consumed_best)
    sigma_sig = _fixed_sigma_signature(method, best_params)
    points = []
    for delay in [float(v) for v in manifest["sweep"]["delay_values"]]:
        point = {
            "dataset": sub["dataset"],
            "method": method,
            "axis": "delay_seconds",
            "value": delay,
            "delay_seconds": delay,
            "window_mode": sub["window_mode"],
            "frame_offset": int(sub["frame_offset"]),
        }
        point.update(best_params)
        point["task_tag"] = _task_tag_for_timing_point(method, point, sigma_sig)
        points.append(point)
    return points


def _execute_branch(manifest: dict, *, results_root: Path, branch_dir: Path, invoke,
                    resume_rows: dict[str, dict], consumed_best: dict) -> None:
    sub = manifest["submission"]
    family = sub["family"]
    models = list(manifest["models"]["list"])
    points = _stage_points(manifest, consumed_best)
    best_params = _timing_best_params_from_source(consumed_best)
    sigma_sig = _fixed_sigma_signature(sub["method"], best_params)
    existing_run_ids = _existing_run_ids(branch_dir)

    def _identity_for(point: dict, model: str) -> str:
        return identity_sha1(
            repo_commit=sub["repo_commit"],
            family=family,
            dataset=sub["dataset"],
            method=sub["method"],
            texture_type=sub.get("texture_type", ""),
            axis="delay_seconds",
            axis_value=float(point["delay_seconds"]),
            fixed_sigma_signature=sigma_sig,
            window_mode=sub["window_mode"],
            frame_offset=int(sub["frame_offset"]),
            fixation_data_tag=sub["fixation_data_tag"],
            model=model,
        )

    def _make_params(point: dict) -> dict:
        params = {
            "stage_name": family,
            "dataset": sub["dataset"],
            "method": sub["method"],
            "texture_type": sub.get("texture_type", ""),
            "timing_contract": "one_turn_from_start",
            "window_mode": sub["window_mode"],
            "delay_seconds": point["delay_seconds"],
            "delay_frames": int(round(float(point["delay_seconds"]) * 30)),
            "frame_offset": sub["frame_offset"],
            "fixation_data_tag": sub["fixation_data_tag"],
            "model_subset_name": manifest["models"]["subset_name"],
            "model_subset_size": len(models),
            "model_set_signature": agg.model_set_signature(models),
            "repo_commit": sub["repo_commit"],
            "branch": sub.get("branch", ""),
            "command": "timing_family_launcher.run_timing_branch",
            "notes": f"family={family} fixed_sigma={sigma_sig}",
            "storage_parts": [family, sub["dataset"], sub["method"]],
        }
        params.update(best_params)
        return params

    for point in points:
        params = _make_params(point)
        run_id = agg.run_signature(params)
        rows: list[dict] = []
        all_resumed = True
        for model in models:
            sha = _identity_for(point, model)
            if sha in resume_rows:
                rows.append(dict(resume_rows[sha]))
                continue
            all_resumed = False
            row = invoke(point, model)
            row["identity_sha1"] = sha
            row.setdefault("repo_commit", sub["repo_commit"])
            rows.append(row)
        if all_resumed and run_id in existing_run_ids:
            continue
        agg.record_run(
            Path(results_root), params, rows,
            command=str(params["command"]),
            on_duplicate="supersede" if run_id in existing_run_ids else "error",
        )


def run_timing_branch(manifest: dict, *, results_root: Path, invoke,
                      check_smoke: bool = True) -> dict:
    validate_manifest(manifest, check_smoke=check_smoke)
    consumed_best = _load_consumed_branch_best(manifest)
    sub = manifest["submission"]
    branch_dir = Path(results_root) / "ablation" / sub["family"] / sub["dataset"] / sub["method"]
    resume_rows = load_resume_ok_rows(branch_dir)
    _execute_branch(
        manifest, results_root=results_root, branch_dir=branch_dir,
        invoke=invoke, resume_rows=resume_rows, consumed_best=consumed_best,
    )

    rows = _aggregate_rows(branch_dir)
    gate = evaluate_stage(rows, expected_points=len(manifest["sweep"]["delay_values"]))
    out = {"promoted": gate["promoted"], "branch_best_path": None, "held_path": None, "gate": gate}
    if not gate["promoted"]:
        out["held_path"] = _write_held(
            branch_dir,
            family=sub["family"],
            branch=f"{sub['dataset']}/{sub['method']}",
            failed_gates=gate["failed_gates"],
            gate_details=gate["gate_details"],
        )
        return out

    best = dict(consumed_best["best_params"])
    best["delay_seconds"] = float(gate["best"]["delay_seconds"])
    out["branch_best_path"] = _write_branch_best(
        branch_dir,
        family=sub["family"],
        source_row=gate["best"],
        gate=gate,
        best_params=best,
        common_model_set=manifest["models"]["subset_name"],
        n_models_used=len(manifest["models"]["list"]),
    )
    return out


def _real_invoke_for_manifest(manifest: dict, *, results_root: Path):
    sub = manifest["submission"]
    work_dir = Path(results_root) / "ablation" / "_work" / sub["family"] / sub["dataset"] / sub["method"]
    runtime_env = _submission_env(manifest)
    timeout = int(sub["timeout_seconds_per_invocation"])
    python = sub["python"]
    fixation_root = _submission_fixation_root(manifest)

    def invoke(point: dict, model: str) -> dict:
        return ev.subprocess_evaluator_invoke(
            point, model,
            work_dir=work_dir,
            fixation_root=fixation_root,
            timeout=timeout,
            preflight=False,
            env=runtime_env,
            python=python,
        )

    return invoke


def main() -> int:
    ap = argparse.ArgumentParser(description="timing family launcher (cone_timing / screen_space_timing).")
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--results-root", type=Path, default=Path("results"))
    ap.add_argument("--validate-only", action="store_true")
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--skip-smoke-check", action="store_true")
    args = ap.parse_args()

    manifest = json.loads(args.manifest.read_text())
    try:
        validate_manifest(manifest, check_smoke=not args.skip_smoke_check)
    except ManifestError as exc:
        print(f"[timing-family] MANIFEST INVALID: {exc}", file=sys.stderr)
        return 2

    if args.validate_only:
        print("[timing-family] manifest OK")
        return 0

    if args.mock:
        invoke = ev.make_mock_invoke()
    else:
        try:
            _require_current_checkout_commit(manifest)
            _require_manifest_runtime(manifest)
        except (RuntimeGateError, pf.PreflightError) as exc:
            print(f"[timing-family] RUNTIME GATE FAILED: {exc}", file=sys.stderr)
            return 2
        invoke = _real_invoke_for_manifest(manifest, results_root=args.results_root)

    result = run_timing_branch(
        manifest, results_root=args.results_root, invoke=invoke,
        check_smoke=not args.skip_smoke_check,
    )
    verdict = "PROMOTED" if result["promoted"] else "HELD"
    print(f"[timing-family] {verdict} family={manifest['submission']['family']} branch_best={result['branch_best_path']}")
    return 0 if result["promoted"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
