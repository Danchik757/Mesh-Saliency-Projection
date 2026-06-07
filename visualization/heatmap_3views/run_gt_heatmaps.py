#!/usr/bin/env python3
"""
Рендер 3-view heatmap для GT saliency всех моделей.
Запуск: python3 run_gt_heatmaps.py
"""

import subprocess, sys, time
from multiprocessing import Pool
from pathlib import Path
import numpy as np

BASE   = Path("/mnt/ssd1/29d_kon/heatmap_renders")
OUT    = BASE / "output"
TMP    = BASE / "tmp/gt_prep"
ENV_PY = BASE / "env/bin/python3"
RENDER = BASE / "code/render_heatmap_cmd.py"

MAMBA_RGB_ROOT = Path("/mnt/ssd1/29d_kon/FINAL_rgb/MeshMambaSaliency")
MAMBA_NON_ROOT = Path("/mnt/ssd1/29d_kon/FINAL/MeshMambaSaliency")
SAL3D_DATASET  = BASE / "data/sal3d/SAL3D_Dataset"

# (display_name, canonical, dataset, texture_type)
MODELS = [
    # MeshMamba RGB
    ("Cat_v1_l3",               "Cat_v1_L3",                     "meshmamba_rgb", "rgb_texture"),
    ("Spinning_Top_v1_L3",      "Spinning_Top_v1_L3",            "meshmamba_rgb", "rgb_texture"),
    ("egypt_sphinx_iterations-2","egypt_sphinx_iterations-2",    "meshmamba_rgb", "rgb_texture"),
    ("Horse_v01-it2",           "Horse_v01-it2",                 "meshmamba_rgb", "rgb_texture"),
    ("Cardigan_Welsh_Corgi_v1_L3","Cardigan_Welsh_Corgi_v1_L3",  "meshmamba_rgb", "rgb_texture"),
    ("Flying_saucer_v1_L3",     "Flying_saucer_v1_L3",           "meshmamba_rgb", "rgb_texture"),
    # MeshMamba non_texture
    ("Raptor_Claw_Fossil_v2_l3",        "Raptor_Claw_Fossil_v2_l3",        "meshmamba_non", "non_texture"),
    ("Marco_Polo_Sheep_v1_L3",          "Marco_Polo_Sheep_v1_L3",          "meshmamba_non", "non_texture"),
    ("Jambu_fruit_dove_v1_L3",          "Jambu_fruit_dove_v1_L3",          "meshmamba_non", "non_texture"),
    ("Stone_Chess_Knight_Side_A_v2_l1", "Stone_Chess_Knight_Side_A_v2_l1", "meshmamba_non", "non_texture"),
    ("King_Cake_v2_L2",                 "King_Cake_v2_L2",                 "meshmamba_non", "non_texture"),
    # SAL3D
    ("alien", "alien", "sal3d", None),
    ("bunny", "bunny", "sal3d", None),
    ("dragon","dragon","sal3d", None),
    ("horse", "horse", "sal3d", None),
    ("lion",  "lion",  "sal3d", None),
]


def find_gt_sal(display, canonical, dataset, texture_type):
    """Возвращает Path к 1D-файлу с GT saliency (создаёт при необходимости для SAL3D)."""
    if dataset == "meshmamba_rgb":
        gt_dir = MAMBA_RGB_ROOT / "SaliencyMap/rgb_texture"
        # ищем case-insensitive
        for f in gt_dir.glob("*.csv"):
            if f.stem.lower() == canonical.lower():
                return f
        raise FileNotFoundError(f"GT CSV not found for {canonical} in {gt_dir}")

    if dataset == "meshmamba_non":
        gt_dir = MAMBA_NON_ROOT / "SaliencyMap/non_texture"
        for f in gt_dir.glob("*.csv"):
            if f.stem.lower() == canonical.lower():
                return f
        raise FileNotFoundError(f"GT CSV not found for {canonical} in {gt_dir}")

    # SAL3D: 8-column, rows may not match OBJ order → reorder and extract col 6
    gaze_txt = SAL3D_DATASET / "Gaze" / f"{canonical}.txt"
    obj_path  = SAL3D_DATASET / "Meshes" / f"{canonical}.obj"
    out_sal   = TMP / f"{canonical}_gt_smooth_sal.txt"
    if out_sal.exists():
        return out_sal  # already prepared

    # load OBJ vertices
    verts = []
    with open(obj_path) as fh:
        for line in fh:
            if line.startswith("v "):
                p = line.split()
                verts.append([float(p[1]), float(p[2]), float(p[3])])
    verts = np.array(verts, dtype=np.float64)

    # load gaze txt: cols x y z nx ny nz smooth_sal binary_sal
    gaze = np.loadtxt(str(gaze_txt), dtype=np.float64)  # (20000, 8)
    gaze_xyz = gaze[:, :3]
    smooth_sal = gaze[:, 6]

    # match each OBJ vertex to nearest gaze row (kdtree)
    from scipy.spatial import cKDTree
    tree = cKDTree(gaze_xyz)
    _, idx = tree.query(verts, k=1)
    sal_reordered = smooth_sal[idx]   # (N_vertices,) aligned to OBJ order

    out_sal.parent.mkdir(parents=True, exist_ok=True)
    np.savetxt(str(out_sal), sal_reordered, fmt="%.10f")
    return out_sal


def find_obj(canonical, dataset, texture_type):
    if dataset == "sal3d":
        return SAL3D_DATASET / "Meshes" / f"{canonical}.obj"
    root = MAMBA_RGB_ROOT if dataset == "meshmamba_rgb" else MAMBA_NON_ROOT
    mesh_dir = root / "MeshFile" / texture_type
    cl = canonical.lower()
    for d in sorted(mesh_dir.iterdir()):
        if d.is_dir() and d.name.lower() == cl:
            for f in sorted(d.iterdir()):
                if f.suffix.lower() == ".obj":
                    return f
    raise FileNotFoundError(f"OBJ not found: {canonical} in {mesh_dir}")


def process(job):
    display, canonical, dataset, texture_type = job
    job_id = f"{dataset}__{display}__GT"
    t0 = time.time()
    print(f"[START] {job_id}", flush=True)

    try:
        sal_path = find_gt_sal(display, canonical, dataset, texture_type)
        obj_path = find_obj(canonical, dataset, texture_type)
    except Exception as e:
        print(f"[FAIL]  {job_id}: {e}", flush=True)
        return (job_id, False, time.time()-t0)

    out_png = OUT / f"{dataset}__{display}__GT__heatmap_3views.png"
    title   = f"{dataset}  |  {display}  |  GT"

    r = subprocess.run([
        str(ENV_PY), str(RENDER),
        "--obj",    str(obj_path),
        "--sal",    str(sal_path),
        "--output", str(out_png),
        "--title",  title,
    ], capture_output=True, text=True, timeout=180)

    elapsed = time.time()-t0
    ok = r.returncode == 0
    print(f"{'[OK]  ' if ok else '[FAIL]'} {job_id} ({elapsed:.1f}s)", flush=True)
    if not ok:
        print(f"  {r.stderr[-300:]}", flush=True)
    return (job_id, ok, elapsed)


if __name__ == "__main__":
    import os
    OUT.mkdir(parents=True, exist_ok=True)
    TMP.mkdir(parents=True, exist_ok=True)
    n = min(len(MODELS), os.cpu_count() or 8)
    print(f"GT heatmaps: {len(MODELS)} models, {n} workers", flush=True)
    t0 = time.time()
    with Pool(processes=n) as pool:
        results = pool.map(process, MODELS)
    total = time.time()-t0
    n_ok = sum(1 for _,ok,_ in results if ok)
    print(f"\nDone: {n_ok}/{len(MODELS)} OK in {total:.1f}s")
    for jid, ok, el in results:
        print(f"  {'OK  ' if ok else 'FAIL'} {jid} ({el:.1f}s)")
