#!/usr/bin/env python3
"""
CLI-рендер 3-view saliency heatmap (Front / Side / Top) через PyVista.

Usage:
  python render_heatmap_cmd.py \
    --obj    /path/to/mesh.obj \
    --sal    /path/to/saliency.txt \
    --output /path/to/output.png \
    --title  "My mesh | screen_space" \
    --colormap hot
"""

import argparse
import sys
import numpy as np
from pathlib import Path

os_import_error = None
try:
    import pyvista as pv
    import matplotlib
    matplotlib.use("Agg")          # headless — no display needed
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors
    from matplotlib.cm import ScalarMappable
except ImportError as e:
    os_import_error = e


# ─── OBJ parsing ─────────────────────────────────────────────────────────────
def parse_obj(path: Path):
    vertices, faces = [], []
    with open(path) as fh:
        for line in fh:
            if line.startswith("v "):
                p = line.split()
                vertices.append([float(p[1]), float(p[2]), float(p[3])])
            elif line.startswith("f "):
                p = line.split()
                tri = [int(t.split("/")[0]) - 1 for t in p[1:4]]
                faces.append(tri)
    return np.array(vertices, dtype=np.float64), np.array(faces, dtype=np.int32)


# ─── Build PyVista mesh ───────────────────────────────────────────────────────
def build_mesh(vertices, faces, face_sal):
    pv_faces = np.hstack([np.full((len(faces), 1), 3, dtype=np.int32), faces])
    mesh = pv.PolyData(vertices.astype(np.float32), pv_faces.ravel())
    mesh.cell_data["saliency"] = face_sal.astype(np.float32)
    return mesh


# ─── Render views ────────────────────────────────────────────────────────────
VIEWS_4 = {
    "Front": (( 0,  0,  1), (0, 1, 0)),
    "Back":  (( 0,  0, -1), (0, 1, 0)),
    "Left":  ((-1,  0,  0), (0, 1, 0)),
    "Right": (( 1,  0,  0), (0, 1, 0)),
}

VIEWS_6 = {
    "Front":  (( 0,  0,  1), (0,  1,  0)),
    "Back":   (( 0,  0, -1), (0,  1,  0)),
    "Left":   ((-1,  0,  0), (0,  1,  0)),
    "Right":  (( 1,  0,  0), (0,  1,  0)),
    "Top":    (( 0,  1,  0), (0,  0, -1)),
    "Bottom": (( 0, -1,  0), (0,  0,  1)),
}

VIEWS_MAP = {4: VIEWS_4, 6: VIEWS_6}


def render_views(mesh, face_sal, out_path: Path, title: str,
                 colormap: str = "hot", n_views: int = 4):
    import os
    os.environ.setdefault("DISPLAY", "")
    pv.OFF_SCREEN = True

    vmin = float(np.percentile(face_sal, 2))
    vmax = float(np.percentile(face_sal, 98))
    clim = [vmin, vmax]

    views = VIEWS_MAP.get(n_views, VIEWS_4)

    images = {}
    for label, (cam_dir, up_vec) in views.items():
        pl = pv.Plotter(off_screen=True, window_size=(800, 800))
        pl.set_background("white")
        pl.add_mesh(
            mesh,
            scalars="saliency",
            cmap=colormap,
            clim=clim,
            show_scalar_bar=False,
            smooth_shading=False,
        )
        center = np.array(mesh.center)
        length = mesh.length * 0.9
        pl.camera.position = center + np.array(cam_dir, dtype=float) * length
        pl.camera.focal_point = center
        pl.camera.up = up_vec
        pl.reset_camera()
        img = pl.screenshot(return_img=True)
        images[label] = img
        pl.close()

    n_views = len(images)   # = 4

    # Фигура: 4 квадратных панели + тонкая полоска colorbar справа
    # width_ratios: каждая панель = 1, colorbar = 0.04 (≈3.2% ширины)
    fig = plt.figure(figsize=(n_views * 4 + 0.5, 4.5), facecolor="#111111")
    fig.suptitle(title, color="white", fontsize=12, fontweight="bold", y=0.97)

    gs = fig.add_gridspec(
        1, n_views + 1,
        width_ratios=[1] * n_views + [0.04],
        wspace=0.025,
        left=0.01, right=0.99,
        top=0.88, bottom=0.04,
    )

    for col, (label, img) in enumerate(images.items()):
        ax = fig.add_subplot(gs[0, col])
        ax.imshow(img)
        ax.set_title(label, color="white", fontsize=11, pad=4)
        ax.axis("off")

    # Colorbar — тонкая вертикальная полоска в последней колонке
    cax  = fig.add_subplot(gs[0, n_views])
    norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
    sm   = ScalarMappable(cmap=plt.get_cmap(colormap), norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, cax=cax, orientation="vertical")
    cbar.set_label("Saliency", color="white", fontsize=9, labelpad=4)
    cbar.ax.yaxis.set_tick_params(color="white", labelsize=7)
    plt.setp(cbar.ax.yaxis.get_ticklabels(), color="white")
    cbar.outline.set_edgecolor("white")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(out_path), dpi=150, bbox_inches="tight", facecolor="#111111")
    plt.close(fig)
    print(f"[PNG] {out_path}", flush=True)


# ─── main ─────────────────────────────────────────────────────────────────────
def main():
    if os_import_error:
        print(f"[ERROR] Missing dependency: {os_import_error}", file=sys.stderr)
        sys.exit(1)

    ap = argparse.ArgumentParser(description="Render 3-view saliency heatmap PNG.")
    ap.add_argument("--obj",      type=Path, required=True, help="OBJ mesh file")
    ap.add_argument("--sal",      type=Path, required=True, help="Per-face (or per-vertex) saliency .txt")
    ap.add_argument("--output",   type=Path, required=True, help="Output PNG path")
    ap.add_argument("--title",    default=None,              help="Title shown on PNG")
    ap.add_argument("--colormap", default="hot",             help="Matplotlib colormap (default: hot)")
    ap.add_argument("--views",    type=int, default=4, choices=[4, 6],
                    help="Number of orthographic views: 4 (Front/Back/Left/Right) or 6 (+ Top/Bottom)")
    args = ap.parse_args()

    if not args.obj.exists():
        print(f"[ERROR] OBJ not found: {args.obj}", file=sys.stderr); sys.exit(1)
    if not args.sal.exists():
        print(f"[ERROR] Saliency file not found: {args.sal}", file=sys.stderr); sys.exit(1)

    vertices, faces = parse_obj(args.obj)
    sal = np.loadtxt(str(args.sal), dtype=np.float64)

    # Per-vertex → per-face conversion (for SAL3D output)
    if len(sal) != len(faces):
        if len(sal) == len(vertices):
            sal = sal[faces].mean(axis=1)
            print(f"[INFO] Converted {len(vertices)} vertex saliency → {len(faces)} face saliency")
        else:
            print(f"[ERROR] saliency length {len(sal)} matches neither "
                  f"faces ({len(faces)}) nor vertices ({len(vertices)})", file=sys.stderr)
            sys.exit(1)

    title = args.title or args.obj.stem
    mesh  = build_mesh(vertices, faces, sal)
    render_views(mesh, sal, args.output, title, colormap=args.colormap, n_views=args.views)


if __name__ == "__main__":
    main()
