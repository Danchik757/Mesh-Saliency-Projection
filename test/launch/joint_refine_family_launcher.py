"""Stage-2 joint-refine family launcher for cone_joint_refine and
screen_space_joint_refine (campaign plan Stage E, §2.5).

NON-DESTRUCTIVE, LOCAL ONLY by default. One family branch = one (dataset, method)
pair; one stage only. The launcher consumes ALL THREE authoritative upstream
`branch_best.json` markers for the method's chain:

    <method>_sigma:best        -> centre sigma
    <method>_timing:best       -> centre delay_seconds
    <method>_frame_offset:best -> centre frame_offset

It cross-validates that the three markers agree on the shared fixed axes (the
sigma packed into timing/frame_offset best_params must equal the sigma marker's
best, and the delay packed into frame_offset best_params must equal the timing
marker's best), then sweeps a small 3x3x3 local grid centred at
(sigma*, delay*, frame_offset*) with half-widths (+/-5%, +/-0.1 s, +/-15 frames).
The point of Stage E is to confirm the best region is real (not a saddle), so all
three axes vary together rather than one-axis-at-a-time.

Modeled on `frame_offset_family_launcher.py` / `timing_family_launcher.py`. Reuses
the existing aggregation + evaluator-sweep machinery; imports no baseline
evaluator.
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
    "cone_joint_refine": "cone",
    "screen_space_joint_refine": "screen_space",
}
# Each joint-refine family consumes the three upstream markers of its method chain.
UPSTREAM_FAMILIES = {
    "cone_joint_refine": {
        "sigma": "cone_sigma",
        "timing": "cone_timing",
        "frame_offset": "cone_frame_offset",
    },
    "screen_space_joint_refine": {
        "sigma": "screen_space_sigma",
        "timing": "screen_space_timing",
        "frame_offset": "screen_space_frame_offset",
    },
}
# The three consumes.* keys, in the canonical chain order.
CONSUMES_KEYS = ("sigma_branch_best", "timing_branch_best", "frame_offset_branch_best")

# Campaign-plan Stage-E half-widths (full_ablation_campaign_plan.md §2.5):
#   sigma   +/-5% (multiplicative)
#   delay   +/-0.1 s
#   frame   +/-15 frames
# 3 points per axis -> up to 27 points (fewer if an axis collapses, e.g. fo near 0).
SIGMA_HALF_WIDTH_FRAC = 0.05
DELAY_HALF_WIDTH_S = 0.1
FRAME_OFFSET_HALF_WIDTH = 15

COVERAGE_THRESHOLD = 0.70
ERROR_TYPE_MAX_SHARE = 0.30
NOISE_FLOOR_MULT = 0.5


class ManifestError(ValueError):
    """Raised when a joint-refine-family manifest fails validation."""


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
            f"unsupported joint_refine family {family!r}; known: {sorted(FAMILY_METHOD)}"
        )
    return FAMILY_METHOD[family]


def _upstream_families(family: str) -> dict[str, str]:
    return UPSTREAM_FAMILIES[family]


# ── numeric helpers ──────────────────────────────────────────────────────────


def _dedupe_floats(values: list[float]) -> list[float]:
    out: list[float] = []
    for v in values:
        fv = float(v)
        if all(abs(fv - e) > 1e-9 for e in out):
            out.append(fv)
    return out


def _dedupe_ints(values: list[int]) -> list[int]:
    out: list[int] = []
    for v in values:
        iv = int(v)
        if iv not in out:
            out.append(iv)
    return out


# ── smoke gate (mirror frame_offset) ─────────────────────────────────────────


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


# ── upstream marker consumption + cross-validation ───────────────────────────


def _load_one_marker(path_str: str, *, expected_family: str, sub: dict, which: str) -> dict:
    """Read one upstream branch_best.json and validate identity. Refuses sub-stage
    markers — only the authoritative root pointer is accepted."""
    if not path_str:
        raise ManifestError(
            f"joint_refine family requires consumes.{which} (path to upstream branch_best.json)")
    path = Path(path_str)
    if path.name != "branch_best.json":
        raise ManifestError(
            f"consumes.{which} must point at upstream branch_best.json, not a sub-stage marker")
    try:
        source = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"consumes.{which} unreadable: {path_str} ({exc})")
    if source.get("family") != expected_family:
        raise ManifestError(
            f"consumes.{which} family mismatch: expected {expected_family!r}, got {source.get('family')!r}")
    if source.get("dataset") != sub["dataset"] or source.get("method") != sub["method"]:
        raise ManifestError(f"consumes.{which} dataset/method mismatch with submission")
    if source.get("repo_commit") != sub["repo_commit"]:
        raise ManifestError(f"consumes.{which} repo_commit mismatch")
    if not source.get("points_to"):
        raise ManifestError(f"consumes.{which} branch_best.json missing points_to")
    if not isinstance(source.get("best_params"), dict) or not source["best_params"]:
        raise ManifestError(f"consumes.{which} branch_best.json missing best_params")
    return source


def _load_consumed_markers(manifest: dict) -> dict[str, dict]:
    """Read + validate all three upstream branch_best.json markers."""
    sub = manifest["submission"]
    fams = _upstream_families(sub["family"])
    consumes = manifest.get("consumes", {})
    sigma = _load_one_marker(consumes.get("sigma_branch_best"),
                             expected_family=fams["sigma"], sub=sub, which="sigma_branch_best")
    timing = _load_one_marker(consumes.get("timing_branch_best"),
                              expected_family=fams["timing"], sub=sub, which="timing_branch_best")
    frame_offset = _load_one_marker(consumes.get("frame_offset_branch_best"),
                                    expected_family=fams["frame_offset"], sub=sub,
                                    which="frame_offset_branch_best")
    return {"sigma": sigma, "timing": timing, "frame_offset": frame_offset}


def _approx(a, b) -> bool:
    return abs(float(a) - float(b)) <= 1e-6


def _sigma_identity(method: str, best_params: dict) -> float:
    """The single scalar that identifies the fixed sigma across markers: absolute
    sigma_deg for cone, the multiplier for screen_space."""
    if method == "cone":
        return float(best_params["sigma_deg"])
    return float(best_params["sigma_multiplier"])


def derive_center(method: str, markers: dict[str, dict]) -> dict:
    """Cross-validate the three markers agree on the shared fixed axes, then return
    the joint-refine grid centre.

    Consistency checks:
      - sigma marker's sigma == timing marker's packed sigma == frame_offset
        marker's packed sigma
      - timing marker's delay == frame_offset marker's packed delay
    """
    sigma_bp = markers["sigma"]["best_params"]
    timing_bp = markers["timing"]["best_params"]
    fo_bp = markers["frame_offset"]["best_params"]

    # delay must be packed by the timing/frame_offset writers.
    if "delay_seconds" not in timing_bp:
        raise ManifestError("timing branch_best.json:best_params missing 'delay_seconds'")
    if "delay_seconds" not in fo_bp:
        raise ManifestError("frame_offset branch_best.json:best_params missing 'delay_seconds'")
    if "frame_offset" not in fo_bp:
        raise ManifestError("frame_offset branch_best.json:best_params missing 'frame_offset'")

    s_sigma = _sigma_identity(method, sigma_bp)
    t_sigma = _sigma_identity(method, timing_bp)
    f_sigma = _sigma_identity(method, fo_bp)
    if not (_approx(s_sigma, t_sigma) and _approx(s_sigma, f_sigma)):
        raise ManifestError(
            "upstream sigma disagreement across markers: "
            f"sigma={s_sigma}, timing-packed={t_sigma}, frame_offset-packed={f_sigma}")

    t_delay = float(timing_bp["delay_seconds"])
    f_delay = float(fo_bp["delay_seconds"])
    if not _approx(t_delay, f_delay):
        raise ManifestError(
            f"upstream delay disagreement: timing={t_delay} vs frame_offset-packed={f_delay}")

    frame_offset = int(fo_bp["frame_offset"])
    if frame_offset < 0:
        raise ManifestError(f"frame_offset centre must be non-negative, got {frame_offset}")

    if method == "cone":
        return {
            "sigma_deg": float(sigma_bp["sigma_deg"]),
            "radius_sigma_mult": float(sigma_bp["radius_sigma_mult"]),
            "delay_seconds": t_delay,
            "frame_offset": frame_offset,
        }
    sigma_field = "sigma_px" if "sigma_px" in sigma_bp else "sigma_screen"
    if "base_sigma" not in sigma_bp:
        raise ManifestError("screen_space sigma branch_best.json:best_params missing 'base_sigma'")
    return {
        "sigma_multiplier": float(sigma_bp["sigma_multiplier"]),
        "sigma_field": sigma_field,
        "base_sigma": float(sigma_bp["base_sigma"]),
        "delay_seconds": t_delay,
        "frame_offset": frame_offset,
    }


def axis_grids(dataset: str, method: str, center: dict) -> tuple[list[float], list[float], list[int]]:
    """3x3x3 local grid axes around the centre (deduped at the edges)."""
    h = SIGMA_HALF_WIDTH_FRAC
    if method == "cone":
        s = center["sigma_deg"]
    else:
        s = center["sigma_multiplier"]
    sigma_axis = _dedupe_floats([round(s * (1 - h), 5), float(s), round(s * (1 + h), 5)])
    d = center["delay_seconds"]
    delay_axis = _dedupe_floats(
        [round(d - DELAY_HALF_WIDTH_S, 6), float(d), round(d + DELAY_HALF_WIDTH_S, 6)])
    f = int(center["frame_offset"])
    max_fo = rawd.one_turn_frame_offset_bounds(
        dataset, frame_offset=f, delay_seconds=d
    )["max_frame_offset"]
    fo_axis = _dedupe_ints(
        [max(0, f - FRAME_OFFSET_HALF_WIDTH), f, min(max_fo, f + FRAME_OFFSET_HALF_WIDTH)])
    return sigma_axis, delay_axis, fo_axis


def expected_point_count(dataset: str, method: str, center: dict) -> int:
    sigma_axis, delay_axis, fo_axis = axis_grids(dataset, method, center)
    return len(sigma_axis) * len(delay_axis) * len(fo_axis)


def validate_manifest(manifest: dict, *, check_smoke: bool = True) -> dict:
    sub = _require(manifest, "submission")
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

    markers = _load_consumed_markers(manifest)
    # All three upstream markers must agree on the shared common_model_set, and it
    # must equal the submission's subset_name (no subset drift mid-chain).
    subset_name = models.get("subset_name")
    for which, src in markers.items():
        if src.get("common_model_set") != subset_name:
            raise ManifestError(
                f"models.subset_name {subset_name!r} must equal {which} marker "
                f"common_model_set {src.get('common_model_set')!r}")
    if not isinstance(models.get("list"), list) or not models["list"]:
        raise ManifestError("models.list must be non-empty")

    # Cross-validate the markers agree and the grid is well-formed.
    derive_center(method, markers)

    if check_smoke:
        _validate_smoke(manifest, Path(sub["smoke_artifact"]))
    return manifest


# ── git checkout + runtime gates (mirror frame_offset) ───────────────────────


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
    "axis", "anchor_signature", "sigma_value", "delay_value", "frame_offset_value",
    "window_mode", "fixation_data_tag", "model",
)


def identity_sha1(**fields) -> str:
    missing = [f for f in _IDENTITY_FIELDS if f not in fields]
    if missing:
        raise ValueError(f"identity_sha1 missing fields: {missing}")
    payload = "|".join(f"{k}={fields[k]}" for k in _IDENTITY_FIELDS)
    return hashlib.sha1(payload.encode()).hexdigest()


def anchor_signature(method: str, center: dict) -> str:
    """Pack all THREE centre axes (sigma, delay, frame_offset) so a joint-refine
    rerun anchored at a different centre cannot collide with this one."""
    d = center["delay_seconds"]
    fo = int(center["frame_offset"])
    if method == "cone":
        return (f"sdeg={center['sigma_deg']};rsm={center['radius_sigma_mult']};"
                f"d={d};fo={fo}")
    field = center["sigma_field"]
    key = "spx" if field == "sigma_px" else "ssc"
    abs_sigma = round(center["base_sigma"] * center["sigma_multiplier"], 5)
    return f"smul={center['sigma_multiplier']};{key}={abs_sigma};d={d};fo={fo}"


def _task_tag_for_joint_point(method: str, point: dict, anchor_sig: str) -> str:
    """Raw per-task leaf must encode method + all three free axis values + the
    anchor so re-running at a different centre cannot reuse a stale report dir."""
    anchor_tag = anchor_sig.replace(";", "_")
    if method == "cone":
        sigma_tag = f"s{point['sigma_deg']}"
    else:
        sigma_tag = f"s{point['sigma_multiplier']}"
    delay_tag = f"d{point['delay_seconds']}"
    fo_tag = f"fo{int(point['frame_offset'])}"
    window_tag = str(point.get("window_mode", "")).strip()
    parts = [method, sigma_tag, delay_tag, fo_tag, anchor_tag]
    if window_tag:
        parts.insert(1, f"w{window_tag}")
    return "_".join(parts)


# ── resume helpers (mirror frame_offset) ─────────────────────────────────────

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


# ── promotion gates (mirror frame_offset) ────────────────────────────────────


def _row_status(row: dict) -> str:
    n_ok = int(row.get("n_ok") or 0)
    n_total = int(row.get("n_total_models") or 0)
    if n_ok == 0:
        return "RED"
    if n_ok == n_total:
        return "GREEN"
    return "AMBER"


def _point_key(row: dict, method: str) -> tuple:
    """Identify a joint-refine grid point from an aggregate row (the 3 free axes)."""
    sigma = row.get("sigma_deg") if method == "cone" else row.get("sigma_multiplier")
    return (sigma, row.get("delay_seconds"), row.get("frame_offset"))


def evaluate_stage(rows: list[dict], expected_points: int, *, method: str) -> dict:
    if expected_points <= 0:
        raise ValueError("expected_points must be > 0")
    statuses = {_point_key(r, method): _row_status(r) for r in rows}
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


# ── marker writers (mirror frame_offset) ─────────────────────────────────────


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


def _best_params_from_row(method: str, row: dict, center: dict) -> dict:
    """Reconstruct the refined optimum's best_params from the winning row."""
    delay = float(row["delay_seconds"])
    frame_offset = int(row["frame_offset"])
    if method == "cone":
        return {
            "sigma_deg": float(row["sigma_deg"]),
            "radius_sigma_mult": float(row.get("radius_sigma_mult") or center["radius_sigma_mult"]),
            "delay_seconds": delay,
            "frame_offset": frame_offset,
        }
    field = center["sigma_field"]
    return {
        "sigma_multiplier": float(row["sigma_multiplier"]),
        field: float(row.get(field) or (center["base_sigma"] * float(row["sigma_multiplier"]))),
        "base_sigma": center["base_sigma"],
        "delay_seconds": delay,
        "frame_offset": frame_offset,
    }


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


def _stage_points(manifest: dict, center: dict, anchor_sig: str) -> list[dict]:
    sub = manifest["submission"]
    method = sub["method"]
    sigma_axis, delay_axis, fo_axis = axis_grids(sub["dataset"], method, center)
    points = []
    for sigma in sigma_axis:
        for delay in delay_axis:
            for fo in fo_axis:
                point = {
                    "dataset": sub["dataset"], "method": method,
                    "axis": "joint_refine",
                    "window_mode": sub["window_mode"],
                    "delay_seconds": float(delay),
                    "frame_offset": int(fo),
                }
                if method == "cone":
                    point["sigma_deg"] = float(sigma)
                    point["radius_sigma_mult"] = float(center["radius_sigma_mult"])
                    sigma_value = float(sigma)
                else:
                    abs_sigma = round(center["base_sigma"] * float(sigma), 5)
                    point["sigma_multiplier"] = float(sigma)
                    point[center["sigma_field"]] = abs_sigma
                    sigma_value = float(sigma)
                point["sigma_value"] = sigma_value
                # `value` is the per-point numeric magnitude consumed by the mock
                # invoke and the evaluator --tag; delay/frame_offset reach the real
                # evaluator via their own flags and the full triple is captured in
                # task_tag (the raw per-task dir leaf), so this stays numeric.
                point["value"] = sigma_value
                point["task_tag"] = _task_tag_for_joint_point(method, point, anchor_sig)
                points.append(point)
    return points


def _execute_branch(manifest: dict, *, results_root: Path, branch_dir: Path,
                    invoke, resume_rows: dict[str, dict], center: dict, anchor_sig: str) -> None:
    sub = manifest["submission"]
    family = sub["family"]
    method = sub["method"]
    models = list(manifest["models"]["list"])
    points = _stage_points(manifest, center, anchor_sig)
    existing_run_ids = _existing_run_ids(branch_dir)

    def _identity_for(point: dict, model: str) -> str:
        return identity_sha1(
            repo_commit=sub["repo_commit"],
            family=family,
            dataset=sub["dataset"],
            method=method,
            texture_type=sub.get("texture_type", ""),
            axis="joint_refine",
            anchor_signature=anchor_sig,
            sigma_value=point["sigma_value"],
            delay_value=float(point["delay_seconds"]),
            frame_offset_value=int(point["frame_offset"]),
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
            "delay_seconds": float(point["delay_seconds"]),
            "delay_frames": int(round(float(point["delay_seconds"]) * 30)),
            "frame_offset": int(point["frame_offset"]),
            "fixation_data_tag": sub["fixation_data_tag"],
            "model_subset_name": manifest["models"]["subset_name"],
            "model_subset_size": len(models),
            "model_set_signature": agg.model_set_signature(models),
            "repo_commit": sub["repo_commit"],
            "branch": sub.get("branch", ""),
            "command": "joint_refine_family_launcher.run_joint_refine_branch",
            "notes": f"family={family} stage=sweep anchor={anchor_sig}",
            "storage_parts": [family, sub["dataset"], method],
        }
        if method == "cone":
            params["sigma_deg"] = float(point["sigma_deg"])
            params["radius_sigma_mult"] = float(point["radius_sigma_mult"])
        else:
            params["sigma_multiplier"] = float(point["sigma_multiplier"])
            params[center["sigma_field"]] = point[center["sigma_field"]]
        return params

    for point in points:
        params = _make_params(point)
        run_id = agg.run_signature(params)
        rows: list[dict] = []
        all_resumed = True
        for model in models:
            row = _wrapped_invoke(point, model)
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


def run_joint_refine_branch(manifest: dict, *, results_root: Path, invoke,
                            check_smoke: bool = True, check_runtime: bool = True) -> dict:
    """Top-level orchestration for one (family, dataset, method) submission."""
    validate_manifest(manifest, check_smoke=check_smoke)
    sub = manifest["submission"]
    method = sub["method"]
    markers = _load_consumed_markers(manifest)
    center = derive_center(method, markers)
    anchor_sig = anchor_signature(method, center)

    if check_runtime:
        _require_current_checkout_commit(manifest)
        _require_manifest_runtime(manifest)

    branch_dir = Path(results_root) / "ablation" / sub["family"] / sub["dataset"] / sub["method"]
    resume_rows = load_resume_ok_rows(branch_dir)
    _execute_branch(
        manifest, results_root=results_root, branch_dir=branch_dir,
        invoke=invoke, resume_rows=resume_rows, center=center, anchor_sig=anchor_sig,
    )

    rows = _aggregate_rows(branch_dir)
    gate = evaluate_stage(
        rows,
        expected_points=expected_point_count(sub["dataset"], method, center),
        method=method,
    )
    out = {"promoted": gate["promoted"], "branch_best_path": None, "held_path": None,
           "gate": gate, "center": center, "anchor_signature": anchor_sig}
    if not gate["promoted"]:
        out["held_path"] = _write_held(
            branch_dir, family=sub["family"],
            branch=f"{sub['dataset']}/{sub['method']}",
            failed_gates=gate["failed_gates"], gate_details=gate["gate_details"])
        return out

    best_params = _best_params_from_row(method, gate["best"], center)
    out["branch_best_path"] = _write_branch_best(
        branch_dir, family=sub["family"], source_row=gate["best"],
        gate=gate, best_params=best_params,
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
    ap = argparse.ArgumentParser(description="joint_refine family launcher (cone/screen_space).")
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
        print(f"[joint_refine] MANIFEST INVALID: {exc}", file=sys.stderr)
        return 2

    if args.validate_only:
        print("[joint_refine] manifest OK")
        return 0

    invoke = ev.make_mock_invoke() if args.mock else _real_invoke_for_manifest(
        manifest, results_root=args.results_root)
    try:
        result = run_joint_refine_branch(
            manifest, results_root=args.results_root, invoke=invoke,
            check_smoke=not args.skip_smoke_check,
            check_runtime=not (args.mock or args.skip_runtime_check))
    except (ManifestError, RuntimeGateError) as exc:
        print(f"[joint_refine] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    verdict = "PROMOTED" if result["promoted"] else "HELD"
    print(f"[joint_refine] {verdict} branch_best={result['branch_best_path']}")
    return 0 if result["promoted"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
