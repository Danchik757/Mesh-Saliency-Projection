#!/usr/bin/env python3
"""
Validate 3DVA per-view GT camera geometry by comparing Blender-rendered silhouettes
with the original GT images from 3DModels-Simplif-224-up/views/.

The GT images in views/ were rendered by the original paper authors for the 3 static
viewpoints from which participants viewed each model. The camera positions are given
as (azimuth, elevation) angle pairs in test_viewpoints/{model}.txt.

This script:
1. Reads azimuth/elevation for each of the 3 viewpoints.
2. Places a Blender camera on the corresponding orbital position.
3. Renders a 224×224 preview of the model.
4. Extracts silhouette from both the GT JPG and the Blender render.
5. Computes IoU between them.

High IoU (≥ 0.85) means our camera reconstruction is correct, which validates:
  - The OBJ orientation matches what the GT authors used.
  - The visibility masks from CentricityAndVisibilityMaps are valid.
  - Our combined GT construction is geometrically sound.

Camera model:
  Orbital camera around origin at (azimuth, elevation, radius).
  Convention (matches 3DStudio Max standard):
    azimuth = 0°   → camera on -Y axis (front view in Blender)
    azimuth = 90°  → camera on +X axis (right side view)
    elevation = 0° → camera level with the object
    elevation > 0° → camera above

Usage:
  python3 test/tools/validate_gt_viewpoints.py \\
    --model bunny \\
    --dataset-root $VISUAL_ATTENTION_3D_SHAPES_ROOT \\
    --gt-views-dir /path/to/3DModels-Simplif-224-up/views \\
    --test-viewpoints-dir /path/to/test_viewpoints \\
    --output-dir /tmp/gt_viewpoint_check \\
    [--camera-radius 1.5] \\
    [--fov-deg 60] \\
    [--search-radius]   # grid-search best camera radius
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image


# ── silhouette extraction ─────────────────────────────────────────────────────

def extract_silhouette_from_gt_jpg(jpg_path: Path, bg_threshold: float = 8.0) -> np.ndarray:
    """Extract binary mask from a GT JPG (white background).

    The GT images have a pure-white background [255,255,255].
    We use corner sampling to estimate background colour robustly.
    """
    img = np.asarray(Image.open(jpg_path).convert("RGB"), dtype=np.float32)
    h, w = img.shape[:2]
    patch = min(16, h // 8, w // 8)
    corners = np.concatenate([
        img[:patch, :patch].reshape(-1, 3),
        img[:patch, w - patch:].reshape(-1, 3),
        img[h - patch:, :patch].reshape(-1, 3),
        img[h - patch:, w - patch:].reshape(-1, 3),
    ], axis=0)
    bg = np.median(corners, axis=0)
    dist = np.linalg.norm(img - bg.reshape(1, 1, 3), axis=2)
    return dist > bg_threshold


def extract_silhouette_from_blender_png(png_path: Path) -> np.ndarray:
    """Extract binary mask from a Blender EEVEE render (transparent background).

    EEVEE with film_transparent=True writes alpha=0 for background, alpha>0 for mesh.
    Falls back to RGB distance from background if alpha is all-zero.
    """
    rgba = np.asarray(Image.open(png_path).convert("RGBA"), dtype=np.uint8)
    alpha = rgba[:, :, 3]
    if int(alpha.max()) > 0:
        return alpha > 0
    # fallback: RGB distance from corners
    rgb = rgba[:, :, :3].astype(np.float32)
    h, w = rgb.shape[:2]
    patch = min(16, h // 8, w // 8)
    corners = np.concatenate([
        rgb[:patch, :patch].reshape(-1, 3),
        rgb[:patch, w - patch:].reshape(-1, 3),
        rgb[h - patch:, :patch].reshape(-1, 3),
        rgb[h - patch:, w - patch:].reshape(-1, 3),
    ], axis=0)
    bg = np.median(corners, axis=0)
    dist = np.linalg.norm(rgb - bg.reshape(1, 1, 3), axis=2)
    return dist > 10.0


def iou(mask_a: np.ndarray, mask_b: np.ndarray) -> float:
    inter = float(np.logical_and(mask_a, mask_b).sum())
    union = float(np.logical_or(mask_a, mask_b).sum())
    return inter / union if union > 0 else 0.0


# ── orbital camera ────────────────────────────────────────────────────────────

def orbit_camera_position(azimuth_deg: float, elevation_deg: float, radius: float,
                          az_offset_deg: float = 180.0) -> tuple[float, float, float]:
    """Return Blender world-space camera position on orbital sphere.

    Convention (calibrated against 3DStudio Max azimuth from test_viewpoints/):
      The GT azimuth=0°   → camera on +Y axis (behind the model in Blender convention)
      az_offset_deg=180   → shift so our Blender frame matches GT convention

      azimuth=0°   → camera on -Y axis after offset (standard front view in Blender)
      azimuth=90°  → camera on -X axis after offset
      elevation=0° → level with origin
      elevation>0° → above origin

    Calibration note:
      GT view_002 (az=-163°, el=7°) shows model's BACK.
      In Blender, model back faces camera at (0,-R,z).
      Adding 180° to azimuth: (az+180)=-163+180=17° → camera at mostly -Y ← correct.
    """
    az = math.radians(azimuth_deg + az_offset_deg)
    el = math.radians(elevation_deg)
    r_xy = radius * math.cos(el)
    x = r_xy * math.sin(az)
    y = -r_xy * math.cos(az)
    z = radius * math.sin(el)
    return x, y, z


# ── Blender render helper ─────────────────────────────────────────────────────

BLENDER_RENDER_SCRIPT = """
import bpy, math, sys
from pathlib import Path

args = sys.argv[sys.argv.index('--') + 1:]
obj_path   = args[0]
output_png = args[1]
cx, cy, cz = float(args[2]), float(args[3]), float(args[4])
fov_deg    = float(args[5])
res        = int(args[6])

bpy.ops.wm.read_factory_settings(use_empty=True)

# ── render settings ──────────────────────────────────────────────────────────
scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.film_transparent = True
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode  = "RGBA"
scene.render.resolution_x = res
scene.render.resolution_y = res
scene.render.resolution_percentage = 100
scene.render.filepath = output_png

# ── import OBJ (forward_axis/up_axis ignored in Blender 4.1 wm.obj_import) ──
bpy.ops.wm.obj_import(filepath=obj_path, forward_axis='X', up_axis='Z')
obj = bpy.context.selected_objects[0]
bpy.context.view_layer.objects.active = obj
bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
obj.location = (0, 0, 0)

# Scale to fit in the same bbox as the video render (matches 3dva_render_1.py).
# BBOX_MAX_WIDTH=0.8, BBOX_MAX_DEPTH=0.8, BBOX_MAX_HEIGHT=0.7
from mathutils import Vector as V
bb = [obj.matrix_world @ V(c) for c in obj.bound_box]
w = max(c.x for c in bb) - min(c.x for c in bb)
d = max(c.y for c in bb) - min(c.y for c in bb)
h = max(c.z for c in bb) - min(c.z for c in bb)
sf = min(0.8 / w if w > 0 else 1.0,
         0.8 / d if d > 0 else 1.0,
         0.7 / h if h > 0 else 1.0)
obj.scale = (sf, sf, sf)
bpy.context.view_layer.update()

# ── emission material (flat blue, no lights needed) ──────────────────────────
mat = bpy.data.materials.new("M")
mat.use_nodes = True
nodes = mat.node_tree.nodes
links = mat.node_tree.links
nodes.clear()
em  = nodes.new("ShaderNodeEmission")
em.inputs["Color"].default_value = (0.18, 0.55, 0.86, 1.0)
em.inputs["Strength"].default_value = 1.0
out = nodes.new("ShaderNodeOutputMaterial")
links.new(em.outputs["Emission"], out.inputs["Surface"])
if not obj.data.materials:
    obj.data.materials.append(mat)
else:
    obj.data.materials[0] = mat

# ── camera ───────────────────────────────────────────────────────────────────
bpy.ops.object.camera_add()
cam_obj  = bpy.context.active_object
cam_data = cam_obj.data
cam_obj.location = (cx, cy, cz)

import mathutils
direction = mathutils.Vector((cx, cy, cz))  # from origin to camera
rot = (-direction).to_track_quat('-Z', 'Y')
cam_obj.rotation_euler = rot.to_euler()

cam_data.lens_unit = 'FOV'
cam_data.angle = math.radians(fov_deg)
scene.camera = cam_obj

bpy.ops.render.render(write_still=True)
"""


def render_from_position(
    obj_path: Path,
    cx: float, cy: float, cz: float,
    fov_deg: float,
    output_png: Path,
    resolution: int = 224,
    blender_bin: Path = Path("/Applications/Blender.app/Contents/MacOS/Blender"),
    log_path: Path | None = None,
) -> dict[str, object]:
    """Render a PNG from the given world-space camera position (looking at origin).

    Returns a diagnostic dict instead of a bare bool so Blender failures do not get
    collapsed into a silent "render FAILED" with no reason.
    """
    script_path = Path(tempfile.mktemp(suffix=".py"))
    script_path.write_text(BLENDER_RENDER_SCRIPT)
    command = [
        str(blender_bin), "--background", "--factory-startup",
        "--python", str(script_path),
        "--", str(obj_path), str(output_png),
        str(cx), str(cy), str(cz), str(fov_deg), str(resolution),
    ]
    try:
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            error_type = None
            error_message = ""
            if result.returncode != 0:
                error_type = "blender_nonzero_exit"
                error_message = f"Blender exited with return code {result.returncode}"
            render_info: dict[str, object] = {
                "ok": result.returncode == 0 and output_png.exists(),
                "returncode": result.returncode,
                "output_exists": output_png.exists(),
                "stdout": result.stdout,
                "stderr": result.stderr,
                "error_type": error_type,
                "error_message": error_message,
                "command": command,
            }
        except subprocess.TimeoutExpired as exc:
            render_info = {
                "ok": False,
                "returncode": None,
                "output_exists": output_png.exists(),
                "stdout": exc.stdout or "",
                "stderr": exc.stderr or "",
                "error_type": "timeout",
                "error_message": f"Blender render timed out after {exc.timeout}s",
                "command": command,
            }
        except FileNotFoundError as exc:
            render_info = {
                "ok": False,
                "returncode": None,
                "output_exists": output_png.exists(),
                "stdout": "",
                "stderr": "",
                "error_type": "missing_blender",
                "error_message": str(exc),
                "command": command,
            }
        if log_path is not None:
            log_text = [
                f"command: {shlex.join(command)}",
                f"ok: {render_info['ok']}",
                f"returncode: {render_info['returncode']}",
                f"output_exists: {render_info['output_exists']}",
                f"error_type: {render_info['error_type']}",
                f"error_message: {render_info['error_message']}",
                "",
                "stdout:",
                str(render_info["stdout"]),
                "",
                "stderr:",
                str(render_info["stderr"]),
            ]
            log_path.write_text("\n".join(log_text))
        return render_info
    finally:
        script_path.unlink(missing_ok=True)


# ── main ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Validate 3DVA GT viewpoint geometry via IoU.")
    p.add_argument("--model", required=True, help="Model name, e.g. bunny")
    p.add_argument(
        "--dataset-root", type=Path,
        default=Path(os.environ.get("VISUAL_ATTENTION_3D_SHAPES_ROOT",
                                    "e.g. /srv/datasets/3DVA")),
        help="Root of the 3DVA dataset (contains 3DModels-Simplif-up/).",
    )
    p.add_argument(
        "--gt-views-dir", type=Path,
        default=Path(os.environ.get("THREE_DVA_GT_VIEWS_DIR",
                                    "e.g. /srv/datasets/3DVA/3DModels-Simplif-224-up/views")),
        help="Directory with GT JPG renders: {model}_001.jpg etc.",
    )
    p.add_argument(
        "--test-viewpoints-dir", type=Path,
        default=Path(os.environ.get("THREE_DVA_TEST_VIEWPOINTS_DIR",
                                    "e.g. /srv/datasets/3DVA/test_viewpoints")),
        help="Directory with per-model viewpoint angle files: {model}.txt",
    )
    p.add_argument(
        "--output-dir", type=Path,
        default=Path("/tmp/gt_viewpoint_check"),
        help="Directory for rendered previews, overlays, and report JSON.",
    )
    p.add_argument(
        "--camera-radius", type=float, default=1.5,
        help="Orbital camera distance from origin (metres). Default 1.5.",
    )
    p.add_argument(
        "--fov-deg", type=float, default=60.0,
        help="Camera horizontal FOV in degrees. Default 60.",
    )
    p.add_argument(
        "--search-radius", action="store_true",
        help="Grid-search camera radius [0.8..3.0] to find best IoU.",
    )
    p.add_argument(
        "--search-fov", action="store_true",
        help="Also grid-search FOV [40..80] when --search-radius is set.",
    )
    p.add_argument(
        "--az-offset", type=float, default=180.0,
        help="Azimuth offset in degrees applied to test_viewpoints angles (default 180).",
    )
    p.add_argument(
        "--blender-bin", type=Path,
        default=Path("/Applications/Blender.app/Contents/MacOS/Blender"),
    )
    p.add_argument(
        "--resolution", type=int, default=224,
        help="Render resolution (square). Default 224 to match GT.",
    )
    return p.parse_args()


def _casefold_obj(dataset_root: Path, model: str) -> Path | None:
    d = dataset_root / "3DModels-Simplif-up"
    for f in d.glob("*.obj"):
        if f.stem.lower() == model.lower():
            return f
    return None


def main() -> None:
    args = parse_args()

    # ── resolve paths ─────────────────────────────────────────────────────────
    obj_path = _casefold_obj(args.dataset_root, args.model)
    if obj_path is None:
        raise SystemExit(f"OBJ not found for '{args.model}' in {args.dataset_root}/3DModels-Simplif-up")

    vp_file = args.test_viewpoints_dir / f"{args.model}.txt"
    if not vp_file.exists():
        # try case-insensitive
        for f in args.test_viewpoints_dir.glob("*.txt"):
            if f.stem.lower() == args.model.lower():
                vp_file = f
                break
    if not vp_file.exists():
        raise SystemExit(f"Viewpoints file not found: {vp_file}")

    # ── read viewpoints: each line = "azimuth elevation" ─────────────────────
    lines = [l.strip() for l in vp_file.read_text().splitlines() if l.strip()]
    viewpoints: list[tuple[float, float]] = []
    for line in lines:
        parts = line.split()
        viewpoints.append((float(parts[0]), float(parts[1])))
    print(f"[{args.model}] viewpoints: {viewpoints}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []

    radii_to_try = (
        [round(r, 2) for r in np.arange(0.8, 3.1, 0.2)]
        if args.search_radius else [args.camera_radius]
    )
    fovs_to_try = (
        [float(f) for f in range(40, 81, 5)]
        if (args.search_radius and args.search_fov) else [args.fov_deg]
    )

    for view_idx, (az, el) in enumerate(viewpoints):
        view_num = view_idx + 1
        gt_jpg = args.gt_views_dir / f"{args.model}_{view_num:03d}.jpg"
        if not gt_jpg.exists():
            # case-insensitive lookup
            for f in args.gt_views_dir.glob(f"*_{view_num:03d}.jpg"):
                if f.name.split("_")[0].lower() == args.model.lower():
                    gt_jpg = f
                    break
        if not gt_jpg.exists():
            print(f"  [view {view_num}] GT JPG missing: {gt_jpg}")
            continue

        gt_mask = extract_silhouette_from_gt_jpg(gt_jpg)
        view_out = args.output_dir / args.model / f"view_{view_num:03d}_az{int(az)}_el{int(el)}"
        view_out.mkdir(parents=True, exist_ok=True)

        # save GT mask for reference
        Image.open(gt_jpg).save(view_out / "gt.jpg")

        best_iou = -1.0
        best_r   = args.camera_radius
        best_fov = args.fov_deg
        best_png_path: Path | None = None
        best_log_path: Path | None = None
        failed_attempts: list[dict[str, object]] = []

        for radius in radii_to_try:
            for fov in fovs_to_try:
                png_path = view_out / f"preview_r{radius:.2f}_fov{fov:.0f}.png"
                log_path = view_out / f"preview_r{radius:.2f}_fov{fov:.0f}.log"
                cx, cy, cz = orbit_camera_position(az, el, radius, az_offset_deg=args.az_offset)
                render_info = render_from_position(
                    obj_path=obj_path,
                    cx=cx, cy=cy, cz=cz,
                    fov_deg=fov,
                    output_png=png_path,
                    resolution=args.resolution,
                    blender_bin=args.blender_bin,
                    log_path=log_path,
                )
                if not bool(render_info["ok"]):
                    failure = {
                        "radius": radius,
                        "fov": fov,
                        "returncode": render_info["returncode"],
                        "error_type": render_info["error_type"],
                        "error_message": render_info["error_message"],
                        "log_path": str(log_path),
                    }
                    failed_attempts.append(failure)
                    print(
                        f"  [view {view_num}] render FAILED "
                        f"(r={radius}, fov={fov}, rc={render_info['returncode']}, log={log_path})"
                    )
                    continue

                pred_mask = extract_silhouette_from_blender_png(png_path)
                score = iou(gt_mask, pred_mask)
                print(f"  [view {view_num}] az={az:.1f} el={el:.1f} R={radius:.2f} fov={fov:.0f}° → IoU={score:.4f}")

                if score > best_iou:
                    best_iou   = score
                    best_r     = radius
                    best_fov   = fov
                    best_png_path = png_path
                    best_log_path = log_path

        # ── overlay best result ───────────────────────────────────────────────
        if best_png_path is not None and best_png_path.exists():
            gt_img   = np.asarray(Image.open(gt_jpg).convert("RGB"))
            pred_img = np.asarray(Image.open(best_png_path).convert("RGB"))
            pred_sil = extract_silhouette_from_blender_png(best_png_path)

            # draw red contour of best prediction on GT image
            from PIL import ImageDraw
            from scipy.ndimage import binary_dilation, binary_erosion
            contour = binary_dilation(pred_sil, iterations=1) & ~binary_erosion(pred_sil, iterations=1)
            overlay = Image.fromarray(gt_img)
            draw = ImageDraw.Draw(overlay)
            ys, xs = np.nonzero(contour)
            for x, y in zip(xs.tolist(), ys.tolist()):
                draw.point((x, y), fill=(220, 20, 60))
            overlay.save(view_out / "overlay_best.png")
            shutil.copy(best_png_path, view_out / "best_preview.png")

        row = {
            "view":       view_num,
            "azimuth":    az,
            "elevation":  el,
            "best_iou":   round(best_iou, 4),
            "best_radius": best_r,
            "best_fov":   best_fov,
            "best_preview": str(best_png_path) if best_png_path is not None else None,
            "best_log":    str(best_log_path) if best_log_path is not None else (
                failed_attempts[-1]["log_path"] if failed_attempts else None
            ),
            "failed_attempt_count": len(failed_attempts),
            "failed_attempts": failed_attempts,
            "status":     "✅" if best_iou >= 0.85 else ("⚠️" if best_iou >= 0.70 else "❌"),
        }
        results.append(row)
        print(f"  → BEST [view {view_num}]: IoU={best_iou:.4f} R={best_r} fov={best_fov}°")

    # ── summary ───────────────────────────────────────────────────────────────
    report = {
        "model":    args.model,
        "obj_path": str(obj_path),
        "results":  results,
        "mean_iou": round(sum(r["best_iou"] for r in results) / max(len(results), 1), 4),
    }
    report_path = args.output_dir / args.model / "report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    print(f"\n{'='*60}")
    print(f"Model: {args.model}  |  Mean IoU: {report['mean_iou']:.4f}")
    for r in results:
        print(f"  {r['status']} view{r['view']} (az={r['azimuth']}, el={r['elevation']}): "
              f"IoU={r['best_iou']:.4f}  R={r['best_radius']}  fov={r['best_fov']}°")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
