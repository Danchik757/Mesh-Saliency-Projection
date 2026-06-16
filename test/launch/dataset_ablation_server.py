"""Server-run contract + monitor/resume for dataset-level ablation.

This is the server-entry layer for the dataset-method orchestrator. It does NOT
launch anything. It only:

  1. emits a portable, self-contained **server-run manifest** for one
     `(dataset, method, stage)` branch — the exact low-priority command, host
     placement, env/asset roots, repo pin, and the expected per-candidate
     aggregate run_ids, so a human/runner can submit a real multi-model run on an
     approved server; and
  2. reports **status** of a branch (expected vs completed candidates, promoted /
     held), which makes the dataset-level run monitorable and resumable: the real
     launcher already supersedes/skips finished candidates, so re-submitting the
     same manifest resumes cleanly.

Approved servers only (`vg-iai`, `vg-gml01`, `vg-gml02`), always at low priority
(`nice -n 19 ionice -c2 -n7`). No evaluator formula is touched here, and no job is
executed by this module.
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
agg = _load("ablation_aggregation")

SCHEMA_VERSION = "dataset-ablation-server/1"

# Only these hosts may receive a real dataset-level submission, always low-prio.
APPROVED_HOSTS = ("vg-iai", "vg-gml01", "vg-gml02")
FIRST_TARGET_HOST = "vg-iai"

DEFAULT_NICE = 19
DEFAULT_IONICE_CLASS = 2
DEFAULT_IONICE_LEVEL = 7

LAUNCHER_BY_METHOD = {
    "screen_space": "screen_space_dataset_ablation.py",
    "cone": "cone_dataset_ablation.py",
}


class ServerError(ValueError):
    """Raised when a server-run manifest request is malformed or disallowed."""


def _spec_for(method: str) -> "core.MethodSpec":
    if method == "screen_space":
        return _load("screen_space_dataset_ablation").build_spec()
    if method == "cone":
        return _load("cone_dataset_ablation").build_spec()
    raise ServerError(f"unsupported method {method!r}; known: {sorted(LAUNCHER_BY_METHOD)}")


# ── expected work (for monitoring + provenance) ──────────────────────────────


def expected_candidate_run_ids(request: dict, spec: "core.MethodSpec") -> dict[str, str]:
    """Map static candidate_id -> expected aggregate run_id. Refined sigma points
    are data-dependent (centred on the coarse best) and are therefore NOT included
    here; they are discovered at run time. timing / frame_offset stages are fully
    static, so every candidate is covered."""
    signature = core.comparability_signature(core.comparability_context(request))
    branch_family = core._branch_family(spec.method, request["stage"])
    out: dict[str, str] = {}
    for cand in core.plan_candidates(request, spec):
        params = core._make_params(request, spec, cand, branch_family, signature)
        out[cand.candidate_id] = core._candidate_run_id(params, signature)
    return out


def _low_priority_prefix(nice: int, ionice_class: int, ionice_level: int) -> list[str]:
    return ["nice", "-n", str(nice), "ionice", "-c", str(ionice_class), "-n", str(ionice_level)]


def _default_checkout_root() -> Path:
    return _DIR.parents[1]


# ── server-run manifest ──────────────────────────────────────────────────────


def build_server_manifest(request: dict, *, host: str, results_root: str,
                          request_path: str, repo_url: str | None = None,
                          checkout_root: str | None = None,
                          nice: int = DEFAULT_NICE, ionice_class: int = DEFAULT_IONICE_CLASS,
                          ionice_level: int = DEFAULT_IONICE_LEVEL,
                          python: str | None = None) -> dict:
    """Build a portable, self-contained server-run manifest for one branch.

    Safety contract:
      - request must validate (core.validate_request);
      - host must be approved;
      - low priority is mandatory (nice/ionice baked into the command);
      - the manifest pins repo_commit so the runner can verify the checkout;
      - this returns a manifest only — it never executes anything.
    """
    core.validate_request(request)
    if host not in APPROVED_HOSTS:
        raise ServerError(f"host {host!r} not approved; allowed: {list(APPROVED_HOSTS)}")
    if request.get("models") and len(request["models"]) < 1:
        raise ServerError("request.models must be non-empty for a server run")
    method = request["method"]
    spec = _spec_for(method)
    launcher = LAUNCHER_BY_METHOD[method]
    py = python or request.get("python") or "python3"
    checkout = str(Path(checkout_root or request.get("checkout_root") or _default_checkout_root()).resolve())

    signature = core.comparability_signature(core.comparability_context(request))
    branch_family = core._branch_family(method, request["stage"])
    branch_dir = core.branch_dir_for(Path(results_root), request, spec)
    expected = expected_candidate_run_ids(request, spec)

    command = [
        *_low_priority_prefix(nice, ionice_class, ionice_level),
        py, str(Path(checkout) / "test" / "launch" / launcher),
        "--request", request_path,
        "--results-root", results_root,
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "dataset_ablation_server_run",
        "host": host,
        "approved_hosts": list(APPROVED_HOSTS),
        "priority": {"nice": nice, "ionice_class": ionice_class, "ionice_level": ionice_level},
        "repo": {"commit": request["repo_commit"], "url": repo_url or "", "checkout_root": checkout},
        "cwd": checkout,
        "dataset": request["dataset"],
        "method": method,
        "stage": request["stage"],
        "branch_family": branch_family,
        "comparability_signature": signature,
        "subset_name": request["subset_name"],
        "subset_size": len(request["models"]),
        "results_root": results_root,
        "branch_dir": str(branch_dir),
        "request_path": request_path,
        "request": request,
        "command": command,
        "command_str": " ".join(command),
        "expected_candidate_run_ids": expected,
        "n_static_candidates": len(expected),
        "refined_substage_dynamic": bool(
            request["stage"] == "sigma" and request.get("sigma", {}).get("refined")),
        "resume": {
            "policy": "rerun the same command; finished candidates supersede/skip",
            "aggregate_jsonl": str(branch_dir / "aggregate" / "ablation_runs.jsonl"),
            "branch_best": str(branch_dir / "branch_best.json"),
            "held": str(branch_dir / "_held.json"),
        },
        "generated_at_utc": agg.utc_now_iso(),
        "notes": "low-priority real run; emitted not launched; submit on an approved host only",
    }


def write_server_manifest(manifest: dict, out_path: Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2, default=str))
    return out_path


# ── status / monitor / resume ────────────────────────────────────────────────


def _completed_run_ids(branch_dir: Path) -> set[str]:
    p = branch_dir / "aggregate" / "ablation_runs.jsonl"
    if not p.is_file():
        return set()
    out: set[str] = set()
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("status") == "superseded":
            continue
        if row.get("run_id"):
            out.add(row["run_id"])
    return out


def server_run_status(results_root: str, request: dict) -> dict:
    """Monitor a branch: expected static candidates vs completed, plus terminal
    state. Used to decide whether to (re)submit (resume) or that the branch is
    done. Re-submission of the same command is the resume mechanism."""
    core.validate_request(request)
    spec = _spec_for(request["method"])
    branch_dir = core.branch_dir_for(Path(results_root), request, spec)
    expected = expected_candidate_run_ids(request, spec)
    completed = _completed_run_ids(branch_dir)

    expected_ids = set(expected.values())
    done = expected_ids & completed
    pending = expected_ids - completed
    promoted = (branch_dir / "branch_best.json").is_file()
    held = (branch_dir / "_held.json").is_file()

    # extra completed run_ids beyond the static set = discovered refined points
    extra = completed - expected_ids

    if pending:
        state = "pending"
    elif promoted:
        state = "promoted"
    elif held:
        state = "held"
    else:
        state = "complete_unresolved"

    return {
        "dataset": request["dataset"], "method": request["method"], "stage": request["stage"],
        "comparability_signature": core.comparability_signature(core.comparability_context(request)),
        "branch_dir": str(branch_dir),
        "state": state,
        "n_static_candidates": len(expected_ids),
        "n_static_done": len(done),
        "n_static_pending": len(pending),
        "pending_candidate_ids": sorted(
            cid for cid, rid in expected.items() if rid in pending),
        "n_refined_discovered": len(extra),
        "promoted": promoted,
        "held": held,
    }


# ── CLI ──────────────────────────────────────────────────────────────────────


def _cmd_emit(args) -> int:
    request = json.loads(Path(args.request).read_text())
    try:
        manifest = build_server_manifest(
            request, host=args.host, results_root=str(args.results_root),
            request_path=str(args.request_path_on_server or args.request), repo_url=args.repo_url,
            checkout_root=args.checkout_root,
            nice=args.nice, ionice_class=args.ionice_class, ionice_level=args.ionice_level,
            python=args.python)
    except (core.BranchError, ServerError) as exc:
        print(f"[dmlab-server] EMIT FAILED: {exc}", file=sys.stderr)
        return 2
    if args.out:
        write_server_manifest(manifest, Path(args.out))
        print(f"[dmlab-server] wrote {args.out}")
    print(f"[dmlab-server] host={manifest['host']} "
          f"signature={manifest['comparability_signature']} "
          f"static_candidates={manifest['n_static_candidates']}")
    print(f"[dmlab-server] RUN ON SERVER:\n  {manifest['command_str']}")
    return 0


def _cmd_status(args) -> int:
    request = json.loads(Path(args.request).read_text())
    try:
        status = server_run_status(str(args.results_root), request)
    except (core.BranchError, ServerError) as exc:
        print(f"[dmlab-server] STATUS FAILED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(status, indent=2))
    return 0 if status["state"] in ("promoted", "held") else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="dataset-level ablation server contract + monitor.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pe = sub.add_parser("emit", help="emit a server-run manifest (does not launch)")
    pe.add_argument("--request", type=Path, required=True)
    pe.add_argument("--request-path-on-server", default=None,
                    help="server-side absolute path to the same request JSON; defaults to --request")
    pe.add_argument("--host", required=True, choices=APPROVED_HOSTS)
    pe.add_argument("--results-root", type=Path, default=Path("results"))
    pe.add_argument("--out", type=Path, default=None, help="write the manifest JSON here")
    pe.add_argument("--repo-url", default=None)
    pe.add_argument("--checkout-root", default=None,
                    help="server-side repo checkout root; defaults to request.checkout_root or current repo root")
    pe.add_argument("--python", default=None)
    pe.add_argument("--nice", type=int, default=DEFAULT_NICE)
    pe.add_argument("--ionice-class", type=int, default=DEFAULT_IONICE_CLASS)
    pe.add_argument("--ionice-level", type=int, default=DEFAULT_IONICE_LEVEL)
    pe.set_defaults(func=_cmd_emit)

    ps = sub.add_parser("status", help="report branch progress (monitor/resume)")
    ps.add_argument("--request", type=Path, required=True)
    ps.add_argument("--results-root", type=Path, default=Path("results"))
    ps.set_defaults(func=_cmd_status)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
