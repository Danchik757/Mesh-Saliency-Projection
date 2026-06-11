#!/usr/bin/env python3
"""
Dry-run path resolver for top-20 models by cone CC.

Reads compact benchmark CSVs, selects top 7/7/6 rows from
  MM non_texture / MM rgb_texture / SAL3D
and resolves all local paths (GT, mesh, placement JSON) plus expected
server-side cone map paths (which are NOT available locally).

Outputs a human-readable table; does NOT render anything.

Usage:
    python dry_run_top20_by_cc.py [--n-per-track N]
"""
import argparse
import csv
import glob
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Local path roots — edit if your drives are mounted differently
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]

MM_DATASET_ROOT = Path("/mnt/f/ClaudeCode/MeshMamba-main/dataset")
SAL3D_PKG_ROOT  = Path("/mnt/f/ClaudeCode/sal3d_benchmark_pkg")

MM_SALIENCY_DIR = MM_DATASET_ROOT / "SaliencyMap"
MM_MESH_DIR     = MM_DATASET_ROOT / "MeshFile"
SAL3D_GT_DIR    = SAL3D_PKG_ROOT  / "sal3d_fixed_face_gt"
SAL3D_MESH_DIR  = SAL3D_PKG_ROOT  / "Meshes"

PLACEMENT_ROOT = REPO_ROOT / "jsons" / "object_placement"

# ---------------------------------------------------------------------------
# Cone map paths — local after transfer from rc3_full_metrics batch
# Server source: 29d_kon@lab.graphicon.ru (MeshMamba_reference_batch_20260601 /
#   SAL3D_reference_batch_20260601 / baseline_cone / recenter_rotx90p0_...)
# ---------------------------------------------------------------------------
LOCAL_CONE_ROOT  = Path("/mnt/f/ClaudeCode/rc3_cone_maps")

MM_CONE_SUFFIX  = "_cone_faces.txt"          # rc3_full_metrics batch naming
SAL_CONE_SUFFIX = "_cone_vertices.txt"       # rc3_full_metrics batch naming

# ---------------------------------------------------------------------------
# Benchmark CSV paths
# ---------------------------------------------------------------------------
MM_COMPACT_CSV  = REPO_ROOT / "results/benchmark_runs/meshmamba/2026-06-02_meshmamba_reference/meshmamba_model_metrics_compact.csv"
SAL_COMPACT_CSV = REPO_ROOT / "results/benchmark_runs/sal3d/2026-06-01_sal3d_reference/sal3d_model_metrics_compact.csv"
MM_LONG_CSV     = REPO_ROOT / "results/benchmark_runs/meshmamba/2026-06-02_meshmamba_reference/meshmamba_reference_long.csv"
SAL_LONG_CSV    = REPO_ROOT / "results/benchmark_runs/sal3d/2026-06-01_sal3d_reference/sal3d_detailed_by_model_method.csv"


# ---------------------------------------------------------------------------
# Path resolvers
# ---------------------------------------------------------------------------

def _casefold_glob(directory: Path, pattern: str):
    """Glob case-insensitively; return first match or None."""
    for p in directory.iterdir() if directory.is_dir() else []:
        if p.name.lower() == pattern.lower():
            return p
    # fallback: glob
    matches = list(directory.glob(pattern)) if directory.is_dir() else []
    return matches[0] if matches else None


def resolve_mm_gt(texture_type: str, gt_file: str) -> Path:
    gt_dir = MM_SALIENCY_DIR / texture_type
    return gt_dir / gt_file


def resolve_mm_mesh(texture_type: str, model: str) -> Path:
    mesh_dir = MM_MESH_DIR / texture_type / model
    if not mesh_dir.is_dir():
        return mesh_dir / f"{model}.obj"  # will show as missing
    # find *.obj inside
    objs = list(mesh_dir.glob("*.obj"))
    if objs:
        return objs[0]
    return mesh_dir / f"{model}.obj"


def resolve_mm_placement(texture_type: str, model: str) -> Path:
    sub = "mamba_non_jsons" if texture_type == "non_texture" else "mamba_rgb_jsons"
    return PLACEMENT_ROOT / sub / f"MeshMamba_{texture_type}_{model}.json"


def resolve_mm_cone_local(texture_type: str, model: str) -> Path:
    return LOCAL_CONE_ROOT / "meshmamba" / texture_type / model / f"{model}{MM_CONE_SUFFIX}"


def resolve_sal_gt(model: str) -> Path:
    return SAL3D_GT_DIR / f"{model}_faces.txt"


def resolve_sal_mesh(model: str) -> Path:
    return SAL3D_MESH_DIR / f"{model}.obj"


def resolve_sal_placement(model: str) -> Path:
    return PLACEMENT_ROOT / "sal3d_jsons" / f"Sal3D_{model}.json"


def resolve_sal_cone_local(model: str) -> Path:
    return LOCAL_CONE_ROOT / "sal3d" / model / f"{model}{SAL_CONE_SUFFIX}"


# ---------------------------------------------------------------------------
# CSV reading
# ---------------------------------------------------------------------------

def load_gt_files(mm_long_csv: Path, sal_long_csv: Path):
    """Return dict (track, model) -> gt_file from long CSVs (cone rows only)."""
    gt_map = {}
    with open(mm_long_csv) as f:
        for r in csv.DictReader(f):
            if r["method"] == "cone" and r["status"] == "ok":
                key = (r["texture_type"], r["model"])
                gt_map[key] = r["gt_file"]
    with open(sal_long_csv) as f:
        for r in csv.DictReader(f):
            if r["method"] == "cone" and r["status"] == "ok":
                gt_map[("sal3d", r["model"])] = r.get("gt_file", "")
    return gt_map


def load_compact(mm_csv: Path, sal_csv: Path):
    """Return sorted lists per track: (texture_or_dataset, model, cc)."""
    tracks = {"non_texture": [], "rgb_texture": [], "sal3d": []}
    with open(mm_csv) as f:
        for r in csv.DictReader(f):
            if r["cone_status"].lower() == "ok":
                tracks[r["texture_type"]].append((r["model"], float(r["cone_CC"])))
    with open(sal_csv) as f:
        for r in csv.DictReader(f):
            if r["cone_status"].lower() == "ok":
                tracks["sal3d"].append((r["model"], float(r["cone_CC"])))
    for t in tracks:
        tracks[t].sort(key=lambda x: x[1], reverse=True)
    return tracks


# ---------------------------------------------------------------------------
# Row builder
# ---------------------------------------------------------------------------

def build_row(track: str, model: str, cc: float, gt_file: str):
    is_sal = track == "sal3d"

    if is_sal:
        gt_path   = resolve_sal_gt(model)
        mesh_path = resolve_sal_mesh(model)
        json_path = resolve_sal_placement(model)
        cone_path = resolve_sal_cone_local(model)
        dataset   = "SAL3D"
        texture   = "—"
    else:
        gt_path   = resolve_mm_gt(track, gt_file)
        mesh_path = resolve_mm_mesh(track, model)
        json_path = resolve_mm_placement(track, model)
        cone_path = resolve_mm_cone_local(track, model)
        dataset   = "MeshMamba"
        texture   = track

    return {
        "dataset": dataset,
        "texture_type": texture,
        "model": model,
        "CC": cc,
        "gt_path": gt_path,
        "gt_ok": gt_path.exists(),
        "mesh_path": mesh_path,
        "mesh_ok": mesh_path.exists(),
        "json_path": json_path,
        "json_ok": json_path.exists(),
        "cone_path": cone_path,
        "cone_ok": cone_path.exists(),
    }


# ---------------------------------------------------------------------------
# Printing
# ---------------------------------------------------------------------------

OK   = "OK   "
MISS = "MISS "

def _status(ok: bool) -> str:
    return OK if ok else MISS


def print_table(rows: list[dict]):
    print()
    print(f"{'#':>2}  {'Dataset':12} {'Track':12} {'Model':45} {'CC':6}  GT    Mesh  JSON  Cone")
    print("─" * 110)
    for i, r in enumerate(rows, 1):
        print(f"{i:>2}  {r['dataset']:12} {r['texture_type']:12} {r['model']:45} {r['CC']:.4f}  "
              f"{_status(r['gt_ok'])} {_status(r['mesh_ok'])} {_status(r['json_ok'])} {_status(r['cone_ok'])}")

    n_gt_ok   = sum(r["gt_ok"]   for r in rows)
    n_mesh_ok = sum(r["mesh_ok"] for r in rows)
    n_json_ok = sum(r["json_ok"] for r in rows)
    n_cone_ok = sum(r["cone_ok"] for r in rows)
    print("─" * 110)
    print(f"    GT={n_gt_ok}/{len(rows)}  Mesh={n_mesh_ok}/{len(rows)}  "
          f"JSON={n_json_ok}/{len(rows)}  Cone={n_cone_ok}/{len(rows)}"
          + ("  ← transfer cone maps before rendering" if n_cone_ok < len(rows) else ""))

    print()
    checks = [("GT", "gt_path", "gt_ok"), ("Mesh", "mesh_path", "mesh_ok"),
              ("JSON", "json_path", "json_ok"), ("Cone", "cone_path", "cone_ok")]
    missing = [(lbl, r) for lbl, pk, ok in checks for r in rows if not r[ok]]
    if missing:
        print("MISSING FILES:")
        for lbl, pk, ok in checks:
            for r in rows:
                if not r[ok]:
                    print(f"  [{lbl}] {r[pk]}")
    else:
        print("All files (GT / Mesh / JSON / Cone) present.")


def print_render_commands(rows: list[dict], output_dir: str):
    print()
    print("=" * 80)
    print("RENDER COMMANDS (GT + cone, full-turn, white bg)")
    print("=" * 80)
    for r in rows:
        ds = r["dataset"].lower()
        tt = f' --texture-type {r["texture_type"]}' if r["dataset"] == "MeshMamba" else ""
        print(f"\n# {r['dataset']} {r['texture_type']} {r['model']}  (CC={r['CC']:.4f})")
        print(f"python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \\")
        print(f"  --dataset {ds}{tt} --model {r['model']} \\")
        print(f"  --map-type gt --map-path {r['gt_path']} \\")
        print(f"  --mesh {r['mesh_path']} --placement {r['json_path']} \\")
        print(f"  --output-dir {output_dir} --background-color white --full-turn \\")
        print(f"  --map-provenance-note rc3_vis_gt")
        print()
        print(f"python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \\")
        print(f"  --dataset {ds}{tt} --model {r['model']} \\")
        print(f"  --map-type cone --map-path {r['cone_path']} \\")
        print(f"  --mesh {r['mesh_path']} --placement {r['json_path']} \\")
        print(f"  --output-dir {output_dir} --background-color white --full-turn \\")
        print(f"  --map-provenance-note rc3_full_metrics_20260611_004003")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n-mm-nt",  type=int, default=7,  help="Top N from MM non_texture (default 7)")
    ap.add_argument("--n-mm-rgb", type=int, default=7,  help="Top N from MM rgb_texture (default 7)")
    ap.add_argument("--n-sal",    type=int, default=6,  help="Top N from SAL3D (default 6)")
    ap.add_argument("--output-dir", default="/tmp/heatmap_top20", help="Output dir shown in render commands")
    ap.add_argument("--show-commands", action="store_true", help="Print render commands at end")
    args = ap.parse_args()

    gt_files = load_gt_files(MM_LONG_CSV, SAL_LONG_CSV)
    tracks   = load_compact(MM_COMPACT_CSV, SAL_COMPACT_CSV)

    rows = []
    for model, cc in tracks["non_texture"][:args.n_mm_nt]:
        gt_file = gt_files.get(("non_texture", model), "")
        rows.append(build_row("non_texture", model, cc, gt_file))
    for model, cc in tracks["rgb_texture"][:args.n_mm_rgb]:
        gt_file = gt_files.get(("rgb_texture", model), "")
        rows.append(build_row("rgb_texture", model, cc, gt_file))
    for model, cc in tracks["sal3d"][:args.n_sal]:
        rows.append(build_row("sal3d", model, cc, ""))

    print(f"\nDRY-RUN: top-{args.n_mm_nt}/{args.n_mm_rgb}/{args.n_sal} "
          f"(MM-NT / MM-RGB / SAL3D) by cone CC — {len(rows)} models total")
    print("NO RENDERING.")

    print_table(rows)

    if args.show_commands:
        print_render_commands(rows, args.output_dir)

    # exit non-zero if any required file is missing
    all_ok = all(r["gt_ok"] and r["mesh_ok"] and r["json_ok"] and r["cone_ok"] for r in rows)
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
