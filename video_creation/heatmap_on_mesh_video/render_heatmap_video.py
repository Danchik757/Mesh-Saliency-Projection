#!/usr/bin/env python3
"""
Render per-frame heatmap-on-mesh video using object-placement JSON pose.

Produces:
  {output-dir}/{dataset}/{track}/{model}/{map-type}/heatmap_video.mp4
  {output-dir}/{dataset}/{track}/{model}/{map-type}/manifest.json
  {output-dir}/{dataset}/{track}/{model}/{map-type}/manifest.csv
  {output-dir}/{dataset}/{track}/{model}/{map-type}/preview_frame_*.png

Transform contract (blender_rig, canonical):
  recenter → scale → rotate_x(90°) → rotate_z(per-frame) → +location

Timing contracts:
  rc3_one_turn (default):
    start_idx = 0  (frame_offset=0, delay_seconds=0.0)
    end_idx   = TURN_FRAMES[dataset]  (450 for 3DVA/MeshMamba, 660 for SAL3D)
  rc2_cropped (legacy):
    start_idx = round(1.8 * fps)   # = 54
    end_idx   = total_frames - round(0.2 * fps)

Usage:
  python render_heatmap_video.py \\
    --dataset meshmamba --texture-type non_texture --model Starfruit_L3 \\
    --map-type screen_space \\
    --map-path /path/to/Starfruit_L3_screen_space_faces.txt \\
    --mesh /path/to/Starfruit_L3.obj \\
    --placement-json jsons/object_placement/mamba_non_jsons/MeshMamba_non_texture_Starfruit_L3.json \\
    --output-dir /tmp/heatmap_videos \\
    --max-frames 120 --alpha 0.8 --colormap jet

  # Auto-resolve OBJ and placement JSON from dataset roots:
  python render_heatmap_video.py \\
    --dataset meshmamba --texture-type non_texture --model Starfruit_L3 \\
    --map-type screen_space --map-path /path/to/map.txt \\
    --dataset-root /data/MeshMambaSaliency \\
    --json-root jsons/object_placement \\
    --output-dir /tmp/heatmap_videos --max-frames 120
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

# matplotlib is available in the test environment; import eagerly so
# compute_rgb_colors works in tests (pyvista/PIL are not needed for pure-logic).
import matplotlib
matplotlib.use("Agg")
from matplotlib import colormaps as _mpl_colormaps


def _get_cmap(name: str):
    return _mpl_colormaps[name]

# Heavy rendering deps (pyvista, PIL) — lazy so py_compile and pure-logic tests
# work without a display or GPU.
_import_error: Exception | None = None
try:
    import pyvista as pv
    from PIL import Image
except ImportError as _exc:
    _import_error = _exc

# ── timing ────────────────────────────────────────────────────────────────────

# rc2 legacy constants (kept for backward-compat with existing tests/callers)
CROP_START_S = 1.8
CROP_END_S   = 0.2

# rc3 one-turn-from-start timing: frames per dataset turn
TURN_FRAMES: dict[str, int] = {
    "3dva":       450,
    "meshmamba":  450,
    "sal3d":      660,
}

# Canonical dataset names for output paths / manifest
_DATASET_CANONICAL: dict[str, str] = {
    "3dva":      "3DVA",
    "meshmamba": "MeshMamba",
    "sal3d":     "SAL3D",
}

# Per-dataset X-rotation applied to OBJ vertices to match Blender import convention.
# 3DVA render script imports OBJ with up_axis='Z' (already Z-up) → no extra X rotation.
# MeshMamba/SAL3D use default Y-up OBJ import → Blender applies rotX(90°) internally.
# Matches evaluator defaults: eval_3dva_raycast_cone default=0°, eval_sal3d/meshmamba default=90°.
_DATASET_EXTRA_ROTATE_X: dict[str, float] = {
    "3dva":      0.0,
    "meshmamba": 90.0,
    "sal3d":     90.0,
}


def resolve_frame_window(
    dataset: str,
    fps: int,
    total_frames: int,
    *,
    timing_contract: str = "rc3_one_turn",
    max_frames: int | None = None,
) -> tuple[int, int]:
    """Return (start_idx, end_idx) for frame iteration.

    rc3_one_turn: start=0, end=TURN_FRAMES[dataset] (capped at total_frames).
    rc2_cropped:  start=round(1.8*fps), end=total_frames-round(0.2*fps).
    """
    dataset_lc = dataset.lower()
    if timing_contract == "rc3_one_turn":
        start_idx = 0
        turn = TURN_FRAMES.get(dataset_lc)
        if turn is None:
            raise ValueError(
                f"Unknown dataset for rc3 timing: {dataset!r}. "
                f"Known: {list(TURN_FRAMES.keys())}"
            )
        end_idx = min(turn, total_frames)
    elif timing_contract == "rc2_cropped":
        start_idx = round(CROP_START_S * fps)
        end_idx = total_frames - round(CROP_END_S * fps)
    else:
        raise ValueError(f"Unknown timing_contract: {timing_contract!r}")

    if max_frames is not None:
        end_idx = min(end_idx, start_idx + max_frames)
    if end_idx <= start_idx:
        raise ValueError(
            f"Empty frame window: start={start_idx} end={end_idx} "
            f"(total_frames={total_frames}, timing={timing_contract})"
        )
    return start_idx, end_idx


# ── preview frame selection ───────────────────────────────────────────────────

def select_preview_indices(n_frames: int) -> list[int]:
    """Return sorted frame indices for preview PNGs: 0, 25%, 50%, 75%, last."""
    if n_frames <= 0:
        return []
    idxs = {
        0,
        n_frames // 4,
        n_frames // 2,
        3 * n_frames // 4,
        n_frames - 1,
    }
    return sorted(idxs)


# ── OBJ ──────────────────────────────────────────────────────────────────────

def parse_obj(path: Path) -> tuple[np.ndarray, np.ndarray]:
    vertices: list[list[float]] = []
    faces: list[list[int]] = []
    with open(path) as fh:
        for line in fh:
            if line.startswith("v "):
                p = line.split()
                vertices.append([float(p[1]), float(p[2]), float(p[3])])
            elif line.startswith("f "):
                p = line.split()
                faces.append([int(t.split("/")[0]) - 1 for t in p[1:4]])
    return np.array(vertices, dtype=np.float64), np.array(faces, dtype=np.int32)


# ── path auto-resolution ─────────────────────────────────────────────────────

def _casefold_find(directory: Path, stem: str, suffix: str) -> Path | None:
    if not directory.is_dir():
        return None
    target = stem.lower()
    for f in directory.iterdir():
        if f.suffix.lower() == suffix and f.stem.lower() == target:
            return f
    return None


def _casefold_find_nested(directory: Path, stem: str, suffix: str) -> Path | None:
    """Like _casefold_find but also checks a model-named subdirectory.

    Handles MeshMamba layout: MeshFile/{tt}/{model}/{obj_stem}.obj
    where obj_stem may differ from model (dash vs underscore, short stems).
    """
    direct = _casefold_find(directory, stem, suffix)
    if direct is not None:
        return direct
    if not directory.is_dir():
        return None
    stem_norm = stem.lower().replace("_", "").replace("-", "")
    for d in directory.iterdir():
        if not d.is_dir() or d.name.lower().replace("_", "").replace("-", "") != stem_norm:
            continue
        nested = _casefold_find(d, stem, suffix)
        if nested is not None:
            return nested
        wanted = stem.lower().replace("_", "").replace("-", "")
        candidates = sorted(d.glob(f"*{suffix}"))
        for f in candidates:
            if f.stem.lower().replace("_", "").replace("-", "") == wanted:
                return f
        if len(candidates) == 1:
            return candidates[0]
    return None


def auto_resolve_obj(
    dataset: str, texture_type: str, model: str, dataset_root: Path
) -> Path:
    """Construct OBJ path from dataset root using per-dataset conventions."""
    ds = dataset.lower()
    if ds == "3dva":
        candidate = _casefold_find(dataset_root / "3DModels-Simplif-up", model, ".obj")
    elif ds == "meshmamba":
        candidate = _casefold_find_nested(dataset_root / "MeshFile" / texture_type, model, ".obj")
    elif ds == "sal3d":
        candidate = _casefold_find(dataset_root / "Meshes", model, ".obj")
    else:
        raise ValueError(f"Unknown dataset for OBJ auto-resolve: {dataset!r}")
    if candidate is None:
        raise FileNotFoundError(
            f"OBJ not found for model '{model}' (dataset={dataset}, "
            f"texture_type={texture_type}) under {dataset_root}"
        )
    return candidate


def auto_resolve_placement_json(
    dataset: str, texture_type: str, model: str, json_root: Path
) -> Path:
    """Construct placement JSON path from json_root using per-dataset conventions."""
    ds = dataset.lower()
    if ds == "3dva":
        path = json_root / "3dva_jsons" / f"3DVA_{model}.json"
    elif ds == "meshmamba":
        if texture_type == "non_texture":
            path = json_root / "mamba_non_jsons" / f"MeshMamba_non_texture_{model}.json"
        else:
            path = json_root / "mamba_rgb_jsons" / f"MeshMamba_rgb_texture_{model}.json"
    elif ds == "sal3d":
        # Files on disk use "Sal3D_" prefix (mixed-case), not "SAL3D_"
        path = json_root / "sal3d_jsons" / f"Sal3D_{model}.json"
    else:
        raise ValueError(f"Unknown dataset for placement JSON auto-resolve: {dataset!r}")
    if not path.exists():
        raise FileNotFoundError(f"Placement JSON not found: {path}")
    return path


# ── map loading ───────────────────────────────────────────────────────────────

def load_map(
    path: Path,
    n_vertices: int,
    n_faces: int,
    gt_column: int | None = None,
) -> tuple[np.ndarray, str]:
    """Load saliency map; auto-detect domain.

    Returns (values, domain) where domain is 'vertex' or 'face'.
    For multi-column files (e.g. SAL3D Gaze .txt) use gt_column (default 7).
    """
    raw = np.loadtxt(str(path), dtype=np.float64)
    if raw.ndim == 2:
        col = gt_column if gt_column is not None else 7
        raw = raw[:, col]
    n = len(raw)
    if n == n_faces:
        return raw, "face"
    if n == n_vertices:
        return raw, "vertex"
    raise ValueError(
        f"Map length {n} matches neither n_faces={n_faces} nor n_vertices={n_vertices}. "
        f"File: {path}"
    )


# ── transforms ────────────────────────────────────────────────────────────────

def _rotate_x(v: np.ndarray, deg: float) -> np.ndarray:
    rad = math.radians(deg)
    c, s = math.cos(rad), math.sin(rad)
    out = v.copy()
    out[:, 1] = c * v[:, 1] - s * v[:, 2]
    out[:, 2] = s * v[:, 1] + c * v[:, 2]
    return out


def _rotate_z(v: np.ndarray, rad: float) -> np.ndarray:
    c, s = math.cos(rad), math.sin(rad)
    out = v.copy()
    out[:, 0] = c * v[:, 0] - s * v[:, 1]
    out[:, 1] = s * v[:, 0] + c * v[:, 1]
    return out


def precompute_base_transform(
    vertices: np.ndarray,
    placement: dict,
    *,
    recenter: bool = True,
    extra_rotate_x_deg: float = 90.0,
) -> np.ndarray:
    """Apply static transforms (recenter, scale, X-rot). Returns base vertices
    ready for per-frame Z rotation via apply_frame_rotation().

    model_static.location is NOT applied here; it must be added after the
    per-frame rotation to match the evaluator blender_rig transform order:
      recenter → scale → rotX → rotZ(frame) → +location
    """
    v = vertices.copy()
    if recenter:
        bbox_center = 0.5 * (v.min(axis=0) + v.max(axis=0))
        v -= bbox_center
    scale = np.asarray(placement["model_static"]["scale"], dtype=np.float64)
    v *= scale
    if abs(extra_rotate_x_deg) > 1e-9:
        v = _rotate_x(v, extra_rotate_x_deg)
    return v


def apply_frame_rotation(base_verts: np.ndarray, rotation_z_rad: float) -> np.ndarray:
    if abs(rotation_z_rad) <= 1e-12:
        return base_verts
    return _rotate_z(base_verts, rotation_z_rad)


# ── camera ────────────────────────────────────────────────────────────────────

def camera_from_placement(
    placement: dict,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """Return (position, focal_point, up, vert_fov_deg) from placement JSON.

    Decomposes view_matrix to recover exact Blender camera position and
    orientation. Converts horizontal FOV (60°) to vertical for PyVista.
    """
    cam = placement["camera_static"]
    V = np.array(cam["view_matrix"], dtype=np.float64).reshape(4, 4)
    R, t = V[:3, :3], V[:3, 3]

    position = (-R.T @ t)
    up = (R.T @ np.array([0.0, 1.0, 0.0]))

    focal_point = np.asarray(placement["model_static"]["location"], dtype=np.float64)

    vi = placement["video_info"]
    aspect = vi["resolution_width"] / vi["resolution_height"]
    horiz_fov_rad = math.radians(cam["fov_degrees"])
    vert_fov_deg = math.degrees(
        2.0 * math.atan(math.tan(horiz_fov_rad / 2.0) / aspect)
    )
    return position, focal_point, up, vert_fov_deg


# ── colormap blending ──────────────────────────────────────────────────────────

def compute_rgb_colors(
    values: np.ndarray,
    domain: str,
    *,
    colormap: str = "jet",
    alpha: float = 1.0,
) -> tuple[np.ndarray, str, dict]:
    """Map saliency values to blended RGB (uint8).

    alpha=1.0 → pure heatmap; alpha=0.0 → neutral gray.
    Constant-value maps normalize to all-zero (cold end of colormap) with a warning.
    Returns (rgb (N,3) uint8, pv_domain, norm_stats) where:
      pv_domain is 'cell' or 'point'
      norm_stats is {"input_min", "input_max", "display_normalization"}
    Metric values are NOT modified — normalization is display-only.
    """
    cmap = _get_cmap(colormap)
    vmin, vmax = float(values.min()), float(values.max())
    if vmax - vmin < 1e-12:
        print(
            f"[WARN] constant saliency map detected (all values ≈ {vmin:.6g}); "
            "normalizing to zero — heatmap will show cold-end color only.",
            file=sys.stderr,
        )
        normalized = np.zeros(len(values))
    else:
        normalized = (values - vmin) / (vmax - vmin)

    rgba = cmap(normalized)
    heatmap_rgb = rgba[:, :3]
    gray = np.full_like(heatmap_rgb, 0.5)
    blended = alpha * heatmap_rgb + (1.0 - alpha) * gray
    rgb_u8 = (np.clip(blended, 0.0, 1.0) * 255).astype(np.uint8)

    pv_domain = "cell" if domain == "face" else "point"
    norm_stats = {
        "input_min": vmin,
        "input_max": vmax,
        "display_normalization": "minmax_per_map",
    }
    return rgb_u8, pv_domain, norm_stats


# ── PyVista mesh ───────────────────────────────────────────────────────────────

def build_poly(vertices: np.ndarray, faces: np.ndarray) -> "pv.PolyData":
    pv_faces = np.hstack([
        np.full((len(faces), 1), 3, dtype=np.int32),
        faces.astype(np.int32),
    ])
    return pv.PolyData(vertices.astype(np.float32), pv_faces.ravel())


# ── frame rendering ───────────────────────────────────────────────────────────

def render_frames(
    base_verts: np.ndarray,
    faces: np.ndarray,
    frame_rotations: list[float],
    rgb_colors: np.ndarray,
    pv_domain: str,
    camera_params: tuple,
    frames_dir: Path,
    width: int,
    height: int,
    model_location: np.ndarray | None = None,
    background_color: str = "white",
) -> list[Path]:
    """Render frames off-screen. Reuses a single Plotter with in-place point updates.

    model_location is added after per-frame rotation, matching the evaluator
    blender_rig transform order (location is the final translation step).
    background_color is passed directly to PyVista (e.g. "white", "black").
    """
    os.environ.setdefault("DISPLAY", "")
    pv.OFF_SCREEN = True

    position, focal_point, up, vert_fov_deg = camera_params
    loc = model_location if model_location is not None else np.zeros(3)

    init_verts = apply_frame_rotation(base_verts, frame_rotations[0]) + loc
    mesh_poly = build_poly(init_verts, faces)
    if pv_domain == "cell":
        mesh_poly.cell_data["color"] = rgb_colors
    else:
        mesh_poly.point_data["color"] = rgb_colors

    pl = pv.Plotter(off_screen=True, window_size=(width, height))
    pl.set_background(background_color)
    pl.add_mesh(
        mesh_poly,
        scalars="color",
        rgb=True,
        show_scalar_bar=False,
        smooth_shading=False,
        preference=pv_domain,
    )
    pl.camera.position = position.tolist()
    pl.camera.focal_point = focal_point.tolist()
    pl.camera.up = up.tolist()
    pl.camera.view_angle = vert_fov_deg

    png_paths: list[Path] = []
    n = len(frame_rotations)
    for i, rot_rad in enumerate(frame_rotations):
        rotated = apply_frame_rotation(base_verts, rot_rad) + loc
        mesh_poly.points = rotated.astype(np.float32)
        pl.render()
        img = pl.screenshot(return_img=True)
        p = frames_dir / f"frame_{i:05d}.png"
        Image.fromarray(img).save(str(p))
        png_paths.append(p)
        if (i + 1) % 50 == 0 or i == n - 1:
            print(f"  frame {i+1}/{n}", flush=True)

    pl.close()
    return png_paths


# ── video assembly ────────────────────────────────────────────────────────────

def frames_to_mp4(frames_dir: Path, output_mp4: Path, fps: int) -> None:
    ffmpeg = shutil.which("ffmpeg") or str(Path.home() / ".local/bin/ffmpeg")
    if not Path(ffmpeg).exists() and not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found on PATH — cannot assemble video")
    cmd = [
        ffmpeg, "-y",
        "-framerate", str(fps),
        "-i", str(frames_dir / "frame_%05d.png"),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "medium",
        "-crf", "18",
        str(output_mp4),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{result.stderr[-2000:]}")


# ── GPU preflight ─────────────────────────────────────────────────────────────

# Renderer strings that indicate CPU software rasterization.
_CPU_RENDERER_PATTERNS = ("llvmpipe", "softpipe", "mesa software", "virtualbox", "vmware")

# Minimum frame cap when running on CPU fallback.
_CPU_FALLBACK_MAX_FRAMES = 30

# Probe script run in a subprocess so vtkRenderWindow.Initialize() — which can
# call exit() on headless systems — never runs inside the main Python process.
_VTK_PROBE_SCRIPT = """\
import json, platform

try:
    import vtk as _vtk
    rw = _vtk.vtkRenderWindow()
    rw.SetOffScreenRendering(1)
    rw.Initialize()
    rw.AddRenderer(_vtk.vtkRenderer())
    rw.Render()
    vendor = renderer = version = "unknown"
    try:
        import ctypes, ctypes.util
        lib_names = {"Darwin": ["OpenGL"], "Windows": ["opengl32"]}.get(
            platform.system(), ["GL", "libGL.so.1"]
        )
        for _n in lib_names:
            _pt = ctypes.util.find_library(_n)
            if not _pt:
                continue
            try:
                lib = ctypes.CDLL(_pt)
                lib.glGetString.restype = ctypes.c_char_p
                def _gl(e):
                    v = lib.glGetString(e)
                    return v.decode() if v else "unknown"
                vendor = _gl(0x1F00)
                renderer = _gl(0x1F01)
                version = _gl(0x1F02)
                break
            except Exception:
                pass
    except Exception as ge:
        renderer = "ctypes-error:" + str(ge)
    finally:
        try:
            rw.Finalize()
        except Exception:
            pass
    print(json.dumps({"ok": True, "vendor": vendor, "renderer": renderer, "version": version}))
except Exception as exc:
    print(json.dumps({"ok": False, "error": str(exc)}))
"""


def probe_gpu_backend() -> dict:
    """Probe the OpenGL/VTK backend and return a preflight result dict.

    Sets GALLIUM_DRIVER=d3d12 / MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA before
    VTK initialises its render context so WSL's Mesa D3D12 bridge uses the
    physical GPU instead of llvmpipe.

    Returns a dict with keys:
      gpu_available        bool  — True if nvidia-smi found a GPU
      opengl_renderer      str   — GL_RENDERER string (or error message)
      opengl_vendor        str   — GL_VENDOR string
      opengl_version       str   — GL_VERSION string
      pyvista_version      str
      vtk_version          str
      pyvista_backend      str   — "d3d12_gpu" | "cpu_software" | "unknown"
      offscreen_backend    str   — "vtk_offscreen" | "error:<msg>"
      used_cpu_fallback    bool  — True when renderer matches a software rasterizer
    """
    # ── 1. nvidia-smi ──────────────────────────────────────────────────────────
    gpu_available = False
    gpu_name = ""
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0 and r.stdout.strip():
            gpu_available = True
            gpu_name = r.stdout.strip().splitlines()[0]
    except Exception:
        pass

    # ── 2. Steer Mesa to D3D12 backend (WSL) and build subprocess env ─────────
    # Set in the current process so later pv.Plotter() picks it up; also pass
    # to the probe subprocess so VTK inside it uses the same driver.
    if gpu_available and "GALLIUM_DRIVER" not in os.environ:
        os.environ["GALLIUM_DRIVER"] = "d3d12"
        os.environ.setdefault("MESA_D3D12_DEFAULT_ADAPTER_NAME", "NVIDIA")
    probe_env = os.environ.copy()

    # ── 3. Run VTK probe in an isolated subprocess ────────────────────────────
    # vtkRenderWindow.Initialize() can call exit() on headless systems.
    # Subprocess isolation prevents that from aborting the caller (pytest).
    opengl_renderer = "unknown"
    opengl_vendor   = "unknown"
    opengl_version  = "unknown"
    offscreen_backend = "vtk_offscreen"
    try:
        probe = subprocess.run(
            [sys.executable, "-c", _VTK_PROBE_SCRIPT],
            capture_output=True, text=True, timeout=20,
            env=probe_env,
        )
        last_line = (probe.stdout or "").strip().rsplit("\n", 1)[-1]
        if probe.returncode == 0 and last_line.startswith("{"):
            data = json.loads(last_line)
            if data.get("ok"):
                opengl_vendor   = data.get("vendor",   "unknown")
                opengl_renderer = data.get("renderer", "unknown")
                opengl_version  = data.get("version",  "unknown")
            else:
                offscreen_backend = "error:" + str(data.get("error", "unknown"))
        elif probe.returncode != 0:
            offscreen_backend = f"error:probe_exit_{probe.returncode}"
        else:
            offscreen_backend = "error:probe_no_output"
    except subprocess.TimeoutExpired:
        offscreen_backend = "error:vtk_probe_timeout"
    except Exception as exc:
        offscreen_backend = f"error:{exc}"

    # ── 4. Classify backend ────────────────────────────────────────────────────
    renderer_lc = opengl_renderer.lower()
    used_cpu_fallback = any(p in renderer_lc for p in _CPU_RENDERER_PATTERNS)
    if used_cpu_fallback:
        pyvista_backend = "cpu_software"
    elif "d3d12" in renderer_lc or (gpu_available and not used_cpu_fallback):
        pyvista_backend = "d3d12_gpu"
    else:
        pyvista_backend = "unknown"

    pyvista_ver = vtk_ver = "not_installed"
    try:
        import pyvista as _pv
        pyvista_ver = _pv.__version__
    except ImportError:
        pass
    try:
        import vtk as _vtk2
        vtk_ver = _vtk2.vtkVersion.GetVTKVersion()
    except ImportError:
        pass

    return {
        "gpu_available":     gpu_available,
        "gpu_name":          gpu_name,
        "opengl_renderer":   opengl_renderer,
        "opengl_vendor":     opengl_vendor,
        "opengl_version":    opengl_version,
        "pyvista_version":   pyvista_ver,
        "vtk_version":       vtk_ver,
        "pyvista_backend":   pyvista_backend,
        "offscreen_backend": offscreen_backend,
        "used_cpu_fallback": used_cpu_fallback,
    }


# ── manifest ──────────────────────────────────────────────────────────────────

def write_manifest(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2)


def write_manifest_csv(path: Path, manifest: dict) -> None:
    """Flatten nested manifest dict to a single CSV row."""
    flat: dict[str, object] = {}
    for k, v in manifest.items():
        if isinstance(v, dict):
            for kk, vv in v.items():
                flat[f"{k}.{kk}"] = vv
        else:
            flat[k] = v
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(flat.keys()))
        writer.writeheader()
        writer.writerow(flat)


# ── CLI ───────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Render per-frame heatmap-on-mesh video from placement JSON (rc3)."
    )
    ap.add_argument("--dataset", required=True,
                    choices=["3dva", "meshmamba", "sal3d"],
                    help="Dataset: 3dva, meshmamba, or sal3d (case-insensitive)")
    ap.add_argument("--texture-type", default="",
                    choices=["", "non_texture", "rgb_texture"],
                    dest="texture_type",
                    help="Texture track for MeshMamba (non_texture or rgb_texture)")
    ap.add_argument("--track", default=None,
                    help="Alias for --texture-type (legacy; overridden by --texture-type)")
    ap.add_argument("--model", required=True, help="Model name")
    ap.add_argument("--map-type", required=True,
                    choices=["screen_space", "cone", "gt"],
                    help="Heatmap source type")
    ap.add_argument("--map-path", "--map-file", type=Path, required=True,
                    dest="map_path",
                    help="Per-face or per-vertex saliency .txt file")
    ap.add_argument("--mesh", type=Path, default=None,
                    help="OBJ mesh file (explicit). If omitted, auto-resolved from --dataset-root.")
    ap.add_argument("--placement-json", type=Path, default=None,
                    help="Placement JSON (explicit). If omitted, auto-resolved from --json-root.")
    ap.add_argument("--dataset-root", type=Path, default=None,
                    help="Dataset root for auto-resolving OBJ path")
    ap.add_argument("--json-root", type=Path, default=Path("jsons/object_placement"),
                    help="Root containing {3dva,mamba_non,mamba_rgb,sal3d}_jsons/ dirs "
                         "(default: jsons/object_placement)")
    ap.add_argument("--output-dir", "--output-root", type=Path, required=True,
                    dest="output_dir",
                    help="Output root directory")
    ap.add_argument("--timing-contract",
                    choices=["rc3_one_turn", "rc2_cropped"],
                    default="rc3_one_turn",
                    help="Timing contract (default: rc3_one_turn = first 450/660 frames from 0)")
    ap.add_argument("--fps", type=int, default=None,
                    help="Output FPS (default: from placement JSON)")
    ap.add_argument("--alpha", type=float, default=1.0,
                    help="Heatmap opacity [0,1]; blends with neutral gray (default: 1.0)")
    ap.add_argument("--colormap", default="jet",
                    help="Matplotlib colormap (default: jet)")
    ap.add_argument("--max-frames", type=int, default=None,
                    help="Limit to first N frames (use ≤120 for smoke tests)")
    ap.add_argument("--full-turn", action="store_true",
                    help="Render a complete turn (450 frames for 3DVA/MeshMamba, 660 for SAL3D). "
                         "Equivalent to --allow-full-batch with no --max-frames cap. "
                         "--max-frames still applies as an additional upper bound if provided.")
    ap.add_argument("--width", type=int, default=960)
    ap.add_argument("--height", type=int, default=540)
    ap.add_argument("--extra-rotate-x-deg", type=float, default=None,
                    dest="extra_rotate_x_deg",
                    help="Extra X rotation (degrees) applied to OBJ vertices before per-frame Z rotation. "
                         "Auto-selected per dataset when omitted: 3DVA=0°, SAL3D/MeshMamba=90°. "
                         "Matches evaluator blender_rig conventions.")
    ap.add_argument("--gt-column", type=int, default=None,
                    help="Column index in multi-column GT file (SAL3D default: 7)")
    ap.add_argument("--keep-frames", action="store_true",
                    help="Keep individual PNG frames after video assembly")
    ap.add_argument("--background-color", default="white",
                    dest="background_color",
                    help="PyVista background color (default: white)")
    ap.add_argument("--object-base-color", default="lightgray",
                    dest="object_base_color",
                    help="Base mesh color when no heatmap is applied (default: lightgray; "
                         "currently unused — heatmap always covers the mesh)")
    ap.add_argument("--show-axes", action="store_true", default=False,
                    dest="show_axes",
                    help="Show PyVista axes widget (default: off)")
    ap.add_argument("--allow-full-batch", action="store_true",
                    help="Allow rendering more than 120 frames (requires explicit approval). "
                         "Without this flag, renders are capped: 30 frames (CPU) or 120 frames (GPU). "
                         "Implied by --full-turn.")
    ap.add_argument("--map-provenance-note", default="",
                    dest="map_provenance_note",
                    help="Free-text provenance label written to manifest.render.map_provenance_note. "
                         "Use to distinguish rc3_full_metrics maps from pilot/geodesic smoke maps.")
    ap.add_argument("--skip-gpu-preflight", action="store_true",
                    help="Skip GPU backend probe (for automated testing only)")
    return ap


def main() -> None:
    if _import_error:
        print(f"[ERROR] Missing rendering dependency: {_import_error}", file=sys.stderr)
        sys.exit(1)

    args = build_parser().parse_args()

    # ── GPU preflight ──────────────────────────────────────────────────────────
    if args.skip_gpu_preflight:
        gpu_info: dict = {
            "gpu_available": False, "gpu_name": "",
            "opengl_renderer": "skipped", "opengl_vendor": "skipped",
            "opengl_version": "skipped", "pyvista_version": "skipped",
            "vtk_version": "skipped", "pyvista_backend": "skipped",
            "offscreen_backend": "skipped", "used_cpu_fallback": False,
        }
    else:
        print("[INFO] running GPU backend preflight ...", flush=True)
        gpu_info = probe_gpu_backend()
        print(
            f"[INFO] renderer={gpu_info['opengl_renderer']!r}  "
            f"backend={gpu_info['pyvista_backend']}  "
            f"cpu_fallback={gpu_info['used_cpu_fallback']}",
            flush=True,
        )

    # ── Smoke / batch frame-count guard ───────────────────────────────────────
    # --full-turn implies allow_full_batch; max_frames is set to TURN_FRAMES[dataset]
    # (respecting an explicit --max-frames as an upper cap).
    if args.full_turn:
        args.allow_full_batch = True
        ds_lc = args.dataset.lower()
        if ds_lc not in TURN_FRAMES:
            print(f"[ERROR] --full-turn: unknown dataset {args.dataset!r}. "
                  f"Known: {list(TURN_FRAMES.keys())}", file=sys.stderr)
            sys.exit(1)
        full_turn_frames = TURN_FRAMES[ds_lc]
        if args.max_frames is None:
            args.max_frames = full_turn_frames
        else:
            args.max_frames = min(args.max_frames, full_turn_frames)
        print(
            f"[INFO] --full-turn: dataset={args.dataset}, turn={full_turn_frames} frames, "
            f"effective max_frames={args.max_frames}",
            flush=True,
        )

    if not args.allow_full_batch:
        smoke_cap = _CPU_FALLBACK_MAX_FRAMES if gpu_info["used_cpu_fallback"] else 120
        if args.max_frames is None or args.max_frames > smoke_cap:
            if args.max_frames is None:
                print(
                    f"[GUARD] --allow-full-batch not set. "
                    f"Capping to {smoke_cap} frames "
                    f"({'CPU fallback' if gpu_info['used_cpu_fallback'] else 'GPU smoke limit'}). "
                    f"Pass --allow-full-batch for full render.",
                    flush=True,
                )
            else:
                print(
                    f"[GUARD] --max-frames {args.max_frames} exceeds smoke cap {smoke_cap}. "
                    f"Capping. Pass --allow-full-batch to override.",
                    flush=True,
                )
            args.max_frames = smoke_cap

    if gpu_info.get("used_cpu_fallback") and args.allow_full_batch:
        print(
            "[WARN] CPU software rasterizer detected (llvmpipe/softpipe). "
            "Full batch allowed by --allow-full-batch but will be very slow. "
            "Notify reviewer/controller before proceeding.",
            file=sys.stderr,
        )

    # Resolve texture_type: --texture-type takes precedence over --track
    texture_type = args.texture_type or (args.track or "")

    # Validate MeshMamba requires texture_type
    if args.dataset.lower() == "meshmamba" and not texture_type:
        print("[ERROR] --texture-type is required for dataset=meshmamba", file=sys.stderr)
        sys.exit(1)

    # Resolve OBJ path
    if args.mesh is not None:
        mesh_path = args.mesh
    elif args.dataset_root is not None:
        mesh_path = auto_resolve_obj(args.dataset, texture_type, args.model, args.dataset_root)
    else:
        print("[ERROR] Provide --mesh or --dataset-root to locate the OBJ file.", file=sys.stderr)
        sys.exit(1)

    # Resolve placement JSON path
    if args.placement_json is not None:
        placement_path = args.placement_json
    else:
        placement_path = auto_resolve_placement_json(
            args.dataset, texture_type, args.model, args.json_root
        )

    for p, name in [
        (args.map_path, "--map-path"),
        (mesh_path, "--mesh / --dataset-root"),
        (placement_path, "--placement-json / --json-root"),
    ]:
        if not p.exists():
            print(f"[ERROR] {name} not found: {p}", file=sys.stderr)
            sys.exit(1)

    placement = json.loads(placement_path.read_text())
    vi = placement["video_info"]
    fps = args.fps or vi["fps"]
    total_frames = vi["total_frames"]
    frames_list = placement["frames"]

    start_idx, end_idx = resolve_frame_window(
        args.dataset, fps, total_frames,
        timing_contract=args.timing_contract,
        max_frames=args.max_frames,
    )
    n_frames = end_idx - start_idx
    print(
        f"[INFO] timing={args.timing_contract}  "
        f"window=[{start_idx},{end_idx})  n_frames={n_frames}  fps={fps}",
        flush=True,
    )

    frame_rotations = [frames_list[i]["rotation_z_radians"] for i in range(start_idx, end_idx)]

    print(f"[INFO] loading mesh: {mesh_path}", flush=True)
    vertices, faces = parse_obj(mesh_path)
    n_vertices, n_faces = len(vertices), len(faces)
    print(f"[INFO] mesh: {n_vertices} vertices, {n_faces} faces", flush=True)

    print(f"[INFO] loading map: {args.map_path}", flush=True)
    values, map_domain = load_map(
        args.map_path, n_vertices, n_faces, gt_column=args.gt_column
    )
    print(f"[INFO] map: {len(values)} elements, domain={map_domain}", flush=True)

    # Per-dataset X-rotation: auto-select from table unless overridden by CLI flag.
    ds_lc_for_rot = args.dataset.lower()
    extra_rot_x = (
        args.extra_rotate_x_deg
        if args.extra_rotate_x_deg is not None
        else _DATASET_EXTRA_ROTATE_X.get(ds_lc_for_rot, 90.0)
    )
    print(f"[INFO] extra_rotate_x_deg={extra_rot_x} (dataset={args.dataset})", flush=True)
    base_verts = precompute_base_transform(vertices, placement, extra_rotate_x_deg=extra_rot_x)
    model_location = np.asarray(placement["model_static"]["location"], dtype=np.float64)
    rgb_colors, pv_domain, norm_stats = compute_rgb_colors(
        values, map_domain, colormap=args.colormap, alpha=args.alpha
    )
    camera_params = camera_from_placement(placement)
    pos, fp, up, vfov = camera_params
    print(f"[INFO] camera: pos={pos.tolist()}, focal={fp.tolist()}, vfov={vfov:.2f}°", flush=True)

    canonical_ds = _DATASET_CANONICAL.get(args.dataset.lower(), args.dataset)
    out_subdir = args.output_dir / canonical_ds / texture_type / args.model / args.map_type
    if not texture_type:
        out_subdir = args.output_dir / canonical_ds / args.model / args.map_type
    out_subdir.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] rendering {n_frames} frames ({args.width}×{args.height}) ...", flush=True)
    with tempfile.TemporaryDirectory(prefix="heatmap_frames_") as tmpdir:
        tmp_path = Path(tmpdir)
        png_paths = render_frames(
            base_verts, faces, frame_rotations,
            rgb_colors, pv_domain, camera_params,
            tmp_path, args.width, args.height,
            model_location=model_location,
            background_color=args.background_color,
        )

        # Save preview PNGs before temp dir cleanup
        preview_indices = select_preview_indices(len(png_paths))
        for idx in preview_indices:
            src = png_paths[idx]
            dst = out_subdir / f"preview_frame_{idx:05d}.png"
            shutil.copy(src, dst)
        print(f"[INFO] saved {len(preview_indices)} preview PNGs", flush=True)

        if args.keep_frames:
            frames_out = out_subdir / "frames"
            frames_out.mkdir(exist_ok=True)
            for p in png_paths:
                shutil.copy(p, frames_out / p.name)

        mp4_path = out_subdir / "heatmap_video.mp4"
        print(f"[INFO] assembling video: {mp4_path}", flush=True)
        frames_to_mp4(tmp_path, mp4_path, fps)

    pos_arr, fp_arr, up_arr, vfov_val = camera_params
    manifest_data = {
        "dataset":        canonical_ds,
        "texture_type":   texture_type,
        "model":          args.model,
        "map_type":       args.map_type,
        "map_file":       str(args.map_path.resolve()),
        "mesh_file":      str(mesh_path.resolve()),
        "placement_json": str(placement_path.resolve()),
        "camera": {
            "source":             "placement_json",
            "decoding":           "view_matrix_R_T_decomposition",
            "placement_json_path": str(placement_path.resolve()),
            "position":           pos_arr.tolist(),
            "focal_point":        fp_arr.tolist(),
            "up":                 up_arr.tolist(),
            "vert_fov_deg":       round(vfov_val, 6),
        },
        "timing_contract": {
            "name":              args.timing_contract,
            "frame_offset":      start_idx,
            "start_frame_idx":   start_idx,
            "end_frame_idx":     end_idx,
            "n_frames":          len(png_paths),
            "fps":               fps,
            "dataset_turn_frames": TURN_FRAMES.get(args.dataset.lower()),
        },
        "render": {
            "n_rendered_frames":     len(png_paths),
            "fps":                   fps,
            "width":                 args.width,
            "height":                args.height,
            "alpha":                 args.alpha,
            "colormap":              args.colormap,
            "background_color":      args.background_color,
            "extra_rotate_x_deg":    extra_rot_x,
            "map_domain":            map_domain,
            "n_map_elements":        len(values),
            "n_mesh_vertices":       n_vertices,
            "n_mesh_faces":          n_faces,
            "map_provenance_note":   args.map_provenance_note,
            **norm_stats,
        },
        "gpu_preflight":  gpu_info,
        "output_files": {
            "video":    str(mp4_path),
            "manifest": str(out_subdir / "manifest.json"),
            "manifest_csv": str(out_subdir / "manifest.csv"),
            "preview_pngs": [
                str(out_subdir / f"preview_frame_{i:05d}.png")
                for i in preview_indices
            ],
        },
    }

    write_manifest(out_subdir / "manifest.json", manifest_data)
    write_manifest_csv(out_subdir / "manifest.csv", manifest_data)
    print(f"[INFO] manifest: {out_subdir / 'manifest.json'}", flush=True)
    print(f"[DONE] {mp4_path}", flush=True)


if __name__ == "__main__":
    main()
