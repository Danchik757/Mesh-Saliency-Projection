"""Dataset-method ablation orchestration core (orchestra/metric-ablation-lab).

PURPOSE
-------
Select ablation parameters for ONE (dataset, method) pair on a *fair* basis:

  * sigma is chosen per (dataset, method), NEVER per model;
  * every sigma candidate is evaluated on the SAME full model subset;
  * the winner is decided by mean CC computed on the COMMON MODEL SET — the
    intersection of models that succeeded for *every* candidate — so a candidate
    cannot win just because a different (easier) subset of models happened to
    survive for it.

This is an orchestration / launch / aggregation layer ONLY. It imports no
baseline evaluator and changes no metric formula. The per-point evaluator
invocation and the per-run artifact writing are delegated to the existing
`run_evaluator_sweep` + `ablation_aggregation` modules.

The same engine drives the sigma branch and (once sigma is fixed) the timing and
frame_offset branches: each is just a different swept axis with the same
common-model-set fairness rule.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

_DIR = Path(__file__).resolve().parent

# Default parallelism for model invocations within one candidate.
# subprocess_evaluator_invoke spawns one subprocess per model, so threads
# are fine — the GIL is not held while waiting for subprocesses.
# Override per-request with request["max_workers"].
_DEFAULT_MAX_WORKERS = min(16, os.cpu_count() or 4)

# Approved server nice/ionice prefix (Linux only; silent no-op on macOS).
_NICE_PREFIX: list[str] = ["nice", "-n", "19", "ionice", "-c2", "-n7"]


def _server_nice_prefix(request: dict) -> list[str]:
    """Return the nice/ionice prefix when request["server_nice"] is truthy
    and the OS is Linux. Empty on macOS (ionice is not available there)."""
    if not request.get("server_nice"):
        return []
    if sys.platform == "darwin":
        return []
    return _NICE_PREFIX


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

# Compact metric names we mean-aggregate (same set the aggregate tables use).
METRIC_KEYS: tuple[str, ...] = tuple(agg.METRIC_COLUMNS)
RANK_METRIC = "CC"

# A branch is HELD if fewer than this fraction of the full subset survives on
# *every* candidate (i.e. the common set is too thin to compare fairly).
COVERAGE_COMMON_MIN = 0.70

# Fields whose disagreement makes two runs incomparable. Runs that differ on any
# of these MUST NOT be averaged/ranked together.
COMPAT_FIELDS: tuple[str, ...] = (
    "release_tag", "fixation_data_tag", "timing_contract",
    "frame_offset_policy", "delay_policy", "subset_signature",
)

# Leading columns of the shared dataset-method table (ABLATION lab contract).
TABLE_LEAD_COLUMNS: tuple[str, ...] = (
    "dataset", "method", "stage", "sigma_param", "sigma_value",
    "sigma_multiplier", "sigma_px", "sigma_screen", "sigma_deg", "radius_sigma_mult",
    "delay_seconds", "frame_offset", "subset_name", "subset_size",
    "n_ok_raw", "n_common_models", "repo_commit", "release_tag",
    "fixation_data_tag", "timing_contract",
)
TABLE_SERVICE_COLUMNS: tuple[str, ...] = (
    "results_root", "branch_best_path", "held_path", "promoted", "notes",
    "comparability_signature", "coverage_raw", "coverage_common", "n_total_models",
)
TABLE_COLUMNS: tuple[str, ...] = (
    *TABLE_LEAD_COLUMNS, *METRIC_KEYS, *TABLE_SERVICE_COLUMNS,
)

DATASET_METHOD_TABLE_REL = ("ablation", "_tables", "dataset_method_ablation.csv")


class BranchError(ValueError):
    """Raised when a dataset-method ablation request is malformed or incomparable."""


class RuntimeGateError(RuntimeError):
    """Raised when the local checkout/runtime is incompatible with a request."""


# ── method abstraction ───────────────────────────────────────────────────────


@dataclass
class MethodSpec:
    """Per-method knobs. `expand_sigma(dataset, sigma_value)` returns the evaluator
    sigma fields for one sigma candidate (e.g. cone -> {sigma_deg, radius_sigma_mult};
    screen_space -> {sigma_multiplier, sigma_px|sigma_screen})."""
    method: str
    sigma_param: str
    coarse_grid: tuple[float, ...]
    refined_coefs: tuple[float, ...]
    expand_sigma: Callable[[str, float], dict]
    refined_grid: Callable[[float], list[float]]


# ── comparability ────────────────────────────────────────────────────────────


def comparability_context(request: dict) -> dict:
    """Extract the comparability-relevant fields from a branch request."""
    return {
        "release_tag": str(request.get("release_tag", "")),
        "fixation_data_tag": str(request.get("fixation_data_tag", "")),
        "timing_contract": str(request.get("timing_contract", "")),
        "frame_offset_policy": str(request.get("frame_offset_policy", "")),
        "delay_policy": str(request.get("delay_policy", "")),
        "subset_signature": agg.model_set_signature(list(request.get("models", []))),
    }


def comparability_signature(context: dict) -> str:
    payload = "|".join(f"{k}={context.get(k, '')}" for k in COMPAT_FIELDS)
    return hashlib.sha1(payload.encode()).hexdigest()[:16]


def assert_homogeneous(records: Sequence[dict]) -> str:
    """Verify every record shares one comparability signature; return it.
    Raises BranchError on any incompatible mix — the guard that keeps runs with
    different release/fixation/timing/offset/delay/subset from being compared."""
    sigs = set()
    for rec in records:
        ctx = {k: str(rec.get(k, "")) for k in COMPAT_FIELDS}
        if "subset_signature" not in rec and "models" in rec:
            ctx["subset_signature"] = agg.model_set_signature(list(rec["models"]))
        sigs.add(comparability_signature(ctx))
    if len(sigs) > 1:
        raise BranchError(
            f"incompatible mix: {len(sigs)} distinct comparability signatures "
            "(release/fixation/timing/frame_offset/delay/subset differ); refusing to compare")
    return next(iter(sigs)) if sigs else ""


# ── common model set ─────────────────────────────────────────────────────────


def _normalize_rows(raw_rows: Sequence[dict]) -> list[dict]:
    """Per-model rows with compact metric names + model/status preserved."""
    out = []
    for r in raw_rows:
        norm = agg.normalize_metric_row(r)
        norm["model"] = r.get("model", "")
        norm["status"] = r.get("status", "")
        out.append(norm)
    return out


def common_model_set(candidate_rows: dict[str, list[dict]]) -> set[str]:
    """Intersection of status-ok models across ALL candidates."""
    ok_sets = []
    for rows in candidate_rows.values():
        ok_sets.append({r["model"] for r in rows if str(r.get("status")) == "ok" and r.get("model")})
    if not ok_sets:
        return set()
    common = set(ok_sets[0])
    for s in ok_sets[1:]:
        common &= s
    return common


def means_on_models(rows: Sequence[dict], models: set[str], metric_keys=METRIC_KEYS) -> dict:
    """Mean of each compact metric over the given models (status-ok only)."""
    sel = [r for r in rows if r.get("model") in models and str(r.get("status")) == "ok"]
    out: dict[str, float | None] = {}
    for m in metric_keys:
        vals = [agg._to_float(r.get(m)) for r in sel]
        vals = [v for v in vals if v is not None]
        out[m] = (sum(vals) / len(vals)) if vals else None
    return out


# ── candidate construction ───────────────────────────────────────────────────


@dataclass
class Candidate:
    candidate_id: str          # stable, human-readable (the swept value)
    sub_stage: str             # coarse | refined | sweep
    axis: str                  # sigma | timing | frame_offset
    axis_value: Any            # the swept magnitude
    sigma_value: float         # sigma magnitude (sigma_deg or sigma_multiplier)
    point: dict = field(default_factory=dict)   # evaluator point
    table_sigma: dict = field(default_factory=dict)  # sigma_* table columns
    delay_seconds: float = 0.0
    frame_offset: int = 0


def _task_tag(method: str, axis: str, candidate_id: str, window_mode: str) -> str:
    raw = f"{method}_{axis}_{candidate_id}_w{window_mode}"
    return raw


def _sigma_candidate(request: dict, spec: MethodSpec, sigma_value: float,
                     *, sub_stage: str) -> Candidate:
    dataset = request["dataset"]
    sig_fields = spec.expand_sigma(dataset, sigma_value)
    delay = float(request.get("fixed", {}).get("delay_seconds", 0.0))
    fo = int(request.get("fixed", {}).get("frame_offset", 0))
    window_mode = request.get("window_mode", "one_turn_from_start")
    cid = f"s{_fmt_num(sigma_value)}"
    point = {
        "dataset": dataset, "method": spec.method, "axis": "sigma",
        "window_mode": window_mode, "delay_seconds": delay, "frame_offset": fo,
        "value": float(sigma_value),
    }
    point.update(sig_fields)
    point["task_tag"] = _task_tag(spec.method, "sigma", cid, window_mode)
    return Candidate(candidate_id=cid, sub_stage=sub_stage, axis="sigma",
                     axis_value=float(sigma_value), sigma_value=float(sigma_value),
                     point=point, table_sigma=dict(sig_fields),
                     delay_seconds=delay, frame_offset=fo)


def _axis_candidate(request: dict, spec: MethodSpec, axis: str, axis_value) -> Candidate:
    """timing (delay_seconds) or frame_offset candidate with sigma fixed."""
    dataset = request["dataset"]
    fixed_sigma = dict(request["fixed_sigma"])
    sigma_value = float(fixed_sigma.get(spec.sigma_param))
    window_mode = request.get("window_mode", "one_turn_from_start")
    if axis == "timing":
        delay = float(axis_value)
        fo = int(request.get("fixed", {}).get("frame_offset", 0))
        cid = f"d{_fmt_num(delay)}"
        value = delay
    elif axis == "frame_offset":
        delay = float(request.get("fixed", {}).get("delay_seconds", 0.0))
        fo = int(axis_value)
        cid = f"fo{fo}"
        value = float(fo)
    else:
        raise BranchError(f"unsupported axis {axis!r}")
    point = {
        "dataset": dataset, "method": spec.method, "axis": axis,
        "window_mode": window_mode, "delay_seconds": delay, "frame_offset": fo,
        "value": value,
    }
    point.update({k: v for k, v in fixed_sigma.items()
                  if k in ("sigma_deg", "sigma_px", "sigma_screen", "sigma_multiplier", "radius_sigma_mult")})
    point["task_tag"] = _task_tag(spec.method, axis, cid, window_mode)
    return Candidate(candidate_id=cid, sub_stage="sweep", axis=axis, axis_value=axis_value,
                     sigma_value=sigma_value, point=point,
                     table_sigma={k: fixed_sigma.get(k) for k in
                                  ("sigma_deg", "sigma_px", "sigma_screen", "sigma_multiplier", "radius_sigma_mult")
                                  if fixed_sigma.get(k) is not None},
                     delay_seconds=delay, frame_offset=fo)


def _fmt_num(v) -> str:
    f = float(v)
    return str(int(f)) if f.is_integer() else str(f)


# ── validation ───────────────────────────────────────────────────────────────


def validate_request(request: dict) -> None:
    for field_name in ("dataset", "method", "stage", "models", "subset_name", "repo_commit"):
        if field_name not in request:
            raise BranchError(f"request.{field_name} missing")
    if not isinstance(request["models"], list) or not request["models"]:
        raise BranchError("request.models must be a non-empty list")
    if len(set(request["models"])) != len(request["models"]):
        raise BranchError("request.models must be unique")
    if not isinstance(request["repo_commit"], str) or len(request["repo_commit"]) != 40:
        raise BranchError("request.repo_commit must be a 40-char sha")
    stage = request["stage"]
    if stage not in ("sigma", "timing", "frame_offset"):
        raise BranchError(f"unsupported stage {stage!r}")
    if stage in ("timing", "frame_offset"):
        if "fixed_sigma" not in request:
            raise BranchError(f"stage {stage!r} requires request.fixed_sigma (the chosen sigma)")
        if "axis_values" not in request or not request["axis_values"]:
            raise BranchError(f"stage {stage!r} requires non-empty request.axis_values")
        if len(set(request["axis_values"])) != len(request["axis_values"]):
            raise BranchError("request.axis_values must be unique")


def _git(*args: str) -> str:
    repo_root = _DIR.parents[1]
    try:
        return subprocess.check_output(
            ["git", *args], cwd=repo_root, stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return ""


def _request_env(request: dict) -> dict[str, str]:
    env = request.get("resolved_env") or {}
    if not isinstance(env, dict):
        raise BranchError("request.resolved_env must be a dict when provided")
    return {
        str(k): str(v) for k, v in env.items()
        if str(k).strip() and str(v).strip()
    }


def _request_fixation_root(request: dict) -> str | None:
    env = _request_env(request)
    return env.get("FIXATION_ROOT") or env.get("REPROJECT_PROCESSED_FIXATIONS_ROOT")


def _require_current_checkout_commit(request: dict) -> None:
    expected = request["repo_commit"]
    actual = _git("rev-parse", "HEAD")
    if not actual:
        raise RuntimeGateError("unable to resolve current git HEAD for repo-commit gate")
    # Allow HEAD to be a descendant of the pinned commit (newer checkout is safe;
    # older checkout — where expected is not an ancestor of HEAD — is rejected).
    if actual == expected:
        return
    repo_root = _DIR.parents[1]
    try:
        subprocess.check_call(
            ["git", "merge-base", "--is-ancestor", expected, "HEAD"],
            cwd=repo_root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except subprocess.CalledProcessError:
        raise RuntimeGateError(
            f"checkout HEAD {actual!r} does not contain request.repo_commit {expected!r} "
            f"— the repo may be on an older or divergent branch"
        )


def _require_request_runtime(request: dict, spec: MethodSpec) -> None:
    python = request.get("python") or os.environ.get("REPROJECT_PYTHON") or sys.executable
    pf.require(
        request["dataset"], spec.method,
        fixation_root=_request_fixation_root(request),
        env=dict(os.environ, **_request_env(request)),
    )
    pf.require_runtime_dependencies(spec.method, python=python)


def _real_invoke_for_request(request: dict, spec: MethodSpec, *, results_root: Path):
    branch_family = _branch_family(spec.method, request["stage"])
    signature = comparability_signature(comparability_context(request))
    work_dir = (
        Path(results_root) / "ablation" / "_work" / branch_family
        / request["dataset"] / spec.method / signature
    )
    runtime_env = _request_env(request)
    fixation_root = _request_fixation_root(request)
    timeout = int(request.get("timeout_seconds_per_invocation") or 1800)
    python = request.get("python") or os.environ.get("REPROJECT_PYTHON") or sys.executable
    nice_prefix = _server_nice_prefix(request)

    def invoke(point: dict, model: str) -> dict:
        return ev.subprocess_evaluator_invoke(
            point, model,
            work_dir=work_dir,
            fixation_root=fixation_root,
            timeout=timeout,
            preflight=False,
            env=runtime_env,
            python=python,
            nice_prefix=nice_prefix or None,
        )

    return invoke


# ── candidate planning ───────────────────────────────────────────────────────


def plan_candidates(request: dict, spec: MethodSpec) -> list[Candidate]:
    """Build the full candidate pool. For sigma: coarse grid, plus a refined grid
    around the coarse common-set best when request.sigma.refined is set. For
    timing/frame_offset: one candidate per axis value."""
    stage = request["stage"]
    if stage == "sigma":
        coarse = [_sigma_candidate(request, spec, s, sub_stage="coarse") for s in spec.coarse_grid]
        return coarse
    return [_axis_candidate(request, spec, stage, v) for v in request["axis_values"]]


def refined_candidates(request: dict, spec: MethodSpec, coarse_best_sigma: float) -> list[Candidate]:
    grid = spec.refined_grid(coarse_best_sigma)
    coarse_set = {round(s, 6) for s in spec.coarse_grid}
    return [_sigma_candidate(request, spec, s, sub_stage="refined")
            for s in grid if round(s, 6) not in coarse_set]


# ── execution ────────────────────────────────────────────────────────────────


def _candidate_run_id(params: dict, signature: str) -> str:
    """Comparability-aware aggregate run_id. `agg.run_signature` only hashes the
    swept numeric params + model_set_signature, so two runs that differ ONLY in
    release_tag/fixation_data_tag/timing/frame_offset/delay policy would collide
    and supersede each other. Suffixing the comparability signature keeps them
    distinct in the aggregate jsonl/csv (P1-2)."""
    return f"{agg.run_signature(params)}_cmp{signature}"


def _make_params(request: dict, spec: MethodSpec, cand: Candidate, branch_family: str,
                 signature: str) -> dict:
    models = list(request["models"])
    params = {
        "stage_name": branch_family,
        "dataset": request["dataset"], "method": spec.method,
        "texture_type": request.get("texture_type", ""),
        "timing_contract": request.get("timing_contract", "one_turn_from_start"),
        "window_mode": request.get("window_mode", "one_turn_from_start"),
        "delay_seconds": float(cand.delay_seconds),
        "delay_frames": int(round(float(cand.delay_seconds) * 30)),
        "frame_offset": int(cand.frame_offset),
        "fixation_data_tag": request.get("fixation_data_tag", ""),
        "model_subset_name": request["subset_name"],
        "model_subset_size": len(models),
        "model_set_signature": agg.model_set_signature(models),
        "repo_commit": request["repo_commit"],
        "release_tag": request.get("release_tag", ""),
        "branch": request.get("branch", ""),
        "command": f"dataset_ablation_core.run_branch  # {cand.axis}={cand.axis_value}",
        "notes": f"family={branch_family} sub_stage={cand.sub_stage} cmp={signature}",
        # Branch artifacts AND the aggregate live under a signature-scoped path so an
        # incompatible run can never overwrite a prior one's markers/aggregate (P1-1).
        "storage_parts": [branch_family, request["dataset"], spec.method, signature],
    }
    for k in ("sigma_deg", "sigma_px", "sigma_screen", "sigma_multiplier", "radius_sigma_mult"):
        if cand.table_sigma.get(k) is not None:
            params[k] = cand.table_sigma[k]
    return params


def _run_candidate(request: dict, spec: MethodSpec, cand: Candidate, *,
                   results_root: Path, invoke, branch_family: str, signature: str,
                   existing_run_ids: set[str]) -> tuple[dict, list[dict]]:
    """Run all models for one candidate, record the run, return (params, normalized rows)."""
    models = list(request["models"])
    params = _make_params(request, spec, cand, branch_family, signature)
    run_id = _candidate_run_id(params, signature)
    params["run_id"] = run_id
    max_workers = int(request.get("max_workers") or _DEFAULT_MAX_WORKERS)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(invoke, cand.point, m) for m in models]
        raw_rows = [f.result() for f in futures]
    agg.record_run(
        Path(results_root), params, raw_rows, run_id=run_id,
        command=str(params.get("command", "")),
        on_duplicate="supersede" if run_id in existing_run_ids else "error",
    )
    existing_run_ids.add(run_id)
    return params, _normalize_rows(raw_rows)


# ── selection + artifacts ────────────────────────────────────────────────────


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _branch_family(method: str, stage: str) -> str:
    return f"{method}_{stage}_dmlab"


def branch_dir_for(results_root: Path, request: dict, spec: MethodSpec) -> Path:
    """The signature-scoped branch directory for a request. Single source of truth
    for the layout, shared by run_branch and the server monitor/resume layer."""
    signature = comparability_signature(comparability_context(request))
    branch_family = _branch_family(spec.method, request["stage"])
    return (Path(results_root) / "ablation" / branch_family
            / request["dataset"] / spec.method / signature)


def _existing_branch_run_ids(branch_dir: Path) -> set[str]:
    """Seed the supersede set from any prior aggregate so a re-run of the same
    branch supersedes its earlier rows instead of erroring on duplicate run_id."""
    p = branch_dir / "aggregate" / "ablation_runs.jsonl"
    if not p.is_file():
        return set()
    out: set[str] = set()
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rid = json.loads(line).get("run_id")
        except json.JSONDecodeError:
            continue
        if rid:
            out.add(rid)
    return out


def select_branch_best(candidates: list[Candidate], cand_rows: dict[str, list[dict]],
                       cand_params: dict[str, dict]) -> dict:
    """The fair selector: intersect surviving models across all candidates, mean
    metrics on that intersection, rank by mean CC."""
    n_total = len(next(iter(cand_rows.values()))) if cand_rows else 0
    common = common_model_set(cand_rows)
    n_common = len(common)
    coverage_common = (n_common / n_total) if n_total else 0.0

    per_candidate = []
    for cand in candidates:
        rows = cand_rows[cand.candidate_id]
        n_ok_raw = sum(1 for r in rows if str(r.get("status")) == "ok")
        common_means = means_on_models(rows, common)
        raw_means = means_on_models(rows, {r["model"] for r in rows if str(r.get("status")) == "ok"})
        per_candidate.append({
            "candidate_id": cand.candidate_id,
            "sub_stage": cand.sub_stage,
            "axis": cand.axis, "axis_value": cand.axis_value,
            "sigma_value": cand.sigma_value,
            "n_ok_raw": n_ok_raw,
            "coverage_raw": (n_ok_raw / n_total) if n_total else 0.0,
            "mean_common": common_means,
            "mean_raw": raw_means,
            "run_id": cand_params[cand.candidate_id]["run_id"],
        })

    summary = {
        "n_total_models": n_total,
        "n_common_models": n_common,
        "coverage_common": round(coverage_common, 4),
        "common_models": sorted(common),
        "rank_metric": f"mean_{RANK_METRIC}_on_common_set",
        "per_candidate": per_candidate,
    }

    if n_common == 0 or coverage_common < COVERAGE_COMMON_MIN:
        summary["promoted"] = False
        summary["hold_reason"] = (
            "empty_common_set" if n_common == 0
            else f"coverage_common {coverage_common:.3f} < {COVERAGE_COMMON_MIN}")
        return summary

    rankable = [c for c in per_candidate if c["mean_common"].get(RANK_METRIC) is not None]
    if not rankable:
        summary["promoted"] = False
        summary["hold_reason"] = "no_rankable_candidate"
        return summary
    rankable.sort(key=lambda c: c["mean_common"][RANK_METRIC], reverse=True)
    summary["promoted"] = True
    summary["best"] = rankable[0]
    return summary


def _branch_best_payload(request: dict, spec: MethodSpec, best: dict,
                         common: list[str], signature: str) -> dict:
    cand = best
    # best_params carries the FULL fixed parameter set so a downstream branch can
    # consume it directly: sigma fields (+radius), and the chosen swept axis value.
    if request["stage"] == "sigma":
        best_params = dict(spec.expand_sigma(request["dataset"], best["sigma_value"]))
        best_params["delay_seconds"] = float(request.get("fixed", {}).get("delay_seconds", 0.0))
        best_params["frame_offset"] = int(request.get("fixed", {}).get("frame_offset", 0))
    else:
        best_params = {k: v for k, v in request["fixed_sigma"].items()
                       if k in ("sigma_deg", "sigma_px", "sigma_screen",
                                "sigma_multiplier", "radius_sigma_mult")}
        if request["stage"] == "timing":
            best_params["delay_seconds"] = float(best["axis_value"])
            best_params["frame_offset"] = int(request.get("fixed", {}).get("frame_offset", 0))
        else:  # frame_offset
            best_params["delay_seconds"] = float(request.get("fixed", {}).get("delay_seconds", 0.0))
            best_params["frame_offset"] = int(best["axis_value"])
    return {
        "family": _branch_family(spec.method, request["stage"]),
        "dataset": request["dataset"], "method": spec.method, "stage": request["stage"],
        "selection_rule": "mean_CC_on_common_model_set",
        "promoted_at_utc": agg.utc_now_iso(),
        "best_candidate_id": cand["candidate_id"],
        "best_sub_stage": cand["sub_stage"],
        "best_axis_value": cand["axis_value"],
        "best_params": best_params,
        "best_mean_CC_common": cand["mean_common"].get("CC"),
        "best_mean_metrics_common": cand["mean_common"],
        "n_common_models": len(common),
        "common_model_set": list(common),
        "common_model_set_size": len(common),
        "subset_name": request["subset_name"],
        "repo_commit": request["repo_commit"],
        "comparability_signature": signature,
        "points_to": f"aggregate/ablation_runs.jsonl#run_id={cand['run_id']}",
    }


def _render_readme(request: dict, spec: MethodSpec, signature: str, summary: dict) -> str:
    lines = [
        f"# Dataset-method ablation branch — `{request['dataset']}` / `{spec.method}` / `{request['stage']}`",
        "",
        "**Sigma is selected per (dataset, method), NOT per model.** The winner is",
        "chosen by mean CC on the *common model set* (intersection of models that",
        "succeeded for every candidate), so no candidate can win on an easier subset.",
        "",
        "## Parameters",
        f"- dataset: `{request['dataset']}`  method: `{spec.method}`  stage: `{request['stage']}`",
        f"- subset: `{request['subset_name']}` (size {len(request['models'])})",
        f"- sigma_param: `{spec.sigma_param}`",
        f"- repo_commit: `{request['repo_commit']}`",
        f"- release_tag: `{request.get('release_tag','')}`  "
        f"fixation_data_tag: `{request.get('fixation_data_tag','')}`  "
        f"timing_contract: `{request.get('timing_contract','')}`",
        f"- frame_offset_policy: `{request.get('frame_offset_policy','')}`  "
        f"delay_policy: `{request.get('delay_policy','')}`",
        f"- comparability_signature: `{signature}`",
        "",
        "## Outcome",
        f"- n_total_models: {summary['n_total_models']}",
        f"- n_common_models: {summary['n_common_models']}  "
        f"(coverage_common = {summary['coverage_common']})",
        f"- promoted: `{summary.get('promoted')}`",
    ]
    if summary.get("promoted"):
        b = summary["best"]
        lines += [
            f"- branch_best: candidate `{b['candidate_id']}` "
            f"(sigma={b['sigma_value']}, sub_stage={b['sub_stage']})",
            f"- mean CC on common set: {b['mean_common'].get('CC')}",
        ]
    else:
        lines.append(f"- hold_reason: `{summary.get('hold_reason','')}`")
    lines += ["", "## Files", "- `manifest.json` — full request + signatures",
              "- `aggregate/ablation_runs.{jsonl,csv}` — every candidate run",
              "- `aggregate/common_model_summary.json` — common-set means per candidate",
              "- `branch_best.json` (promoted) or `_held.json` (held)", ""]
    return "\n".join(lines)


# ── shared dataset-method table ──────────────────────────────────────────────


def _table_path(results_root: Path) -> Path:
    p = Path(results_root)
    for part in DATASET_METHOD_TABLE_REL:
        p = p / part
    return p


def _table_row(request: dict, spec: MethodSpec, summary: dict, signature: str, *,
               results_root: Path, branch_best_path: Path | None,
               held_path: Path | None) -> dict:
    promoted = bool(summary.get("promoted"))
    if promoted:
        cand = summary["best"]
        means = cand["mean_common"]
        sigma_value = cand["sigma_value"]
        n_ok_raw = cand["n_ok_raw"]
        coverage_raw = round(cand["coverage_raw"], 4)
        sig_cols = _selected_sigma_columns(request, spec, cand)
        delay = sig_cols.pop("_delay")
        fo = sig_cols.pop("_frame_offset")
        notes = f"best_candidate={cand['candidate_id']} sub_stage={cand['sub_stage']}"
    else:
        means = {m: None for m in METRIC_KEYS}
        sigma_value = ""
        n_ok_raw = ""
        coverage_raw = ""
        sig_cols = {}
        delay = request.get("fixed", {}).get("delay_seconds", "")
        fo = request.get("fixed", {}).get("frame_offset", "")
        notes = f"HELD: {summary.get('hold_reason','')}"

    row = {c: "" for c in TABLE_COLUMNS}
    row.update({
        "dataset": request["dataset"], "method": spec.method, "stage": request["stage"],
        "sigma_param": spec.sigma_param, "sigma_value": sigma_value,
        "delay_seconds": delay, "frame_offset": fo,
        "subset_name": request["subset_name"], "subset_size": len(request["models"]),
        "n_ok_raw": n_ok_raw, "n_common_models": summary["n_common_models"],
        "repo_commit": request["repo_commit"], "release_tag": request.get("release_tag", ""),
        "fixation_data_tag": request.get("fixation_data_tag", ""),
        "timing_contract": request.get("timing_contract", ""),
        "results_root": str(results_root),
        "branch_best_path": str(branch_best_path) if branch_best_path else "",
        "held_path": str(held_path) if held_path else "",
        "promoted": promoted, "notes": notes,
        "comparability_signature": signature,
        "coverage_raw": coverage_raw,
        "coverage_common": summary["coverage_common"],
        "n_total_models": summary["n_total_models"],
    })
    row.update(sig_cols)
    for m in METRIC_KEYS:
        row[m] = means.get(m) if means.get(m) is not None else ""
    return row


def _selected_sigma_columns(request: dict, spec: MethodSpec, cand: dict) -> dict:
    """Reconstruct the sigma_* table cells for the winning candidate."""
    dataset = request["dataset"]
    out: dict = {"_delay": "", "_frame_offset": ""}
    if request["stage"] == "sigma":
        expanded = spec.expand_sigma(dataset, cand["sigma_value"])
        out.update(expanded)
        out["_delay"] = request.get("fixed", {}).get("delay_seconds", 0.0)
        out["_frame_offset"] = request.get("fixed", {}).get("frame_offset", 0)
    else:
        fixed_sigma = request["fixed_sigma"]
        for k in ("sigma_deg", "sigma_px", "sigma_screen", "sigma_multiplier", "radius_sigma_mult"):
            if fixed_sigma.get(k) is not None:
                out[k] = fixed_sigma[k]
        if request["stage"] == "timing":
            out["_delay"] = cand["axis_value"]
            out["_frame_offset"] = request.get("fixed", {}).get("frame_offset", 0)
        else:
            out["_delay"] = request.get("fixed", {}).get("delay_seconds", 0.0)
            out["_frame_offset"] = cand["axis_value"]
    return out


def update_dataset_method_table(results_root: Path, row: dict) -> Path:
    """Append-or-update the shared table. One row per (dataset, method, stage,
    comparability_signature): same key updates in place, a different signature
    appends a new row (incompatible runs never overwrite each other)."""
    import csv
    path = _table_path(results_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    key = ("dataset", "method", "stage", "comparability_signature")

    existing: list[dict] = []
    if path.is_file():
        with path.open() as fh:
            existing = list(csv.DictReader(fh))

    def _k(r):
        return tuple(str(r.get(c, "")) for c in key)

    replaced = False
    new_key = _k(row)
    for i, r in enumerate(existing):
        if _k(r) == new_key:
            existing[i] = {c: row.get(c, "") for c in TABLE_COLUMNS}
            replaced = True
            break
    if not replaced:
        existing.append({c: row.get(c, "") for c in TABLE_COLUMNS})

    fd, tmp = tempfile.mkstemp(prefix=".dataset_method_ablation.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=TABLE_COLUMNS, extrasaction="ignore")
            w.writeheader()
            for r in existing:
                w.writerow({c: _cell(r.get(c, "")) for c in TABLE_COLUMNS})
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path


def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.6f}"
    return str(v)


# ── top-level orchestration ──────────────────────────────────────────────────


def run_branch(request: dict, spec: MethodSpec, *, results_root: Path, invoke,
               update_table: bool = True) -> dict:
    """Run one (dataset, method, stage) branch end to end with common-model-set
    fair selection. Returns a result dict with the summary + artifact paths."""
    validate_request(request)
    if spec.method != request["method"]:
        raise BranchError(f"spec.method {spec.method!r} != request.method {request['method']!r}")

    context = comparability_context(request)
    signature = comparability_signature(context)
    branch_family = _branch_family(spec.method, request["stage"])
    # Signature-scoped branch dir: incompatible runs get distinct artifact roots and
    # can never overwrite each other's manifest/README/summary/branch_best (P1-1).
    branch_dir = branch_dir_for(results_root, request, spec)
    existing_run_ids: set[str] = _existing_branch_run_ids(branch_dir)

    candidates = plan_candidates(request, spec)
    cand_rows: dict[str, list[dict]] = {}
    cand_params: dict[str, dict] = {}
    for cand in candidates:
        params, rows = _run_candidate(
            request, spec, cand, results_root=results_root, invoke=invoke,
            branch_family=branch_family, signature=signature,
            existing_run_ids=existing_run_ids)
        cand_rows[cand.candidate_id] = rows
        cand_params[cand.candidate_id] = params

    # Optional refined sigma sub-stage around the coarse common-set best.
    if request["stage"] == "sigma" and request.get("sigma", {}).get("refined"):
        coarse_summary = select_branch_best(candidates, cand_rows, cand_params)
        if coarse_summary.get("promoted"):
            coarse_best_sigma = coarse_summary["best"]["sigma_value"]
            refined = refined_candidates(request, spec, coarse_best_sigma)
            for cand in refined:
                params, rows = _run_candidate(
                    request, spec, cand, results_root=results_root, invoke=invoke,
                    branch_family=branch_family, signature=signature,
                    existing_run_ids=existing_run_ids)
                cand_rows[cand.candidate_id] = rows
                cand_params[cand.candidate_id] = params
                candidates.append(cand)

    summary = select_branch_best(candidates, cand_rows, cand_params)

    # Artifacts.
    branch_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "request": request, "comparability_context": context,
        "comparability_signature": signature, "branch_family": branch_family,
        "generated_at_utc": agg.utc_now_iso(),
    }
    _atomic_write(branch_dir / "manifest.json", json.dumps(manifest, indent=2, default=str))
    _atomic_write(branch_dir / "aggregate" / "common_model_summary.json",
                  json.dumps(summary, indent=2, default=str))
    _atomic_write(branch_dir / "README.md", _render_readme(request, spec, signature, summary))

    branch_best_path = None
    held_path = None
    if summary.get("promoted"):
        payload = _branch_best_payload(request, spec, summary["best"],
                                       summary["common_models"], signature)
        branch_best_path = branch_dir / "branch_best.json"
        _atomic_write(branch_best_path, json.dumps(payload, indent=2, default=str))
        # clear any stale hold marker
        stale = branch_dir / "_held.json"
        if stale.exists():
            stale.unlink()
    else:
        payload = {
            "family": branch_family, "dataset": request["dataset"], "method": spec.method,
            "stage": request["stage"], "held_at_utc": agg.utc_now_iso(),
            "hold_reason": summary.get("hold_reason", ""),
            "n_total_models": summary["n_total_models"],
            "n_common_models": summary["n_common_models"],
            "coverage_common": summary["coverage_common"],
            "comparability_signature": signature,
        }
        held_path = branch_dir / "_held.json"
        _atomic_write(held_path, json.dumps(payload, indent=2, default=str))

    table_path = None
    if update_table:
        row = _table_row(request, spec, summary, signature, results_root=Path(results_root),
                         branch_best_path=branch_best_path, held_path=held_path)
        table_path = update_dataset_method_table(Path(results_root), row)

    return {
        "promoted": bool(summary.get("promoted")),
        "summary": summary,
        "branch_dir": branch_dir,
        "manifest_path": branch_dir / "manifest.json",
        "common_model_summary_path": branch_dir / "aggregate" / "common_model_summary.json",
        "branch_best_path": branch_best_path,
        "held_path": held_path,
        "dataset_method_table_path": table_path,
        "comparability_signature": signature,
    }
