#!/usr/bin/env python3
"""
Перерендер всех heatmap с корректными ракурсами.
Для каждой модели берём mean_rot_deg из JSON и передаём --rot-deg,
чтобы один из 4 видов смотрел именно с той стороны, с которой видели участники.
Выходные PNG сохраняются в output_v2/.
"""

import subprocess, json, math, os, time
from multiprocessing import Pool
from pathlib import Path

BASE     = Path("/mnt/ssd1/29d_kon/heatmap_renders")
ENV_PY   = BASE / "env/bin/python3"
RENDER   = BASE / "code/render_heatmap_cmd.py"
OUT_OLD  = BASE / "output"
OUT_NEW  = BASE / "output_v2"

MAMBA_RGB_ROOT = Path("/mnt/ssd1/29d_kon/FINAL_rgb/MeshMambaSaliency")
MAMBA_NON_ROOT = Path("/mnt/ssd1/29d_kon/FINAL/MeshMambaSaliency")
SAL3D_DATASET  = BASE / "data/sal3d/SAL3D_Dataset"
JSON_RGB  = Path("/mnt/ssd1/29d_kon/FINAL_rgb/logs/mvp_data")
JSON_NON  = BASE / "data/json/MeshMamba_non_texture"
JSON_SAL3D = BASE / "data/json/SAL3D"

def mean_rot_deg(json_path):
    d = json.load(open(json_path))
    angles = [math.degrees(f["rotation_z_radians"]) for f in d["frames"]]
    return sum(angles) / len(angles)

def find_obj(canonical, dataset, texture_type):
    if dataset == "sal3d":
        return SAL3D_DATASET / "Meshes" / f"{canonical}.obj"
    root = MAMBA_RGB_ROOT if dataset == "meshmamba_rgb" else MAMBA_NON_ROOT
    mesh_dir = root / "MeshFile" / texture_type
    for d in sorted(mesh_dir.iterdir()):
        if d.is_dir() and d.name.lower() == canonical.lower():
            for f in sorted(d.iterdir()):
                if f.suffix.lower() == ".obj":
                    return f
    raise FileNotFoundError(f"OBJ not found: {canonical}")

# (display, canonical, dataset, texture_type, json_prefix)
MODELS = [
    ("Cat_v1_l3",               "Cat_v1_L3",                     "meshmamba_rgb", "rgb_texture", "MeshMamba_rgb_texture"),
    ("Spinning_Top_v1_L3",      "Spinning_Top_v1_L3",            "meshmamba_rgb", "rgb_texture", "MeshMamba_rgb_texture"),
    ("egypt_sphinx_iterations-2","egypt_sphinx_V2_L3",           "meshmamba_rgb", "rgb_texture", "MeshMamba_rgb_texture"),
    ("Horse_v01-it2",           "Horse_v01_L3",                  "meshmamba_rgb", "rgb_texture", "MeshMamba_rgb_texture"),
    ("Cardigan_Welsh_Corgi_v1_L3","Cardigan_Welsh_Corgi_v1_L3",  "meshmamba_rgb", "rgb_texture", "MeshMamba_rgb_texture"),
    ("Flying_saucer_v1_L3",     "Flying_saucer_v1_L3",           "meshmamba_rgb", "rgb_texture", "MeshMamba_rgb_texture"),
    ("Raptor_Claw_Fossil_v2_l3",        "Raptor_Claw_Fossil_v2_L3",        "meshmamba_non", "non_texture", "MeshMamba_non_texture"),
    ("Marco_Polo_Sheep_v1_L3",          "Marco_Polo_Sheep_v1_L3",          "meshmamba_non", "non_texture", "MeshMamba_non_texture"),
    ("Jambu_fruit_dove_v1_L3",          "Jambu_Fruit_Dove_v1_L3",          "meshmamba_non", "non_texture", "MeshMamba_non_texture"),
    ("Stone_Chess_Knight_Side_A_v2_l1", "Stone_Chess_Knight_Side_A_v2_L1", "meshmamba_non", "non_texture", "MeshMamba_non_texture"),
    ("King_Cake_v2_L2",                 "King_Cake_v2_L2",                 "meshmamba_non", "non_texture", "MeshMamba_non_texture"),
    ("alien", "alien", "sal3d", None, "Sal3D"),
    ("bunny", "bunny", "sal3d", None, "Sal3D"),
    ("dragon","dragon","sal3d", None, "Sal3D"),
    ("horse", "horse", "sal3d", None, "Sal3D"),
    ("lion",  "lion",  "sal3d", None, "Sal3D"),
]

METHODS = ["screen_space", "cone_gaussian", "GT"]

def process(job):
    display, canonical, dataset, texture_type, json_prefix, method = job
    job_id = f"{dataset}__{display}__{method}"
    t0 = time.time()

    # Найти OBJ
    try:
        obj_path = find_obj(canonical, dataset, texture_type)
    except Exception as e:
        print(f"[FAIL] {job_id}: {e}", flush=True)
        return (job_id, False)

    # Найти sal файл (уже готовый PNG → берём соответствующий sal из tmp или GT)
    old_png = OUT_OLD / f"{dataset}__{display}__{method}__heatmap_3views.png"
    if not old_png.exists():
        print(f"[SKIP] {job_id}: source PNG not found", flush=True)
        return (job_id, False)

    # Найти sal_path
    TMP = BASE / "tmp"
    if method == "GT":
        if dataset == "meshmamba_rgb":
            gt_dir = MAMBA_RGB_ROOT / "SaliencyMap/rgb_texture"
        elif dataset == "meshmamba_non":
            gt_dir = MAMBA_NON_ROOT / "SaliencyMap/non_texture"
        else:
            sal_path = BASE / "tmp/gt_prep" / f"{canonical}_gt_smooth_sal.txt"
            if not sal_path.exists():
                print(f"[FAIL] {job_id}: GT sal not found: {sal_path}", flush=True)
                return (job_id, False)
            gt_dir = None

        if gt_dir is not None:
            sal_path = None
            for f in gt_dir.glob("*.csv"):
                if f.stem.lower() == canonical.lower() or f.stem.lower() == display.lower():
                    sal_path = f; break
            if sal_path is None:
                print(f"[FAIL] {job_id}: GT CSV not found in {gt_dir}", flush=True)
                return (job_id, False)
    elif method == "screen_space":
        tag = "ss"
        sal_path = TMP / dataset / "screen_space" / canonical / tag
        cands = list(sal_path.glob("*_screen_space_faces.txt")) + list(sal_path.glob("*_screen_space_vertices.txt"))
        if not cands:
            print(f"[FAIL] {job_id}: SS sal not found in {sal_path}", flush=True)
            return (job_id, False)
        sal_path = cands[0]
    else:  # cone_gaussian
        tag = "cone"
        sal_path = TMP / dataset / "cone" / canonical / tag
        # Check cone2 for sal3d alien/lion
        if not list(sal_path.glob("*_cone_*.txt")):
            sal_path = TMP / "sal3d/cone2" / canonical / tag
        cands = list(sal_path.glob("*_cone_faces.txt")) + list(sal_path.glob("*_cone_vertices.txt"))
        if not cands:
            print(f"[FAIL] {job_id}: cone sal not found in {sal_path}", flush=True)
            return (job_id, False)
        sal_path = cands[0]

    # Найти mean_rot_deg из JSON
    rot_deg = None
    if dataset != "sal3d":
        json_dir = JSON_RGB if dataset == "meshmamba_rgb" else JSON_NON
        # ищем JSON
        json_cands = list(json_dir.glob(f"{json_prefix}_{canonical}.json"))
        if not json_cands:
            # case-insensitive
            for f in json_dir.glob("*.json"):
                if canonical.lower() in f.stem.lower():
                    json_cands = [f]; break
        if json_cands:
            rot_deg = mean_rot_deg(json_cands[0])
    else:
        json_cands = list(JSON_SAL3D.glob(f"Sal3D_{canonical}.json"))
        if json_cands:
            rot_deg = mean_rot_deg(json_cands[0])

    # Render
    out_png = OUT_NEW / f"{dataset}__{display}__{method}__heatmap_3views.png"
    title   = f"{dataset}  |  {display}  |  {method}"
    if rot_deg is not None:
        title += f"  (view≈{rot_deg:.0f}°)"

    cmd = [str(ENV_PY), str(RENDER),
           "--obj", str(obj_path),
           "--sal", str(sal_path),
           "--output", str(out_png),
           "--title", title]
    if rot_deg is not None:
        cmd += ["--rot-deg", str(rot_deg % 360)]

    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    elapsed = time.time()-t0
    ok = r.returncode == 0
    print(f"{'[OK]  ' if ok else '[FAIL]'} {job_id} ({elapsed:.1f}s)", flush=True)
    if not ok:
        print(f"  {r.stderr[-300:]}", flush=True)
    return (job_id, ok)


if __name__ == "__main__":
    OUT_NEW.mkdir(parents=True, exist_ok=True)
    jobs = []
    for m in MODELS:
        for method in METHODS:
            jobs.append((*m, method))

    n = min(len(jobs), os.cpu_count() or 8)
    print(f"Rerender {len(jobs)} jobs with {n} workers...", flush=True)
    t0 = time.time()
    with Pool(processes=n) as pool:
        results = pool.map(process, jobs)
    total = time.time()-t0
    n_ok = sum(1 for _, ok in results if ok)
    print(f"\nDone: {n_ok}/{len(jobs)} OK in {total:.1f}s")
    print(f"Results: {OUT_NEW}")
