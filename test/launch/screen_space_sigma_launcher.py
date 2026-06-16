"""`screen_space_sigma` launcher (v1) — Stage-2 screen-space sigma family.

NON-DESTRUCTIVE, LOCAL ONLY by default. Encodes the screen_space_sigma family
from the Stage-2 design notes:
- one branch = one (dataset, "screen_space") pair;
- two internal sub-stages: `coarse` (5-point multiplier grid) then
  `refined`-or-skip (5-point grid centred at the coarse best multiplier).

The swept axis is `sigma_multiplier`; the launcher expands it to the dataset's
absolute evaluator sigma (`sigma_px` for 3DVA/SAL3D, `sigma_screen` for
MeshMamba tracks) before delegating execution to `run_evaluator_sweep`.
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


FAMILY = "screen_space_sigma"
METHOD = "screen_space"
SIGMA_PARAM = "sigma_multiplier"

COARSE_GRID: tuple[float, ...] = (0.5, 0.7, 1.0, 1.3, 1.5)
EDGE_EXPANSION: tuple[float, ...] = (0.35, 1.8)
REFINED_COEFS: tuple[float, ...] = (0.75, 0.875, 1.0, 1.125, 1.25)

BASE_SIGMAS: dict[str, tuple[str, float]] = {
    "3dva": ("sigma_px", 49.0),
    "sal3d": ("sigma_px", 26.3),
    "meshmamba_non_texture": ("sigma_screen", 0.05),
    "meshmamba_rgb_texture": ("sigma_screen", 0.05),
}

COVERAGE_THRESHOLD = 0.70
ERROR_TYPE_MAX_SHARE = 0.30
NOISE_FLOOR_MULT = 0.5
SKIP_REFINED_LEAD_MULT = 3.0


class ManifestError(ValueError):
    """Raised when a screen_space_sigma manifest fails validation."""


class RuntimeGateError(RuntimeError):
    """Raised when the local checkout/runtime is incompatible with a submission."""


def _require(d: dict, *keys: str) -> Any:
    node: Any = d
    for k in keys:
        if not isinstance(node, dict) or k not in node:
            raise ManifestError(f"manifest missing required field: {'.'.join(keys)}")
        node = node[k]
    return node


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


def _dataset_sigma_spec(dataset: str) -> tuple[str, float]:
    if dataset not in BASE_SIGMAS:
        raise ManifestError(f"unsupported dataset for {FAMILY}: {dataset!r}")
    return BASE_SIGMAS[dataset]


def _absolute_sigma_mapping(dataset: str, sigma_multiplier: float) -> dict[str, float]:
    sigma_field, base_sigma = _dataset_sigma_spec(dataset)
    return {sigma_field: round(base_sigma * float(sigma_multiplier), 5)}


def validate_manifest(manifest: dict, *, check_smoke: bool = True) -> dict:
    sub = _require(manifest, "submission")
    sweep = _require(manifest, "sweep")
    models = _require(manifest, "models")
    consumes = manifest.get("consumes", {})

    for field in (
        "family", "branch_stage", "dataset", "method", "texture_type",
        "repo_commit", "smoke_artifact", "fixation_data_tag",
        "window_mode", "delay_seconds", "frame_offset",
    ):
        if field not in sub:
            raise ManifestError(f"submission.{field} missing")

    if sub["family"] != FAMILY:
        raise ManifestError(f"submission.family must be {FAMILY!r}, got {sub['family']!r}")
    if sub["method"] != METHOD:
        raise ManifestError(f"submission.method must be {METHOD!r}, got {sub['method']!r}")
    if sub["branch_stage"] not in ("coarse", "refined"):
        raise ManifestError("submission.branch_stage must be coarse|refined")
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
    _dataset_sigma_spec(sub["dataset"])

    if sweep.get("sigma_param") != SIGMA_PARAM:
        raise ManifestError(f"sweep.sigma_param must be {SIGMA_PARAM!r}")
    if sweep.get("radius_sigma_mult") not in (None, ""):
        raise ManifestError("screen_space_sigma must not set sweep.radius_sigma_mult")
    sigma_values = sweep.get("sigma_values")
    if not (
        isinstance(sigma_values, list)
        and sigma_values
        and all(isinstance(v, (int, float)) for v in sigma_values)
    ):
        raise ManifestError("sweep.sigma_values must be a non-empty list of numbers")

    if sub["branch_stage"] == "coarse":
        expected = sorted(COARSE_GRID + EDGE_EXPANSION) if sweep.get("edge_expansion") else sorted(COARSE_GRID)
        if sorted(float(v) for v in sigma_values) != expected:
            raise ManifestError(
                f"coarse sweep.sigma_values must equal {expected}, got {sorted(float(v) for v in sigma_values)}"
            )
        if consumes:
            raise ManifestError("coarse stage must not have a consumes block")
    else:
        marker_path = consumes.get("coarse_best_marker")
        if not marker_path:
            raise ManifestError("refined stage requires consumes.coarse_best_marker")
        try:
            cb = json.loads(Path(marker_path).read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise ManifestError(f"coarse_best_marker unreadable: {marker_path} ({exc})")
        for field in ("family", "stage", "dataset", "method", "repo_commit", "best_params"):
            if field not in cb:
                raise ManifestError(f"coarse_best marker missing field: {field}")
        if (cb["family"], cb["stage"], cb["dataset"], cb["method"], cb["repo_commit"]) != (
            FAMILY, "coarse", sub["dataset"], METHOD, sub["repo_commit"]
        ):
            raise ManifestError("coarse_best marker mismatch with submission")
        expected_refined = refined_grid(cb["best_params"][SIGMA_PARAM])
        if sorted(float(v) for v in sigma_values) != expected_refined:
            raise ManifestError(
                f"refined sweep.sigma_values must equal {expected_refined}, got {sorted(float(v) for v in sigma_values)}"
            )

    if not isinstance(models.get("list"), list) or not models["list"]:
        raise ManifestError("models.list must be non-empty")
    if not models.get("subset_name"):
        raise ManifestError("models.subset_name must be non-empty")

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
        sub["dataset"], METHOD,
        fixation_root=_submission_fixation_root(manifest),
        env=_submission_env(manifest),
    )
    pf.require_runtime_dependencies(METHOD, python=sub["python"])


_IDENTITY_FIELDS = (
    "repo_commit", "stage_name", "dataset", "method", "texture_type",
    "sigma_param", "sigma_value", "radius_sigma_mult", "window_mode",
    "delay_seconds", "frame_offset", "fixation_data_tag", "model",
)


def identity_sha1(**fields) -> str:
    missing = [f for f in _IDENTITY_FIELDS if f not in fields]
    if missing:
        raise ValueError(f"identity_sha1 missing fields: {missing}")
    payload = "|".join(f"{k}={fields[k]}" for k in _IDENTITY_FIELDS)
    return hashlib.sha1(payload.encode()).hexdigest()


def refined_grid(sigma_star: float, *, coefs: tuple[float, ...] = REFINED_COEFS) -> list[float]:
    return sorted({round(c * float(sigma_star), 2) for c in coefs})


def _row_status(row: dict) -> str:
    n_ok = int(row.get("n_ok") or 0)
    n_total = int(row.get("n_total_models") or 0)
    if n_ok == 0:
        return "RED"
    if n_ok == n_total:
        return "GREEN"
    return "AMBER"


def evaluate_stage(rows: list[dict], expected_points: int) -> dict:
    if expected_points <= 0:
        raise ValueError("expected_points must be > 0")
    statuses = {r.get(SIGMA_PARAM): _row_status(r) for r in rows}
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


def decide_skip_refined(gate_result: dict, *, grid: tuple[float, ...] = COARSE_GRID,
                        force_refined: bool = False) -> bool:
    if force_refined or not gate_result.get("promoted"):
        return False
    best = gate_result["best"]
    grid_sorted = sorted(grid)
    sigma_star = float(best.get(SIGMA_PARAM))
    if sigma_star == grid_sorted[0] or sigma_star == grid_sorted[-1]:
        return False
    second_cc = gate_result.get("second_best_CC")
    noise = gate_result.get("noise_floor_CC", 0.0)
    if second_cc is None:
        return False
    return (gate_result["best_CC"] - second_cc) >= SKIP_REFINED_LEAD_MULT * noise


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


def _stage_marker_payload(stage: str, manifest: dict, gate_result: dict, *,
                          best_artifact_run_id: str | None,
                          skip_refined: bool = False, promoted_at_utc: str | None = None) -> dict:
    sub = manifest["submission"]
    best = gate_result["best"]
    sigma_multiplier = float(best[SIGMA_PARAM])
    sigma_field, base_sigma = _dataset_sigma_spec(sub["dataset"])
    absolute_sigma = float(best.get(sigma_field) or _absolute_sigma_mapping(sub["dataset"], sigma_multiplier)[sigma_field])
    coarse_grid_values = sorted(float(v) for v in manifest["sweep"]["sigma_values"])

    return {
        "family": FAMILY,
        "stage": stage,
        "dataset": sub["dataset"],
        "method": METHOD,
        "texture_type": sub.get("texture_type", ""),
        "repo_commit": sub["repo_commit"],
        "promoted_at_utc": promoted_at_utc or agg.utc_now_iso(),
        "common_model_set": manifest["models"]["subset_name"],
        "n_models_used": len(manifest["models"]["list"]),
        "best_params": {
            SIGMA_PARAM: sigma_multiplier,
            sigma_field: absolute_sigma,
            "base_sigma": base_sigma,
        },
        "best_artifact_run_id": best_artifact_run_id or best.get("artifact_run_id", ""),
        "best_CC": gate_result["best_CC"],
        "second_best_CC": gate_result.get("second_best_CC"),
        "third_best_CC": gate_result.get("third_best_CC"),
        "noise_floor_CC": gate_result.get("noise_floor_CC", 0.0),
        "is_interior_best": bool(
            stage == "coarse"
            and sigma_multiplier in coarse_grid_values
            and 0 < coarse_grid_values.index(sigma_multiplier) < len(coarse_grid_values) - 1
        ) if stage == "coarse" else None,
        "skip_refined_recommended": skip_refined if stage == "coarse" else None,
    }


def write_coarse_best(stage_dir: Path, manifest: dict, gate_result: dict, *,
                      skip_refined: bool) -> Path:
    payload = _stage_marker_payload("coarse", manifest, gate_result,
                                    best_artifact_run_id=None, skip_refined=skip_refined)
    out = stage_dir / "coarse_best.json"
    _atomic_write_json(out, payload)
    return out


def write_final_best(stage_dir: Path, manifest: dict, gate_result: dict) -> Path:
    payload = _stage_marker_payload("refined", manifest, gate_result, best_artifact_run_id=None)
    out = stage_dir / "final_best.json"
    _atomic_write_json(out, payload)
    return out


def write_branch_best(branch_dir: Path, *, stage: str, points_to: str, source: dict) -> Path:
    payload = {
        "family": FAMILY,
        "dataset": source["dataset"],
        "method": METHOD,
        "stage": stage,
        "points_to": points_to,
        "repo_commit": source["repo_commit"],
        "promoted_at_utc": agg.utc_now_iso(),
        "best_params": source["best_params"],
        "common_model_set": source["common_model_set"],
        "n_models_used": source["n_models_used"],
        "noise_floor_CC": source["noise_floor_CC"],
        "best_CC": source["best_CC"],
    }
    out = branch_dir / "branch_best.json"
    _atomic_write_json(out, payload)
    return out


def write_held(stage_dir: Path, *, manifest: dict, failed_gates: list[str],
               gate_details: dict, suggestion: str = "") -> Path:
    sub = manifest["submission"]
    payload = {
        "family": FAMILY,
        "stage": sub["branch_stage"],
        "branch": f"{sub['dataset']}/{METHOD}",
        "held_at_utc": agg.utc_now_iso(),
        "failed_gates": failed_gates,
        "gate_details": gate_details,
        "next_action_suggestion": suggestion or "review gates and resubmit",
    }
    out = stage_dir / "_held.json"
    _atomic_write_json(out, payload)
    return out


def emit_refined_manifest_stub(coarse_manifest: dict, coarse_best_marker_path: Path,
                               out_path: Path) -> Path:
    sub = dict(coarse_manifest["submission"])
    sub["branch_stage"] = "refined"
    sigma_star = json.loads(Path(coarse_best_marker_path).read_text())["best_params"][SIGMA_PARAM]
    stub = {
        "submission": sub,
        "sweep": {"sigma_param": SIGMA_PARAM, "sigma_values": refined_grid(sigma_star), "edge_expansion": False},
        "models": coarse_manifest["models"],
        "consumes": {"coarse_best_marker": str(coarse_best_marker_path)},
        "_note": "v1 stub. Review and re-approve before submitting.",
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(stub, indent=2, default=str))
    return out_path


def load_resume_ok_rows(stage_dir: Path) -> dict[str, dict]:
    reusable: dict[str, dict] = {}
    runs = stage_dir / "runs"
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


def _stage_dirs(results_root: Path, manifest: dict) -> tuple[Path, Path, Path]:
    sub = manifest["submission"]
    branch = Path(results_root) / "ablation" / FAMILY / sub["dataset"] / METHOD
    current = branch / sub["branch_stage"]
    refined = branch / "refined"
    return branch, current, refined


def _stage_aggregate_rows(stage_dir: Path) -> list[dict]:
    p = stage_dir / "aggregate" / "ablation_runs.jsonl"
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


def _existing_run_ids(stage_dir: Path) -> set[str]:
    return {r.get("run_id") for r in _stage_aggregate_rows(stage_dir) if r.get("run_id")}


def _execute_stage(manifest: dict, *, results_root: Path, stage_dir: Path, invoke,
                   resume_rows: dict[str, dict]) -> None:
    sub = manifest["submission"]
    sigma_values = [float(v) for v in manifest["sweep"]["sigma_values"]]
    models = list(manifest["models"]["list"])
    stage_name = f"{FAMILY}_{sub['branch_stage']}"
    sigma_field, base_sigma = _dataset_sigma_spec(sub["dataset"])

    points = []
    for multiplier in sigma_values:
        point = ev.make_sigma_grid(
            sub["dataset"], METHOD, sigma_param=SIGMA_PARAM, sigma_values=[multiplier],
            delay_seconds=float(sub["delay_seconds"]),
            window_mode=sub["window_mode"],
        )[0]
        point["frame_offset"] = int(sub["frame_offset"])
        point.update(_absolute_sigma_mapping(sub["dataset"], multiplier))
        points.append(point)

    def _identity_for(point: dict, model: str) -> str:
        return identity_sha1(
            repo_commit=sub["repo_commit"], stage_name=stage_name,
            dataset=sub["dataset"], method=METHOD,
            texture_type=sub.get("texture_type", ""), sigma_param=SIGMA_PARAM,
            sigma_value=float(point[SIGMA_PARAM]),
            radius_sigma_mult="",
            window_mode=sub["window_mode"], delay_seconds=float(sub["delay_seconds"]),
            frame_offset=int(sub["frame_offset"]),
            fixation_data_tag=sub["fixation_data_tag"], model=model,
        )

    def _make_params(point: dict) -> dict:
        return {
            "stage_name": stage_name,
            "dataset": sub["dataset"], "method": METHOD,
            "texture_type": sub.get("texture_type", ""),
            "timing_contract": "one_turn_from_start",
            "window_mode": sub["window_mode"],
            "delay_seconds": sub["delay_seconds"],
            "delay_frames": int(round(float(sub["delay_seconds"]) * 30)),
            "frame_offset": sub["frame_offset"],
            "sigma_multiplier": point[SIGMA_PARAM],
            sigma_field: point[sigma_field],
            "fixation_data_tag": sub["fixation_data_tag"],
            "model_subset_name": manifest["models"]["subset_name"],
            "model_subset_size": len(models),
            "model_set_signature": agg.model_set_signature(models),
            "repo_commit": sub["repo_commit"],
            "branch": sub.get("branch", ""),
            "command": "screen_space_sigma_launcher.run_screen_space_sigma_branch",
            "notes": f"family={FAMILY} stage={sub['branch_stage']} base_sigma={base_sigma} {sigma_field}={point[sigma_field]}",
            "storage_parts": [FAMILY, sub["dataset"], METHOD, sub["branch_stage"]],
        }

    existing_run_ids = _existing_run_ids(stage_dir)
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
            command=str(params.get("command", "")),
            on_duplicate="supersede" if run_id in existing_run_ids else "error",
        )


def run_screen_space_sigma_branch(manifest: dict, *, results_root: Path, invoke,
                                  check_smoke: bool = True) -> dict:
    validate_manifest(manifest, check_smoke=check_smoke)
    sub = manifest["submission"]
    branch_dir, stage_dir, refined_dir = _stage_dirs(results_root, manifest)

    resume_rows = load_resume_ok_rows(stage_dir)
    _execute_stage(
        manifest, results_root=results_root, stage_dir=stage_dir,
        invoke=invoke, resume_rows=resume_rows,
    )

    rows = _stage_aggregate_rows(stage_dir)
    expected_points = len(manifest["sweep"]["sigma_values"])
    gate = evaluate_stage(rows, expected_points)

    out: dict = {
        "stage": sub["branch_stage"], "promoted": gate["promoted"],
        "skip_refined": None, "coarse_best_path": None, "final_best_path": None,
        "branch_best_path": None, "held_path": None,
        "refined_manifest_stub_path": None, "gate": gate,
    }

    if not gate["promoted"]:
        out["held_path"] = write_held(
            stage_dir, manifest=manifest,
            failed_gates=gate["failed_gates"],
            gate_details=gate["gate_details"],
        )
        return out

    if sub["branch_stage"] == "coarse":
        skip = decide_skip_refined(gate, force_refined=bool(sub.get("force_refined")))
        out["skip_refined"] = skip
        cb_path = write_coarse_best(stage_dir, manifest, gate, skip_refined=skip)
        out["coarse_best_path"] = cb_path
        if skip:
            out["branch_best_path"] = write_branch_best(
                branch_dir, stage="coarse_skipped_refine",
                points_to="coarse/coarse_best.json",
                source=json.loads(cb_path.read_text()),
            )
        else:
            stub = refined_dir / "refined_manifest_stub.json"
            out["refined_manifest_stub_path"] = emit_refined_manifest_stub(manifest, cb_path, stub)
    else:
        fb_path = write_final_best(stage_dir, manifest, gate)
        out["final_best_path"] = fb_path
        out["branch_best_path"] = write_branch_best(
            branch_dir, stage="refined", points_to="refined/final_best.json",
            source=json.loads(fb_path.read_text()),
        )
    return out


def _real_invoke_for_manifest(manifest: dict, *, results_root: Path):
    sub = manifest["submission"]
    work_dir = (
        Path(results_root) / "ablation" / "_work" / FAMILY
        / sub["dataset"] / METHOD / sub["branch_stage"]
    )
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
    ap = argparse.ArgumentParser(description="screen_space_sigma launcher (v1).")
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--results-root", type=Path, default=Path("results"))
    ap.add_argument("--validate-only", action="store_true",
                    help="Run manifest + smoke validation only; do not execute.")
    ap.add_argument("--mock", action="store_true",
                    help="Use the deterministic ev.make_mock_invoke (no subprocess).")
    ap.add_argument("--skip-smoke-check", action="store_true",
                    help="Skip the smoke-artifact check (validator development only).")
    args = ap.parse_args()

    manifest = json.loads(args.manifest.read_text())
    try:
        validate_manifest(manifest, check_smoke=not args.skip_smoke_check)
    except ManifestError as exc:
        print(f"[screen_space_sigma] MANIFEST INVALID: {exc}", file=sys.stderr)
        return 2

    if args.validate_only:
        print("[screen_space_sigma] manifest OK")
        return 0
    if args.mock:
        invoke = ev.make_mock_invoke()
    else:
        try:
            _require_current_checkout_commit(manifest)
            _require_manifest_runtime(manifest)
        except (RuntimeGateError, pf.PreflightError) as exc:
            print(f"[screen_space_sigma] RUNTIME GATE FAILED: {exc}", file=sys.stderr)
            return 2
        invoke = _real_invoke_for_manifest(manifest, results_root=args.results_root)

    result = run_screen_space_sigma_branch(
        manifest, results_root=args.results_root, invoke=invoke,
        check_smoke=not args.skip_smoke_check,
    )
    verdict = "PROMOTED" if result["promoted"] else "HELD"
    print(
        f"[screen_space_sigma] {verdict} stage={result['stage']} "
        f"skip_refined={result['skip_refined']} "
        f"branch_best={result['branch_best_path']}"
    )
    return 0 if result["promoted"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
