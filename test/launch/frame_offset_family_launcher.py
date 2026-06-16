"""Stage-2 frame_offset family launcher for cone_frame_offset and
screen_space_frame_offset.

NON-DESTRUCTIVE, LOCAL ONLY by default. One family branch = one (dataset, method)
pair; one stage only. The launcher consumes the authoritative upstream timing
`branch_best.json`, fixes BOTH sigma AND delay_seconds at the upstream best,
and sweeps the `frame_offset` grid for the same branch.

Modeled on `timing_family_launcher.py`. Reuses the existing aggregation +
evaluator-sweep machinery; imports no baseline evaluator.
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
    "cone_frame_offset": "cone",
    "screen_space_frame_offset": "screen_space",
}
UPSTREAM_FAMILY = {
    "cone_frame_offset": "cone_timing",
    "screen_space_frame_offset": "screen_space_timing",
}
# Campaign-plan frame_offset grid (full_ablation_campaign_plan.md §2.4).
DEFAULT_FRAME_OFFSET_GRID: tuple[int, ...] = (0, 15, 30, 54, 90, 120)

COVERAGE_THRESHOLD = 0.70
ERROR_TYPE_MAX_SHARE = 0.30
NOISE_FLOOR_MULT = 0.5


class ManifestError(ValueError):
    """Raised when a frame_offset-family manifest fails validation."""


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
        raise ManifestError(
            f"unsupported frame_offset family {family!r}; known: {sorted(FAMILY_METHOD)}"
        )
    return FAMILY_METHOD[family]


def _upstream_family(family: str) -> str:
    return UPSTREAM_FAMILY[family]


def _frame_offset_best_params_from_source(source: dict) -> dict:
    """Pass the upstream timing best_params straight through; downstream
    joint_refine will augment with the chosen frame_offset at write time."""
    return dict(source["best_params"])


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
            f"repo_commit drift: manifest {sub['repo_commit']!r} vs smoke {smoke.get('repo_commit')!r}")
    point = smoke.get("point", {})
    if point.get("dataset") not in (None, "", sub["dataset"]):
        raise ManifestError(
            f"smoke dataset mismatch: {point.get('dataset')!r} != {sub['dataset']!r}")
    if point.get("method") not in (None, "", sub["method"]):
        raise ManifestError(
            f"smoke method mismatch: {point.get('method')!r} != {sub['method']!r}")
    summary = smoke.get("metrics_summary_csv", "")
    if not summary or not Path(summary).exists():
        raise ManifestError(f"smoke's metrics_summary_csv missing on disk: {summary!r}")
    return smoke


def _load_consumed_branch_best(manifest: dict) -> dict:
    """Read and validate the upstream timing branch_best.json. Refuses sub-stage
    markers — only the authoritative root pointer is accepted."""
    sub = manifest["submission"]
    source_path = manifest.get("consumes", {}).get("timing_branch_best")
    if not source_path:
        raise ManifestError(
            "frame_offset family requires consumes.timing_branch_best (path to upstream branch_best.json)")
    path = Path(source_path)
    if path.name != "branch_best.json":
        raise ManifestError(
            "frame_offset family must consume upstream branch_best.json, not a sub-stage marker")
    try:
        source = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"timing_branch_best unreadable: {source_path} ({exc})")
    expected_upstream = _upstream_family(sub["family"])
    if source.get("family") != expected_upstream:
        raise ManifestError(
            f"upstream family mismatch: expected {expected_upstream!r}, got {source.get('family')!r}")
    if source.get("dataset") != sub["dataset"] or source.get("method") != sub["method"]:
        raise ManifestError("upstream dataset/method mismatch with submission")
    if source.get("repo_commit") != sub["repo_commit"]:
        raise ManifestError("upstream repo_commit mismatch")
    if not source.get("points_to"):
        raise ManifestError("upstream branch_best.json missing points_to")
    best = source.get("best_params") or {}
    if "delay_seconds" not in best:
        raise ManifestError(
            "upstream timing branch_best.json:best_params must include 'delay_seconds' "
            "(packed at timing branch-best write time)")
    return source


def validate_manifest(manifest: dict, *, check_smoke: bool = True) -> dict:
    sub = _require(manifest, "submission")
    sweep = _require(manifest, "sweep")
    models = _require(manifest, "models")

    for field in ("family", "dataset", "method", "texture_type", "repo_commit",
                  "smoke_artifact", "fixation_data_tag", "window_mode"):
        if field not in sub:
            raise ManifestError(f"submission.{field} missing")
    family = sub["family"]
    method = _family_method(family)
    if sub["method"] != method:
        raise ManifestError(f"submission.method must be {method!r} for family {family!r}")
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

    grid = sweep.get("frame_offset_values")
    if not (isinstance(grid, list) and grid and all(isinstance(v, int) and v >= 0 for v in grid)):
        raise ManifestError("sweep.frame_offset_values must be a non-empty list of non-negative ints")
    if len(set(grid)) != len(grid):
        raise ManifestError("sweep.frame_offset_values must contain unique values")

    source = _load_consumed_branch_best(manifest)
    best = _frame_offset_best_params_from_source(source)
    delay = float(best["delay_seconds"])
    invalid = []
    for fo in grid:
        ok, reason = rawd.one_turn_frame_offset_feasible(
            sub["dataset"], frame_offset=int(fo), delay_seconds=delay
        )
        if not ok:
            invalid.append((int(fo), reason))
    if invalid:
        joined = "; ".join(f"{fo}: {reason}" for fo, reason in invalid)
        raise ManifestError(
            "sweep.frame_offset_values contains infeasible points for the fixed delay "
            f"{delay:+.3f}s: {joined}"
        )
    if source.get("common_model_set") != models.get("subset_name"):
        raise ManifestError(
            f"models.subset_name must equal upstream common_model_set {source.get('common_model_set')!r}")
    if not isinstance(models.get("list"), list) or not models["list"]:
        raise ManifestError("models.list must be non-empty")

    if check_smoke:
        _validate_smoke(manifest, Path(sub["smoke_artifact"]))
    return manifest


# ── git checkout + runtime gates (mirror timing) ─────────────────────────────


def _git(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=_DIR.parents[1], stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return ""


def _submission_env(manifest: dict) -> dict[str, str]:
    return {str(k): str(v) for k, v in (manifest["submission"].get("resolved_env") or {}).items()}


def _submission_fixation_root(manifest: dict) -> str | None:
    env = _submission_env(manifest)
    return env.get("FIXATION_ROOT") or env.get("REPROJECT_PROCESSED_FIXATIONS_ROOT")


def _require_current_checkout_commit(manifest: dict) -> None:
    head = _git("rev-parse", "HEAD")
    target = manifest["submission"]["repo_commit"]
    if head and head != target:
        raise RuntimeGateError(
            f"working tree HEAD {head!r} != manifest.repo_commit {target!r}; refusing run")


def _require_manifest_runtime(manifest: dict) -> None:
    sub = manifest["submission"]
    env = _submission_env(manifest)
    pf.require(sub["dataset"], sub["method"],
               fixation_root=_submission_fixation_root(manifest), env=env)
    pf.require_runtime_dependencies(sub["method"], python=sub["python"])


# ── identity, signatures, task tag ───────────────────────────────────────────

_IDENTITY_FIELDS = (
    "repo_commit", "family", "dataset", "method", "texture_type",
    "axis", "axis_value", "fixed_upstream_signature", "window_mode",
    "fixation_data_tag", "model",
)


def identity_sha1(**fields) -> str:
    missing = [f for f in _IDENTITY_FIELDS if f not in fields]
    if missing:
        raise ValueError(f"identity_sha1 missing fields: {missing}")
    payload = "|".join(f"{k}={fields[k]}" for k in _IDENTITY_FIELDS)
    return hashlib.sha1(payload.encode()).hexdigest()


def _fixed_upstream_signature(method: str, best_params: dict) -> str:
    """Pack BOTH sigma AND delay_seconds (the two upstream-fixed axes) into one
    string. A frame_offset rerun cannot collide with the same frame_offset under
    a different (sigma, delay) combination."""
    delay = best_params["delay_seconds"]
    if method == "cone":
        return f"sdeg={best_params['sigma_deg']};rsm={best_params['radius_sigma_mult']};d={delay}"
    if "sigma_px" in best_params:
        return f"smul={best_params['sigma_multiplier']};spx={best_params['sigma_px']};d={delay}"
    return f"smul={best_params['sigma_multiplier']};ssc={best_params['sigma_screen']};d={delay}"


def _task_tag_for_frame_offset_point(method: str, point: dict, upstream_sig: str) -> str:
    """Raw per-task leaf must encode method + frame_offset + the full upstream
    (sigma+delay) signature so re-running with a different upstream best cannot
    reuse a stale evaluator report directory."""
    frame_offset = int(point["frame_offset"])
    upstream_tag = upstream_sig.replace(";", "_")
    window_tag = str(point.get("window_mode", "")).strip()
    parts = [method, f"fo{frame_offset}", upstream_tag]
    if window_tag:
        parts.insert(1, f"w{window_tag}")
    return "_".join(parts)


# ── resume helpers (mirror timing) ───────────────────────────────────────────

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
    p = branch_dir / "aggregate" / "ablation_runs.jsonl"
    if not p.is_file():
        return []
    out = []
    for line in p.read_text().splitlines():
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


# ── promotion gates (mirror timing) ──────────────────────────────────────────


def evaluate_stage(rows: list[dict], expected_points: int) -> dict:
    if expected_points <= 0:
        raise ValueError("expected_points must be > 0")
    statuses = {r.get("frame_offset"): _row_status(r) for r in rows}
    non_red = [s for s in statuses.values() if s != "RED"]
    coverage = len(non_red) / expected_points if expected_points else 0.0
    has_green = any(s == "GREEN" for s in statuses.values())

    failures_by_type: dict[str, int] = {}
    total_failures = 0
    for r in rows:
        et = (r.get("error_type") or "").strip()
        n_failed = int(r.get("n_failed") or 0)
        if n_failed:
            total_failures += n_failed
            if et:
                failures_by_type[et] = failures_by_type.get(et, 0) + n_failed
    dominant_share = 0.0
    dominant_type = ""
    if total_failures:
        dominant_type = max(failures_by_type, key=failures_by_type.get, default="")
        dominant_share = failures_by_type.get(dominant_type, 0) / total_failures if dominant_type else 0.0

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

    top3 = [float(r["CC"]) for r in rankable[:3]]
    noise = NOISE_FLOOR_MULT * statistics.stdev(top3) if len(top3) >= 2 else 0.0
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
        "second_best_CC": float(second["CC"]) if second else None,
        "third_best_CC": float(third["CC"]) if third else None,
        "noise_floor_CC": round(noise, 6),
    }


def _row_status(row: dict) -> str:
    n_ok = int(row.get("n_ok") or 0)
    n_total = int(row.get("n_total_models") or 0)
    if n_ok == 0:
        return "RED"
    if n_ok == n_total:
        return "GREEN"
    return "AMBER"


# ── marker writers ───────────────────────────────────────────────────────────


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(payload, fh, indent=2, default=str)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


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
        "next_action_suggestion": "review gates and resubmit",
    }
    out = branch_dir / "_held.json"
    _atomic_write_json(out, payload)
    return out


# ── stage execution ──────────────────────────────────────────────────────────


def _stage_points(manifest: dict, consumed_best: dict) -> list[dict]:
    sub = manifest["submission"]
    method = sub["method"]
    best_params = _frame_offset_best_params_from_source(consumed_best)
    delay = float(best_params["delay_seconds"])
    upstream_sig = _fixed_upstream_signature(method, best_params)
    points = []
    for fo in manifest["sweep"]["frame_offset_values"]:
        point = ev.make_sigma_grid(
            sub["dataset"], method,
            sigma_param="sigma_deg" if method == "cone" else (
                "sigma_px" if "sigma_px" in best_params else "sigma_screen"),
            sigma_values=[best_params.get("sigma_deg")
                          or best_params.get("sigma_px")
                          or best_params.get("sigma_screen")],
            radius_sigma_mult=best_params.get("radius_sigma_mult"),
            delay_seconds=delay, window_mode=sub["window_mode"],
        )[0]
        # Make sure all upstream-fixed sigma fields are present on the point so
        # build_evaluator_command emits the correct --sigma-* flag set.
        for k in ("sigma_deg", "sigma_px", "sigma_screen", "radius_sigma_mult"):
            if k in best_params and point.get(k) is None:
                point[k] = best_params[k]
        point["axis"] = "frame_offset"
        point["value"] = int(fo)
        point["frame_offset"] = int(fo)
        point["task_tag"] = _task_tag_for_frame_offset_point(method, point, upstream_sig)
        points.append(point)
    return points


def _execute_branch(manifest: dict, *, results_root: Path, branch_dir: Path,
                    invoke, resume_rows: dict[str, dict], consumed_best: dict) -> None:
    sub = manifest["submission"]
    family = sub["family"]
    method = sub["method"]
    models = list(manifest["models"]["list"])
    points = _stage_points(manifest, consumed_best)
    best_params = _frame_offset_best_params_from_source(consumed_best)
    upstream_sig = _fixed_upstream_signature(method, best_params)
    existing_run_ids = _existing_run_ids(branch_dir)

    def _identity_for(point: dict, model: str) -> str:
        return identity_sha1(
            repo_commit=sub["repo_commit"],
            family=family,
            dataset=sub["dataset"],
            method=method,
            texture_type=sub.get("texture_type", ""),
            axis="frame_offset",
            axis_value=int(point["frame_offset"]),
            fixed_upstream_signature=upstream_sig,
            window_mode=sub["window_mode"],
            fixation_data_tag=sub["fixation_data_tag"],
            model=model,
        )

    def _wrapped_invoke(point: dict, model: str) -> dict:
        sha = _identity_for(point, model)
        if sha in resume_rows:
            row = dict(resume_rows[sha])
            row["status"] = row.get("status", "ok")
            return row
        row = invoke(point, model)
        row["identity_sha1"] = sha
        row.setdefault("repo_commit", sub["repo_commit"])
        return row

    def _make_params(point: dict) -> dict:
        params = {
            "stage_name": family,
            "dataset": sub["dataset"], "method": method,
            "texture_type": sub.get("texture_type", ""),
            "timing_contract": "one_turn_from_start",
            "window_mode": sub["window_mode"],
            "delay_seconds": float(best_params["delay_seconds"]),
            "delay_frames": int(round(float(best_params["delay_seconds"]) * 30)),
            "frame_offset": int(point["frame_offset"]),
            "fixation_data_tag": sub["fixation_data_tag"],
            "model_subset_name": manifest["models"]["subset_name"],
            "model_subset_size": len(models),
            "model_set_signature": agg.model_set_signature(models),
            "repo_commit": sub["repo_commit"],
            "branch": sub.get("branch", ""),
            "command": "frame_offset_family_launcher.run_frame_offset_branch",
            "notes": f"family={family} stage=sweep",
            "storage_parts": [family, sub["dataset"], method],
        }
        for k in ("sigma_deg", "sigma_px", "sigma_screen", "sigma_multiplier",
                  "radius_sigma_mult"):
            if k in best_params:
                params[k] = best_params[k]
        return params

    for point in points:
        params = _make_params(point)
        run_id = agg.run_signature(params)
        rows: list[dict] = []
        all_resumed = True
        for model in models:
            row = _wrapped_invoke(point, model)
            if row.get("status") == "ok" and "identity_sha1" in row and \
               row["identity_sha1"] in resume_rows and \
               resume_rows[row["identity_sha1"]] is row:
                pass
            sha = row.get("identity_sha1")
            if sha not in resume_rows:
                all_resumed = False
            rows.append(row)
        if all_resumed and run_id in existing_run_ids:
            continue
        agg.record_run(
            Path(results_root), params, rows,
            command=str(params.get("command", "")),
            on_duplicate="supersede" if run_id in existing_run_ids else "error",
        )


def run_frame_offset_branch(manifest: dict, *, results_root: Path, invoke,
                            check_smoke: bool = True, check_runtime: bool = True) -> dict:
    """Top-level orchestration for one (family, dataset, method) submission."""
    validate_manifest(manifest, check_smoke=check_smoke)
    sub = manifest["submission"]
    consumed_best = _load_consumed_branch_best(manifest)

    if check_runtime:
        _require_current_checkout_commit(manifest)
        _require_manifest_runtime(manifest)

    branch_dir = Path(results_root) / "ablation" / sub["family"] / sub["dataset"] / sub["method"]
    resume_rows = load_resume_ok_rows(branch_dir)
    _execute_branch(
        manifest, results_root=results_root, branch_dir=branch_dir,
        invoke=invoke, resume_rows=resume_rows, consumed_best=consumed_best,
    )

    rows = _aggregate_rows(branch_dir)
    gate = evaluate_stage(rows, expected_points=len(manifest["sweep"]["frame_offset_values"]))
    out = {"promoted": gate["promoted"], "branch_best_path": None, "held_path": None, "gate": gate}
    if not gate["promoted"]:
        out["held_path"] = _write_held(
            branch_dir, family=sub["family"],
            branch=f"{sub['dataset']}/{sub['method']}",
            failed_gates=gate["failed_gates"], gate_details=gate["gate_details"])
        return out

    best = dict(consumed_best["best_params"])
    best["frame_offset"] = int(gate["best"]["frame_offset"])
    out["branch_best_path"] = _write_branch_best(
        branch_dir, family=sub["family"], source_row=gate["best"],
        gate=gate, best_params=best,
        common_model_set=manifest["models"]["subset_name"],
        n_models_used=len(manifest["models"]["list"]))
    return out


def _real_invoke_for_manifest(manifest: dict, *, results_root: Path):
    sub = manifest["submission"]
    env = _submission_env(manifest)
    fixation_root = _submission_fixation_root(manifest)
    timeout = int(sub["timeout_seconds_per_invocation"])
    python = sub["python"]
    work_dir = Path(results_root) / "ablation" / "_work" / sub["family"] / sub["dataset"] / sub["method"]

    def invoke(point: dict, model: str) -> dict:
        return ev.subprocess_evaluator_invoke(
            point, model, work_dir=work_dir, fixation_root=fixation_root,
            timeout=timeout, preflight=False, env=env, python=python)
    return invoke


def main() -> int:
    ap = argparse.ArgumentParser(description="frame_offset family launcher (cone/screen_space).")
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--results-root", type=Path, default=Path("results"))
    ap.add_argument("--validate-only", action="store_true")
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--skip-smoke-check", action="store_true")
    ap.add_argument("--skip-runtime-check", action="store_true")
    args = ap.parse_args()

    manifest = json.loads(args.manifest.read_text())
    try:
        validate_manifest(manifest, check_smoke=not args.skip_smoke_check)
    except ManifestError as exc:
        print(f"[frame_offset] MANIFEST INVALID: {exc}", file=sys.stderr)
        return 2

    if args.validate_only:
        print("[frame_offset] manifest OK")
        return 0

    invoke = ev.make_mock_invoke() if args.mock else _real_invoke_for_manifest(
        manifest, results_root=args.results_root)
    try:
        result = run_frame_offset_branch(
            manifest, results_root=args.results_root, invoke=invoke,
            check_smoke=not args.skip_smoke_check,
            check_runtime=not (args.mock or args.skip_runtime_check))
    except (ManifestError, RuntimeGateError) as exc:
        print(f"[frame_offset] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    verdict = "PROMOTED" if result["promoted"] else "HELD"
    print(f"[frame_offset] {verdict} branch_best={result['branch_best_path']}")
    return 0 if result["promoted"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
