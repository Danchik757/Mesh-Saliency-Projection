"""Local preflight + one-point smoke gate for Stage-2 ablation automation.

NON-DESTRUCTIVE, LOCAL ONLY. This is the launcher-side gate between:
1. asset/runtime preflight; and
2. any future server-scale ablation submission.

It does exactly one point on exactly one model, writes the resolved-env and
preflight reports under a small smoke root, then returns a GREEN/RED verdict:

- GREEN: the smoke run produced one aggregate row with status=ok and n_ok == n_total_models
- RED: anything else (missing assets, missing runtime deps, evaluator failure, parse failure)

This keeps the server approval gate honest: a real server submission should only
happen after the same code path has passed locally on one concrete model/point.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
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


ev = _load("run_evaluator_sweep")
pf = _load("evaluator_preflight")


_REPO_ROOT = _DIR.parents[1]  # test/launch/.. == repo root


def _git(*args: str) -> str:
    # Must run from the repo root (test/launch/.parents[1]); the previous
    # _DIR.parents[2] pointed one level above the repo so `git rev-parse HEAD`
    # returned empty, leaving `repo_commit` blank in the smoke artifact even on a
    # green run inside the repo.
    try:
        return subprocess.check_output(["git", *args], cwd=_REPO_ROOT,
                                       stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return ""


def _build_point(*, dataset: str, method: str, sigma_param: str, sigma_value: float,
                 radius_sigma_mult: float | None, delay_seconds: float,
                 window_mode: str, frame_offset: int | None) -> dict:
    point = ev.make_sigma_grid(
        dataset, method,
        sigma_param=sigma_param,
        sigma_values=[float(sigma_value)],
        radius_sigma_mult=radius_sigma_mult,
        delay_seconds=float(delay_seconds),
        window_mode=window_mode,
    )[0]
    if frame_offset is not None:
        point["frame_offset"] = int(frame_offset)
    return point


def _smoke_root(results_root: Path, stage: str, dataset: str, method: str) -> Path:
    return Path(results_root) / "ablation" / stage / dataset / method / "_smoke_gate"


def _write_smoke_metadata(smoke_root: Path, *, asset_report: dict, runtime_report: dict,
                          point: dict, model: str, run_dir: Path | None, verdict: dict,
                          command_argv: list[str], repo_commit: str) -> None:
    smoke_root.mkdir(parents=True, exist_ok=True)
    (smoke_root / "asset_preflight.md").write_text(pf.format_report(asset_report))
    (smoke_root / "runtime_preflight.md").write_text(pf.format_runtime_dependency_report(runtime_report))
    (smoke_root / "resolved_env.sh").write_text(pf.shell_exports(asset_report))
    payload = {
        "repo_commit": repo_commit,
        "command_argv": command_argv,
        "model": model,
        "point": point,
        "run_dir": str(run_dir) if run_dir else "",
        "metrics_summary_csv": str(run_dir / "metrics_summary.csv") if run_dir else "",
        "verdict": verdict,
    }
    (smoke_root / "smoke_gate.json").write_text(json.dumps(payload, indent=2, default=str))


def run_local_smoke_gate(*, dataset: str, method: str, model: str,
                         sigma_param: str, sigma_value: float,
                         radius_sigma_mult: float | None = None,
                         delay_seconds: float = 0.0,
                         window_mode: str = "one_turn_from_start",
                         frame_offset: int | None = None,
                         results_root: Path = Path("results"),
                         stage: str = "local_smoke_gate",
                         fixation_root: str | None = None,
                         mock: bool = False,
                         command_argv: list[str] | None = None) -> tuple[dict, Path]:
    point = _build_point(
        dataset=dataset, method=method, sigma_param=sigma_param, sigma_value=sigma_value,
        radius_sigma_mult=radius_sigma_mult, delay_seconds=delay_seconds,
        window_mode=window_mode, frame_offset=frame_offset,
    )

    smoke_root = _smoke_root(results_root, stage, dataset, method)
    asset_report = pf.preflight(dataset, method, fixation_root=fixation_root)
    runtime_report = {"method": method, "python": "", "ok": True, "items": [],
                      "missing": [], "reason": "mock_skip" if mock else "not_run_yet"}
    repo_commit = _git("rev-parse", "HEAD")
    command_argv = command_argv or []

    if not asset_report["ok"]:
        verdict = {"ok": False, "reason": "asset_preflight_failed"}
        _write_smoke_metadata(smoke_root, asset_report=asset_report, runtime_report=runtime_report,
                              point=point, model=model, run_dir=None, verdict=verdict,
                              command_argv=command_argv, repo_commit=repo_commit)
        return verdict, smoke_root

    if not mock:
        runtime_report = pf.runtime_dependency_report(method)
        if not runtime_report["ok"]:
            verdict = {"ok": False, "reason": "runtime_dependency_failed"}
            _write_smoke_metadata(smoke_root, asset_report=asset_report, runtime_report=runtime_report,
                                  point=point, model=model, run_dir=None, verdict=verdict,
                                  command_argv=command_argv, repo_commit=repo_commit)
            return verdict, smoke_root

    invoke = ev.make_mock_invoke() if mock else (
        lambda p, m: ev.subprocess_evaluator_invoke(p, m, work_dir=results_root / "ablation" / "_work" / stage,
                                                    fixation_root=fixation_root, preflight=False)
    )
    run_dir = ev.run_evaluator_sweep(
        [point], [model], results_root, invoke=invoke, stage=stage,
    )[0]
    agg_row = json.loads((run_dir / "aggregate_row.json").read_text())
    ok = agg_row.get("status") == "ok" and int(agg_row.get("n_ok", 0)) == int(agg_row.get("n_total_models", 0))
    verdict = {
        "ok": ok,
        "reason": "green" if ok else "smoke_run_failed",
        "artifact_run_id": agg_row.get("artifact_run_id", ""),
        "status": agg_row.get("status", ""),
        "n_ok": agg_row.get("n_ok", 0),
        "n_failed": agg_row.get("n_failed", 0),
    }
    _write_smoke_metadata(smoke_root, asset_report=asset_report, runtime_report=runtime_report,
                          point=point, model=model, run_dir=run_dir, verdict=verdict,
                          command_argv=command_argv, repo_commit=repo_commit)
    return verdict, run_dir


def main() -> int:
    ap = argparse.ArgumentParser(description="Local Stage-2 smoke gate: preflight + one-point run + verdict.")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--method", required=True, choices=["cone", "screen_space"])
    ap.add_argument("--model", required=True)
    ap.add_argument("--sigma-param", default="sigma_deg", choices=["sigma_deg", "sigma_px", "sigma_screen"])
    ap.add_argument("--sigma-value", required=True)
    ap.add_argument("--radius-sigma-mult", default=None)
    ap.add_argument("--delay-seconds", default=0.0)
    ap.add_argument("--window-mode", default="one_turn_from_start")
    ap.add_argument("--frame-offset", default=None)
    ap.add_argument("--results-root", type=Path, default=Path("results"))
    ap.add_argument("--stage", default="local_smoke_gate")
    ap.add_argument("--fixation-root", default=None)
    ap.add_argument("--mock", action="store_true")
    args = ap.parse_args()

    verdict, path = run_local_smoke_gate(
        dataset=args.dataset, method=args.method, model=args.model,
        sigma_param=args.sigma_param, sigma_value=float(args.sigma_value),
        radius_sigma_mult=(float(args.radius_sigma_mult) if args.radius_sigma_mult else None),
        delay_seconds=float(args.delay_seconds), window_mode=args.window_mode,
        frame_offset=(int(args.frame_offset) if args.frame_offset is not None else None),
        results_root=args.results_root, stage=args.stage, fixation_root=args.fixation_root,
        mock=args.mock, command_argv=sys.argv[:],
    )
    print(f"[smoke-gate] {'GREEN' if verdict['ok'] else 'RED'}: {verdict['reason']}")
    print(f"[smoke-gate] artifacts: {path}")
    return 0 if verdict["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
