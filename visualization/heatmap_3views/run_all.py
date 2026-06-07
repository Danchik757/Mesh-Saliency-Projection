#!/usr/bin/env python3
"""
Параллельный запуск: screen_space + cone для всех моделей → PNG heatmap.

Запуск:
  python run_all.py [--workers N]

По умолчанию N = min(44, nproc).
"""

import argparse
import os
import subprocess
import sys
import time
from multiprocessing import Pool
from pathlib import Path

# ─── Пути на сервере ──────────────────────────────────────────────────────────
BASE          = Path("/mnt/ssd1/29d_kon/heatmap_renders")
CODE          = BASE / "code"
DATA          = BASE / "data"
OUT           = BASE / "output"
TMP           = BASE / "tmp"
ENV_PY        = BASE / "env/bin/python3"

# Датасеты (уже на сервере)
MAMBA_RGB_ROOT   = Path("/mnt/ssd1/29d_kon/FINAL_rgb/MeshMambaSaliency")
MAMBA_NON_ROOT   = Path("/mnt/ssd1/29d_kon/FINAL/MeshMambaSaliency")
MAMBA_RGB_JSON   = Path("/mnt/ssd1/29d_kon/FINAL_rgb/logs/mvp_data")
MAMBA_NON_JSON   = DATA / "json/MeshMamba_non_texture"   # перенесено с локальной машины
SAL3D_ROOT       = DATA / "sal3d/SAL3D_Dataset"
SAL3D_JSON       = DATA / "json/SAL3D"

# Gaze CSV (перенесены с локальной машины)
CSV_RGB  = DATA / "gaze_csv/MeshMamba_rgb_texture"
CSV_NON  = DATA / "gaze_csv/MeshMamba_non_texture"
CSV_SAL3D = DATA / "gaze_csv/SAL3D"

# Eval scripts (внутри перенесённого репо)
REPO     = CODE / "Mesh-Saliency-Projection"
SS_MAMBA = REPO / "reprojection_methods/screen_space_gaussian/eval_meshmamba_screen_space_v2.py"
CO_MAMBA = REPO / "reprojection_methods/cone_projection_on_mesh/eval_meshmamba_cone.py"
SS_SAL3D = REPO / "reprojection_methods/screen_space_gaussian/eval_sal3d_screen_space.py"
CO_SAL3D = REPO / "reprojection_methods/cone_projection_on_mesh/eval_sal3d_cone.py"
RENDER   = CODE / "render_heatmap_cmd.py"

# ─── Описание задач ───────────────────────────────────────────────────────────
# (display_name, canonical_model, dataset, texture_type)
JOBS_RGB = [
    ("Cat_v1_l3",               "Cat_v1_L3",                    "meshmamba_rgb", "rgb_texture"),
    ("Spinning_Top_v1_L3",      "Spinning_Top_v1_L3",           "meshmamba_rgb", "rgb_texture"),
    ("egypt_sphinx_iterations-2","egypt_sphinx_V2_L3",          "meshmamba_rgb", "rgb_texture"),
    ("Horse_v01-it2",           "Horse_v01_L3",                 "meshmamba_rgb", "rgb_texture"),
    ("Cardigan_Welsh_Corgi_v1_L3","Cardigan_Welsh_Corgi_v1_L3", "meshmamba_rgb", "rgb_texture"),
    ("Flying_saucer_v1_L3",     "Flying_saucer_v1_L3",         "meshmamba_rgb", "rgb_texture"),
]
JOBS_NON = [
    ("Raptor_Claw_Fossil_v2_l3",        "Raptor_Claw_Fossil_v2_L3",       "meshmamba_non", "non_texture"),
    ("Marco_Polo_Sheep_v1_L3",          "Marco_Polo_Sheep_v1_L3",         "meshmamba_non", "non_texture"),
    ("Jambu_fruit_dove_v1_L3",          "Jambu_Fruit_Dove_v1_L3",         "meshmamba_non", "non_texture"),
    ("Stone_Chess_Knight_Side_A_v2_l1", "Stone_Chess_Knight_Side_A_v2_L1","meshmamba_non", "non_texture"),
    ("King_Cake_v2_L2",                 "King_Cake_v2_L2",                "meshmamba_non", "non_texture"),
]
JOBS_SAL3D = [
    ("alien", "alien", "sal3d", None),
    ("bunny", "bunny", "sal3d", None),
    ("dragon","dragon","sal3d", None),
    ("horse", "horse", "sal3d", None),
    ("lion",  "lion",  "sal3d", None),
]


# ─── Helpers ──────────────────────────────────────────────────────────────────
def find_obj(canonical, dataset, texture_type):
    """Case-insensitive поиск OBJ-файла."""
    if dataset == "sal3d":
        p = SAL3D_ROOT / "Meshes" / f"{canonical}.obj"
        if p.exists():
            return p
        raise FileNotFoundError(f"SAL3D OBJ not found: {p}")

    root = MAMBA_RGB_ROOT if dataset == "meshmamba_rgb" else MAMBA_NON_ROOT
    mesh_dir = root / "MeshFile" / texture_type
    canon_low = canonical.lower()
    for d in sorted(mesh_dir.iterdir()):
        if d.is_dir() and d.name.lower() == canon_low:
            for f in sorted(d.iterdir()):
                if f.suffix.lower() == ".obj":
                    return f
    raise FileNotFoundError(f"OBJ not found for {canonical} in {mesh_dir}")


def _run(cmd, timeout=600):
    """Запускает команду, возвращает (returncode, stdout, stderr)."""
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout, r.stderr


def _find_output(out_dir: Path, model: str, pattern: str):
    """Ищет файл по шаблону. out_dir = tmp/.../model/tag."""
    cands = list(out_dir.glob(pattern))
    if cands:
        return cands[0]
    # case-insensitive fallback
    pattern_low = pattern.lower().replace("*", "")
    for f in out_dir.iterdir():
        if pattern_low in f.name.lower():
            return f
    return None


# ─── Eval runners ─────────────────────────────────────────────────────────────
TAG_SS   = "ss"
TAG_CONE = "cone"


def eval_screen_space_mamba(canonical, dataset, texture_type):
    csv_root  = CSV_RGB if dataset == "meshmamba_rgb" else CSV_NON
    json_root = MAMBA_RGB_JSON if dataset == "meshmamba_rgb" else MAMBA_NON_JSON
    droot     = MAMBA_RGB_ROOT if dataset == "meshmamba_rgb" else MAMBA_NON_ROOT
    out_base  = TMP / dataset / "screen_space"

    rc, out, err = _run([
        str(ENV_PY), str(SS_MAMBA),
        "--model",          canonical,
        "--texture-type",   texture_type,
        "--dataset-root",   str(droot),
        "--csv-root",       str(csv_root),
        "--json-root",      str(json_root),
        "--output-dir",     str(out_base),
        "--tag",            TAG_SS,
        "--transform-order","blender_rig",
    ])
    if rc != 0:
        return None, err
    f = _find_output(out_base / canonical / TAG_SS, canonical, "*_screen_space_faces.txt")
    return f, err


def eval_cone_mamba(canonical, dataset, texture_type):
    csv_root  = CSV_RGB if dataset == "meshmamba_rgb" else CSV_NON
    json_root = MAMBA_RGB_JSON if dataset == "meshmamba_rgb" else MAMBA_NON_JSON
    droot     = MAMBA_RGB_ROOT if dataset == "meshmamba_rgb" else MAMBA_NON_ROOT
    out_base  = TMP / dataset / "cone"

    rc, out, err = _run([
        str(ENV_PY), str(CO_MAMBA),
        "--model",          canonical,
        "--texture-type",   texture_type,
        "--dataset-root",   str(droot),
        "--csv-root",       str(csv_root),
        "--json-root",      str(json_root),
        "--output-dir",     str(out_base),
        "--tag",            TAG_CONE,
        "--transform-order","blender_rig",
    ])
    if rc != 0:
        return None, err
    f = _find_output(out_base / canonical / TAG_CONE, canonical, "*_cone_faces.txt")
    return f, err


def eval_screen_space_sal3d(model):
    out_base = TMP / "sal3d" / "screen_space"
    rc, out, err = _run([
        str(ENV_PY), str(SS_SAL3D),
        "--model",          model,
        "--dataset-root",   str(SAL3D_ROOT),
        "--csv-root",       str(CSV_SAL3D),
        "--json-root",      str(SAL3D_JSON),
        "--output-dir",     str(out_base),
        "--tag",            TAG_SS,
        "--transform-order","blender_rig",
    ])
    if rc != 0:
        return None, err
    f = _find_output(out_base / model / TAG_SS, model, "*_screen_space_vertices.txt")
    return f, err


def eval_cone_sal3d(model):
    out_base = TMP / "sal3d" / "cone"
    rc, out, err = _run([
        str(ENV_PY), str(CO_SAL3D),
        "--model",          model,
        "--dataset-root",   str(SAL3D_ROOT),
        "--csv-root",       str(CSV_SAL3D),
        "--json-root",      str(SAL3D_JSON),
        "--output-dir",     str(out_base),
        "--tag",            TAG_CONE,
        "--transform-order","blender_rig",
    ])
    if rc != 0:
        return None, err
    f = _find_output(out_base / model / TAG_CONE, model, "*_cone_vertices.txt")
    return f, err


# ─── Render PNG ───────────────────────────────────────────────────────────────
def render_png(obj_path, sal_path, out_png, title):
    rc, _, err = _run([
        str(ENV_PY), str(RENDER),
        "--obj",    str(obj_path),
        "--sal",    str(sal_path),
        "--output", str(out_png),
        "--title",  title,
    ], timeout=180)
    if rc != 0:
        return False, err
    return True, ""


# ─── Job processor ────────────────────────────────────────────────────────────
def process_job(job):
    """
    job = (display_name, canonical, dataset, texture_type, method)
    Возвращает (job_id, success, elapsed, error_msg)
    """
    display, canonical, dataset, texture_type, method = job
    job_id = f"{dataset}__{display}__{method}"
    t0 = time.time()

    print(f"[START] {job_id}", flush=True)

    # 1. Eval → saliency txt
    sal_path = err_msg = None
    try:
        if dataset in ("meshmamba_rgb", "meshmamba_non"):
            if method == "screen_space":
                sal_path, err_msg = eval_screen_space_mamba(canonical, dataset, texture_type)
            else:
                sal_path, err_msg = eval_cone_mamba(canonical, dataset, texture_type)
        else:
            if method == "screen_space":
                sal_path, err_msg = eval_screen_space_sal3d(canonical)
            else:
                sal_path, err_msg = eval_cone_sal3d(canonical)
    except Exception as e:
        elapsed = time.time() - t0
        print(f"[FAIL] {job_id}: eval exception: {e}", flush=True)
        return (job_id, False, elapsed, str(e))

    if sal_path is None or not Path(sal_path).exists():
        elapsed = time.time() - t0
        snippet = (err_msg or "")[-400:].strip()
        print(f"[FAIL] {job_id}: eval produced no output\n  stderr: {snippet}", flush=True)
        return (job_id, False, elapsed, snippet)

    # 2. Find OBJ
    try:
        obj_path = find_obj(canonical, dataset, texture_type)
    except FileNotFoundError as e:
        elapsed = time.time() - t0
        print(f"[FAIL] {job_id}: {e}", flush=True)
        return (job_id, False, elapsed, str(e))

    # 3. Render PNG
    method_label = "screen_space" if method == "screen_space" else "cone_gaussian"
    out_png  = OUT / f"{dataset}__{display}__{method_label}__heatmap_3views.png"
    title    = f"{dataset}  |  {display}  |  {method_label}"
    ok, render_err = render_png(obj_path, sal_path, out_png, title)

    elapsed = time.time() - t0
    if ok:
        print(f"[OK]   {job_id}  ({elapsed:.1f}s)  →  {out_png.name}", flush=True)
        return (job_id, True, elapsed, "")
    else:
        snippet = render_err[-400:].strip()
        print(f"[FAIL] {job_id}: render failed\n  {snippet}", flush=True)
        return (job_id, False, elapsed, snippet)


# ─── main ─────────────────────────────────────────────────────────────────────
def build_all_jobs():
    jobs = []
    for entry in JOBS_RGB:
        display, canonical, dataset, tex = entry
        for method in ("screen_space", "cone"):
            jobs.append((display, canonical, dataset, tex, method))
    for entry in JOBS_NON:
        display, canonical, dataset, tex = entry
        for method in ("screen_space", "cone"):
            jobs.append((display, canonical, dataset, tex, method))
    for entry in JOBS_SAL3D:
        display, canonical, dataset, tex = entry
        for method in ("screen_space", "cone"):
            jobs.append((display, canonical, dataset, tex, method))
    return jobs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=None,
                    help="Parallel workers (default: min(n_jobs, nproc))")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    TMP.mkdir(parents=True, exist_ok=True)

    jobs = build_all_jobs()
    n_jobs = len(jobs)
    n_cpu  = os.cpu_count() or 8
    n_workers = args.workers or min(n_jobs, n_cpu)

    print(f"{'='*60}")
    print(f"  Jobs: {n_jobs}   Workers: {n_workers}   CPUs: {n_cpu}")
    print(f"  Output: {OUT}")
    print(f"{'='*60}", flush=True)

    t0 = time.time()
    with Pool(processes=n_workers) as pool:
        results = pool.map(process_job, jobs)
    total = time.time() - t0

    n_ok   = sum(1 for _, ok, *_ in results if ok)
    n_fail = n_jobs - n_ok

    print(f"\n{'='*60}")
    print(f"  Done: {n_ok}/{n_jobs} OK  |  {n_fail} FAILED  |  {total:.1f}s total")
    print(f"{'='*60}")
    if n_fail:
        print("\nFailed jobs:")
        for job_id, ok, elapsed, err in results:
            if not ok:
                print(f"  ✗ {job_id}  ({elapsed:.1f}s)")
                if err:
                    print(f"    {err[:200]}")
    print(f"\nРезультаты: {OUT}")


if __name__ == "__main__":
    main()
