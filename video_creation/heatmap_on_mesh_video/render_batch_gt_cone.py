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


def _pick_mesh_obj(mesh_dir: Path, model: str) -> Path:
    """Deterministically select the OBJ for model from mesh_dir.

    Returns the single matching OBJ, or a placeholder path when the directory
    is empty (caller's preflight check will report it missing).
    Raises ValueError when multiple OBJs exist and none match model's
    normalised stem — never chooses arbitrarily.
    """
    objs = sorted(mesh_dir.glob("*.obj"))
    if not objs:
        return mesh_dir / f"{model}.obj"
    wanted = model.lower().replace("_", "").replace("-", "")
    matches = [p for p in objs if p.stem.lower().replace("_", "").replace("-", "") == wanted]
    if matches:
        return matches[0]
    if len(objs) == 1:
        return objs[0]
    raise ValueError(
        f"Ambiguous OBJ files for model '{model}' in {mesh_dir}: "
        + ", ".join(p.name for p in objs)
        + ". Rename files or provide --mesh override."
    )


def resolve_paths(ds: str, track: str, model: str, cone_root: Path, gt_lookup: dict, *,
                  mm_dataset_root: Path, sal3d_dataset_root: Path) -> dict:
    if ds == "meshmamba":
        gt_file = gt_lookup.get((track, model))
        if gt_file is None:
            raise RuntimeError(
                f"No GT entry for track={track!r}, model={model!r}. "
                f"Ensure {MM_LONG.name} has a row with method=cone, status=ok."
            )
        gt_path   = mm_dataset_root / "SaliencyMap" / track / gt_file
        mesh_dir  = mm_dataset_root / "MeshFile" / track / model
        mesh      = _pick_mesh_obj(mesh_dir, model)
        sub       = "mamba_non_jsons" if track == "non_texture" else "mamba_rgb_jsons"
        placement = PLACE / sub / f"MeshMamba_{track}_{model}.json"
        cone      = cone_root / "meshmamba" / track / model / f"{model}_cone_faces.txt"
        ds_canon  = "MeshMamba"
    else:
        gt_path   = sal3d_dataset_root / "sal3d_fixed_face_gt" / f"{model}_faces.txt"
        mesh      = sal3d_dataset_root / "Meshes" / f"{model}.obj"
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
    ap.add_argument("--output-dir",    default=str(REPO / "batch_output" / "heatmap_gt_cone"),
                    help="Output directory (default: <repo>/batch_output/heatmap_gt_cone)")
    ap.add_argument("--cone-maps-root", default=os.environ.get("CONE_MAPS_ROOT"),
                    help="Root containing per-model cone map files. Env: CONE_MAPS_ROOT")
    ap.add_argument("--staging",       default="/tmp/render_batch_staging")
    ap.add_argument("--dry-run",       action="store_true", help="Check paths only, no rendering")
    ap.add_argument("--mm-dataset-root",
                    default=os.environ.get("MM_DATASET_ROOT"),
                    help="MeshMamba dataset root (expects MeshFile/ and SaliencyMap/ subdirs). "
                         "Env: MM_DATASET_ROOT")
    ap.add_argument("--sal3d-dataset-root",
                    default=os.environ.get("SAL3D_DATASET_ROOT"),
                    help="SAL3D dataset root (expects sal3d_fixed_face_gt/ and Meshes/ subdirs). "
                         "Env: SAL3D_DATASET_ROOT")
    args = ap.parse_args()

    if args.cone_maps_root is None:
        print("[ERROR] --cone-maps-root is required. Set CONE_MAPS_ROOT env var or pass --cone-maps-root.",
              file=sys.stderr)
        sys.exit(1)

    cone_root          = Path(args.cone_maps_root)
    out_root           = Path(args.output_dir)
    staging            = Path(args.staging)
    mm_dataset_root    = Path(args.mm_dataset_root) if args.mm_dataset_root else None
    sal3d_dataset_root = Path(args.sal3d_dataset_root) if args.sal3d_dataset_root else None
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

    # Dataset root preflight
    needs_mm    = any(ds == "meshmamba" for ds, _, _ in models)
    needs_sal3d = any(ds == "sal3d"     for ds, _, _ in models)
    for root, flag, needed in [
        (mm_dataset_root,    "MM_DATASET_ROOT / --mm-dataset-root",    needs_mm),
        (sal3d_dataset_root, "SAL3D_DATASET_ROOT / --sal3d-dataset-root", needs_sal3d),
    ]:
        if needed and (root is None or not root.is_dir()):
            if root is None:
                print(f"[ERROR] Dataset root not set. Set via env var or CLI flag: {flag}",
                      file=sys.stderr)
            else:
                print(f"[ERROR] Dataset root not found: {root}\n"
                      f"  Set via env var or CLI flag: {flag}", file=sys.stderr)
            sys.exit(1)

    # Path check
    all_ok = True
    print(f"\n{'DRY-RUN' if args.dry_run else 'PATH CHECK'}: {len(models)} models")
    for ds, track, model in models:
        try:
            p = resolve_paths(ds, track, model, cone_root, gt_lookup,
                              mm_dataset_root=mm_dataset_root,
                              sal3d_dataset_root=sal3d_dataset_root)
        except (RuntimeError, ValueError) as exc:
            print(f"  {ds:10} {track:12} {model:40}  ERROR: {exc}", file=sys.stderr)
            all_ok = False
            continue
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
        try:
            paths = resolve_paths(ds, track, model, cone_root, gt_lookup,
                                  mm_dataset_root=mm_dataset_root,
                                  sal3d_dataset_root=sal3d_dataset_root)
        except (RuntimeError, ValueError) as exc:
            print(f"\n[{i:02d}/{len(models)}] SKIP {ds} {track} {model}: {exc}", file=sys.stderr)
            results.append(dict(ds=ds, track=track, model=model, map_type="gt", ok=False, elapsed=0.0))
            results.append(dict(ds=ds, track=track, model=model, map_type="cone", ok=False, elapsed=0.0))
            continue
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
