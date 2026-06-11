#!/usr/bin/env python3
"""
Batch renderer: GT + cone full-turn videos for a list of models.

Reads model list from a TSV (columns: dataset, track, model, cone_CC) or
from inline MODELS list, renders both GT and cone via render_heatmap_video.py,
then flattens each model's output into a single folder:

  {OUT_ROOT}/{Dataset}/{track}/{model}/
    {model}_gt_fullturn.mp4
    {model}_cone_fullturn.mp4
    gt_manifest.json
    cone_manifest.json
    preview_gt_NNN.png  (5 per model)
    preview_cone_NNN.png

Usage:
    python render_batch_gt_cone.py [--models-tsv path/to/models.tsv]
                                   [--output-dir /path/to/out]
                                   [--cone-maps-root /path/to/rc3_cone_maps]
                                   [--dry-run]

SAL3D path note:
  The renderer outputs SAL3D to {staging}/SAL3D/{model}/{map_type}/ (no track subdir).
  MeshMamba outputs to {staging}/MeshMamba/{track}/{model}/{map_type}/.
  The flatten step handles both conventions.
"""
import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO      = Path(__file__).resolve().parents[2]
RENDERER  = Path(__file__).parent / "render_heatmap_video.py"
MM_LONG   = REPO / "results/benchmark_runs/meshmamba/2026-06-02_meshmamba_reference/meshmamba_reference_long.csv"

MM_MESH   = Path("/mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile")
MM_GT_DIR = Path("/mnt/f/ClaudeCode/MeshMamba-main/dataset/SaliencyMap")
SAL_GT    = Path("/mnt/f/ClaudeCode/sal3d_benchmark_pkg/sal3d_fixed_face_gt")
SAL_MESH  = Path("/mnt/f/ClaudeCode/sal3d_benchmark_pkg/Meshes")
PLACE     = REPO / "jsons/object_placement"

CONE_NOTE = (
    "rc3_full_metrics_20260611_004003 baseline_cone renderer batch; "
    "final optimized renders should use optimized full-run maps when available"
)


def load_gt_lookup() -> dict:
    gt = {}
    with open(MM_LONG) as f:
        for r in csv.DictReader(f):
            if r["method"] == "cone" and r["status"] == "ok":
                gt[(r["texture_type"], r["model"])] = r["gt_file"]
    return gt


def resolve_paths(ds: str, track: str, model: str, cone_root: Path, gt_lookup: dict) -> dict:
    if ds == "meshmamba":
        gt_file  = gt_lookup[(track, model)]
        gt_path  = MM_GT_DIR / track / gt_file
        mesh_dir = MM_MESH / track / model
        objs     = list(mesh_dir.glob("*.obj"))
        mesh     = objs[0] if objs else mesh_dir / f"{model}.obj"
        sub      = "mamba_non_jsons" if track == "non_texture" else "mamba_rgb_jsons"
        placement = PLACE / sub / f"MeshMamba_{track}_{model}.json"
        cone     = cone_root / "meshmamba" / track / model / f"{model}_cone_faces.txt"
        ds_canon = "MeshMamba"
    else:
        gt_path   = SAL_GT  / f"{model}_faces.txt"
        mesh      = SAL_MESH / f"{model}.obj"
        placement = PLACE / "sal3d_jsons" / f"Sal3D_{model}.json"
        cone      = cone_root / "sal3d" / model / f"{model}_cone_vertices.txt"
        ds_canon  = "SAL3D"
    return dict(gt=gt_path, mesh=mesh, placement=placement, cone=cone, ds_canon=ds_canon)


def flatten(staging_map_dir: Path, model_out: Path, map_type: str, model: str):
    model_out.mkdir(parents=True, exist_ok=True)
    shutil.move(str(staging_map_dir / "heatmap_video.mp4"),
                str(model_out / f"{model}_{map_type}_fullturn.mp4"))
    shutil.move(str(staging_map_dir / "manifest.json"),
                str(model_out / f"{map_type}_manifest.json"))
    for png in sorted(staging_map_dir.glob("preview_frame_*.png")):
        shutil.move(str(png),
                    str(model_out / f"preview_{map_type}_{png.name[len('preview_frame_'):]}"))
    csv_f = staging_map_dir / "manifest.csv"
    if csv_f.exists():
        csv_f.unlink()
    try:
        staging_map_dir.rmdir()
    except OSError:
        pass


def run_render(ds: str, track: str, model: str, map_type: str,
               map_path: Path, paths: dict, staging: Path, model_out: Path) -> tuple[bool, float, str]:
    ds_flags = ["--dataset", ds]
    if ds == "meshmamba":
        ds_flags += ["--texture-type", track]

    map_note = "rc3_vis_gt" if map_type == "gt" else CONE_NOTE
    staging_model = staging / f"{ds}_{track}_{model}"

    cmd = [
        sys.executable, str(RENDERER),
        *ds_flags, "--model", model,
        "--map-type", map_type,
        "--map-path", str(map_path),
        "--mesh", str(paths["mesh"]),
        "--placement", str(paths["placement"]),
        "--output-dir", str(staging_model),
        "--background-color", "white",
        "--full-turn",
        "--map-provenance-note", map_note,
    ]

    t0 = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO))
    elapsed = time.time() - t0

    if result.returncode != 0:
        return False, elapsed, result.stderr[-500:]

    ds_canon  = paths["ds_canon"]
    # SAL3D: no track subdir; MeshMamba: track subdir present
    if ds == "sal3d":
        render_out = staging_model / ds_canon / model / map_type
    else:
        render_out = staging_model / ds_canon / track / model / map_type

    if not render_out.is_dir():
        return False, elapsed, f"expected dir not found: {render_out}"

    flatten(render_out, model_out, map_type, model)
    return True, elapsed, ""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models-tsv",    default=None, help="TSV with columns: dataset,track,model,cone_CC")
    ap.add_argument("--output-dir",    default="/mnt/c/Users/Danya/Downloads/heatmap_3d_batch_gt_cone")
    ap.add_argument("--cone-maps-root", default="/mnt/f/ClaudeCode/rc3_cone_maps")
    ap.add_argument("--staging",       default="/tmp/render_batch_staging")
    ap.add_argument("--dry-run",       action="store_true", help="Check paths only, no rendering")
    args = ap.parse_args()

    cone_root = Path(args.cone_maps_root)
    out_root  = Path(args.output_dir)
    staging   = Path(args.staging)
    gt_lookup = load_gt_lookup()

    # Load model list
    if args.models_tsv:
        with open(args.models_tsv) as f:
            models = [(r["dataset"], r["track"], r["model"])
                      for r in csv.DictReader(f, delimiter="\t")]
    else:
        # Default: 20-model batch from rc3_full_metrics_20260611_004003
        models = [
            ("meshmamba", "non_texture", "Watermelon_V1_L3"),
            ("meshmamba", "non_texture", "barbiegirl_V1_L3"),
            ("meshmamba", "non_texture", "Soda_Can_v3_L3"),
            ("meshmamba", "non_texture", "Apple_Red_v1_L3"),
            ("meshmamba", "non_texture", "Pear_L3"),
            ("meshmamba", "non_texture", "egypt_sphinx_V2_L3"),
            ("meshmamba", "non_texture", "Peach_L3"),
            ("meshmamba", "rgb_texture", "Watermelon_V1_L3"),
            ("meshmamba", "rgb_texture", "Military_Action_Figure_SG_v2_L3"),
            ("meshmamba", "rgb_texture", "Apple_Red_v1_L3"),
            ("meshmamba", "rgb_texture", "Jukebox_bubbler_style_V2_L1"),
            ("meshmamba", "rgb_texture", "Cat_v1_L3"),
            ("meshmamba", "rgb_texture", "BastetCat_v2_L2"),
            ("meshmamba", "rgb_texture", "Blackberry_v02_L3"),
            ("sal3d", "sal3d", "james"),
            ("sal3d", "sal3d", "vase"),
            ("sal3d", "sal3d", "MaxPlanck"),
            ("sal3d", "sal3d", "cow"),
            ("sal3d", "sal3d", "gorilla"),
            ("sal3d", "sal3d", "igea"),
        ]

    # Path check
    all_ok = True
    print(f"\n{'DRY-RUN' if args.dry_run else 'PATH CHECK'}: {len(models)} models")
    for ds, track, model in models:
        p = resolve_paths(ds, track, model, cone_root, gt_lookup)
        ok = {k: Path(v).exists() for k, v in [("GT", p["gt"]), ("Mesh", p["mesh"]),
                                                 ("JSON", p["placement"]), ("Cone", p["cone"])]}
        status = "OK" if all(ok.values()) else "MISS:" + ",".join(k for k, v in ok.items() if not v)
        print(f"  {ds:10} {track:12} {model:40}  {status}")
        if not all(ok.values()):
            all_ok = False

    if not all_ok:
        print("\nAbort: missing files above.")
        sys.exit(1)
    if args.dry_run:
        print("\nAll paths OK. Use without --dry-run to render.")
        sys.exit(0)

    # Render
    staging.mkdir(parents=True, exist_ok=True)
    out_root.mkdir(parents=True, exist_ok=True)
    results = []
    total_frames = 0
    batch_t0 = time.time()

    for i, (ds, track, model) in enumerate(models, 1):
        paths   = resolve_paths(ds, track, model, cone_root, gt_lookup)
        ds_canon = paths["ds_canon"]
        model_out = (out_root / ds_canon / model) if ds == "sal3d" else (out_root / ds_canon / track / model)
        turn = 660 if ds == "sal3d" else 450

        print(f"\n[{i:02d}/{len(models)}] {ds_canon} {track} {model}  ({turn}f×2)")
        for map_type, map_path in [("gt", paths["gt"]), ("cone", paths["cone"])]:
            print(f"  → {map_type}...", end=" ", flush=True)
            ok, elapsed, err = run_render(ds, track, model, map_type, map_path, paths, staging, model_out)
            if ok:
                print(f"{elapsed:.1f}s  ({elapsed/turn:.3f}s/f)")
                total_frames += turn
            else:
                print(f"FAILED  {err}")
            results.append(dict(ds=ds_canon, track=track, model=model,
                                map_type=map_type, ok=ok, elapsed=elapsed))

    total_elapsed = time.time() - batch_t0
    ok_n   = sum(1 for r in results if r["ok"])
    fail_n = len(results) - ok_n
    print(f"\n{'='*60}")
    print(f"DONE  {ok_n}/{len(results)} renders OK  {fail_n} failed")
    print(f"Total: {total_elapsed:.1f}s ({total_elapsed/60:.1f} min)  avg {sum(r['elapsed'] for r in results if r['ok'])/max(total_frames,1):.3f}s/f")
    print(f"Output: {out_root}")
    if fail_n:
        print("FAILED:", [(r["model"], r["map_type"]) for r in results if not r["ok"]])

    try:
        shutil.rmtree(str(staging))
    except Exception:
        pass

    sys.exit(0 if fail_n == 0 else 1)


if __name__ == "__main__":
    main()
