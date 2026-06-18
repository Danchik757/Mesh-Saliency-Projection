"""Asset-discovery / preflight for the evaluator-backed runner.

NON-DESTRUCTIVE. For a (dataset, method) target it reports which dataset roots /
env vars and asset *kinds* the real evaluator invocation needs, and whether each
is present locally — so a real run fails fast with an actionable message instead
of a cryptic downstream subprocess failure.

The env→flag mapping mirrors `run_ablation_window_delay.build_command` (the
authoritative invocation path). It imports/modifies no baseline evaluator.
"""
from __future__ import annotations

import argparse
import subprocess
import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKSPACE_ROOT = _REPO_ROOT.parents[2]

VALID_METHODS = ("cone", "screen_space")
RUNTIME_DEPENDENCIES = {
    "cone": [
        {
            "module": "rtree",
            "reason": "trimesh ray intersections used by cone/raycast evaluators",
        },
    ],
    "screen_space": [],
}


class PreflightError(RuntimeError):
    """Raised when a real evaluator run is requested without the required assets."""


def _req(name, envs, flag, kind, *, required=True, default=None):
    return {"name": name, "envs": envs, "flag": flag, "kind": kind,
            "required": required, "default": default}


# Fixation JSON is tracked in git, so it has a known default local path.
FIXATION_REQ = _req(
    "fixation_root", ["FIXATION_ROOT", "REPROJECT_PROCESSED_FIXATIONS_ROOT"],
    "--fixation-root", "fixation",
    default="participant_data/processed_fixations_offset0_full_cleaned")

# Per-dataset roots — mirrors run_ablation_window_delay.build_command.
ASSET_SPEC: dict[str, list[dict]] = {
    "3dva": [
        _req(
            "dataset_root",
            ["VISUAL_ATTENTION_3D_SHAPES_ROOT", "THREE_DVA_DATASET_ROOT"],
            "--dataset-root",
            "mesh",
        ),
        _req("json_root", ["THREE_DVA_JSON_ROOT"], "--json-root", "placement_json"),
        _req("combined_gt_dir", ["THREE_DVA_COMBINED_GT_DIR"], "--combined-gt-dir", "ground_truth"),
    ],
    "meshmamba_non_texture": [
        _req("json_root", ["MESHMAMBA_JSON_ROOT"], "--json-root", "placement_json"),
        _req("dataset_root", ["MESHMAMBA_NON_TEXTURE_ROOT"], "--dataset-root", "mesh"),
    ],
    "meshmamba_rgb_texture": [
        _req("json_root", ["MESHMAMBA_RGB_TEXTURE_JSON_ROOT"], "--json-root", "placement_json"),
        _req("dataset_root", ["MESHMAMBA_RGB_TEXTURE_ROOT"], "--dataset-root", "mesh"),
    ],
    "sal3d": [
        _req("json_root", ["SAL3D_JSON_ROOT"], "--json-root", "placement_json"),
        _req("dataset_root", ["SAL3D_DATASET_ROOT"], "--dataset-root", "mesh"),
        _req("fixed_gt_dir", ["SAL3D_FIXED_GT_DIR"], "--fixed-gt-dir", "ground_truth"),
        _req("smooth_gaze_dir", ["SAL3D_SMOOTH_GAZE_DIR"], "--smooth-gaze-dir", "smooth_gaze",
             required=False),
        _req("sal3d_manifest", ["SAL3D_MANIFEST"], "--sal3d-manifest", "manifest"),
    ],
}

def _validate_path(dataset: str, req: dict, path: Path | None) -> bool:
    if path is None:
        return False
    if req["name"] == "dataset_root" and dataset.startswith("meshmamba"):
        texture_type = "non_texture" if dataset.endswith("non_texture") else "rgb_texture"
        return (
            (path / "MeshFile" / texture_type).is_dir()
            and (path / "SaliencyMap" / texture_type).is_dir()
        )
    if req["name"] == "json_root" and dataset == "meshmamba_non_texture":
        return path.is_dir() and any(path.glob("MeshMamba_non_texture_*.json"))
    if req["name"] == "json_root" and dataset == "meshmamba_rgb_texture":
        return path.is_dir() and any(path.glob("MeshMamba_rgb_texture_*.json"))
    return path.exists()


def _auto_candidates(dataset: str, req: dict) -> list[Path]:
    meshmamba_dataset_roots = [
        _WORKSPACE_ROOT / "GAZE_DATA/datasets/MeshMamba/MeshMambaSaliency",
        _WORKSPACE_ROOT / "Models/Meshmamba/MeshMamba/dataset",
        _WORKSPACE_ROOT / "CODE_REALIZATION/MeshMamba/dataset",
    ]
    if req["name"] == "json_root" and dataset == "meshmamba_non_texture":
        return [
            _REPO_ROOT / "jsons/object_placement/mamba_non_jsons",
            _WORKSPACE_ROOT / "GAZE_DATA/jsons_for_models/Mamba_non_textured",
        ]
    if req["name"] == "json_root" and dataset == "meshmamba_rgb_texture":
        return [
            _REPO_ROOT / "jsons/object_placement/mamba_rgb_jsons",
            _WORKSPACE_ROOT / "GAZE_DATA/jsons_for_models/Mamba_rgb_textured",
        ]
    if req["name"] == "dataset_root" and dataset in {"meshmamba_non_texture", "meshmamba_rgb_texture"}:
        return meshmamba_dataset_roots
    return []


def _resolve(dataset, req, env, fixation_root=None):
    if req["name"] == "fixation_root" and fixation_root:
        return Path(fixation_root), None, "argument", []
    for env_name in req["envs"]:
        if env.get(env_name):
            return Path(env[env_name]), env_name, "env", []
    if req["default"]:
        return (_REPO_ROOT / req["default"]), None, "default", []
    checked = _auto_candidates(dataset, req)
    for candidate in checked:
        if _validate_path(dataset, req, candidate):
            return candidate, None, "auto", checked
    return None, None, "unset", checked


def preflight(dataset: str, method: str, *, fixation_root: str | None = None,
              env: dict | None = None) -> dict:
    if dataset not in ASSET_SPEC:
        raise PreflightError(f"unknown dataset {dataset!r}; known: {sorted(ASSET_SPEC)}")
    if method not in VALID_METHODS:
        raise PreflightError(f"unknown method {method!r}; known: {VALID_METHODS}")
    env = os.environ if env is None else env

    items = []
    for req in [FIXATION_REQ, *ASSET_SPEC[dataset]]:
        path, src_env, source, checked = _resolve(dataset, req, env, fixation_root)
        present = _validate_path(dataset, req, path)
        items.append({"name": req["name"], "flag": req["flag"], "kind": req["kind"],
                      "envs": req["envs"], "required": req["required"],
                      "resolved_path": str(path) if path else None,
                      "source": source, "source_env": src_env, "present": present,
                      "checked_paths": [str(p) for p in checked]})
    missing = [i for i in items if i["required"] and not i["present"]]
    return {"dataset": dataset, "method": method, "ok": not missing, "items": items, "missing": missing}


def shell_exports(report: dict) -> str:
    """Ready-to-paste env exports for the resolved roots of a READY report."""
    env_map = resolved_env(report)
    lines = [f'export {name}="{value}"' for name, value in env_map.items()]
    return "\n".join(lines) + ("\n" if lines else "")


def resolved_env(report: dict) -> dict[str, str]:
    """Canonical env mapping for the resolved paths of a READY/NOT READY report."""
    lines = []
    for item in report["items"]:
        if not item["present"] or not item["resolved_path"]:
            continue
        env_name = item["source_env"] or item["envs"][0]
        lines.append((env_name, item["resolved_path"]))
    return dict(lines)


def format_report(report: dict) -> str:
    lines = [f"# Preflight: {report['dataset']} / {report['method']} → "
             f"{'READY' if report['ok'] else 'NOT READY'}", "",
             "| asset | kind | required | present | source | resolved path | env vars |",
             "|---|---|---|---|---|---|---|"]
    for i in report["items"]:
        lines.append(
            f"| {i['name']} | {i['kind']} | {'yes' if i['required'] else 'no'} | "
            f"{'present' if i['present'] else 'MISSING'} | {i['source']} | "
            f"`{i['resolved_path']}` | {', '.join(i['envs'])} |")
    if report["missing"]:
        lines += ["", "## Missing required assets — set one of these env vars to a valid path", ""]
        for i in report["missing"]:
            lines.append(f"- **{i['name']}** ({i['kind']}, evaluator flag `{i['flag']}`): "
                         f"set `{'` or `'.join(i['envs'])}`")
            if i["checked_paths"]:
                lines.append(f"  searched local candidates: `{ '`, `'.join(i['checked_paths']) }`")
    elif report["ok"]:
        exports = shell_exports(report).rstrip()
        if exports:
            lines += ["", "## Ready-to-paste env exports", "", "```bash", exports, "```"]
    return "\n".join(lines) + "\n"


def require(dataset: str, method: str, *, fixation_root: str | None = None,
            env: dict | None = None) -> dict:
    """Return the preflight report, or raise PreflightError with an actionable
    message listing the missing roots/env vars."""
    report = preflight(dataset, method, fixation_root=fixation_root, env=env)
    if not report["ok"]:
        names = [i["name"] for i in report["missing"]]
        raise PreflightError(
            f"preflight failed for {dataset}/{method}: missing required assets {names}.\n"
            + format_report(report))
    return report


def runtime_dependency_report(method: str, *, python: str | None = None) -> dict:
    if method not in VALID_METHODS:
        raise PreflightError(f"unknown method {method!r}; known: {VALID_METHODS}")
    python = python or os.environ.get("REPROJECT_PYTHON", sys.executable)
    items = []
    for dep in RUNTIME_DEPENDENCIES[method]:
        proc = subprocess.run(
            [python, "-c", f"import {dep['module']}"],
            capture_output=True, text=True, timeout=10,
        )
        items.append({
            "module": dep["module"],
            "reason": dep["reason"],
            "python": python,
            "present": proc.returncode == 0,
            "error": (proc.stderr or proc.stdout or "").strip()[-300:],
        })
    missing = [i for i in items if not i["present"]]
    return {"method": method, "python": python, "ok": not missing, "items": items, "missing": missing}


def format_runtime_dependency_report(report: dict) -> str:
    lines = [f"# Runtime dependencies: {report['method']} → "
             f"{'READY' if report['ok'] else 'NOT READY'}", ""]
    if report.get("reason"):
        lines.append(f"- reason: `{report['reason']}`")
    for item in report["items"]:
        lines.append(
            f"- `{item['module']}`: {'present' if item['present'] else 'MISSING'} "
            f"({item['reason']})"
        )
        if item["error"]:
            lines.append(f"  probe: `{item['error']}`")
    return "\n".join(lines) + "\n"


def require_runtime_dependencies(method: str, *, python: str | None = None) -> dict:
    report = runtime_dependency_report(method, python=python)
    if not report["ok"]:
        mods = [i["module"] for i in report["missing"]]
        raise PreflightError(
            f"runtime dependency preflight failed for {method}: missing {mods}.\n"
            + format_runtime_dependency_report(report)
        )
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluator asset preflight / discovery.")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--method", required=True, choices=list(VALID_METHODS))
    ap.add_argument("--fixation-root", default=None)
    ap.add_argument("--out", type=Path, default=None, help="write the markdown report here")
    ap.add_argument("--json", action="store_true", help="also print the machine-readable report")
    ap.add_argument("--shell-exports", action="store_true",
                    help="print only the ready-to-paste export block")
    args = ap.parse_args()

    report = preflight(args.dataset, args.method, fixation_root=args.fixation_root)
    text = shell_exports(report) if args.shell_exports else format_report(report)
    print(text)
    if args.json:
        print(json.dumps(report, indent=2))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
        print(f"[preflight] report -> {args.out}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
