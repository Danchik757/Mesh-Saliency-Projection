#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []
    parser = argparse.ArgumentParser(description="Render a canonical Blender preview from a manifest.")
    parser.add_argument("--manifest", required=True)
    return parser.parse_args(argv)


def expand_path(raw: str | None) -> Path | None:
    if raw is None:
        return None
    expanded = os.path.expandvars(os.path.expanduser(raw))
    if "$" in expanded:
        raise ValueError(f"Unresolved environment variable in path: {raw}")
    return Path(expanded)


def load_manifest(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def configure_render(scene, width: int, height: int, output_path: Path) -> None:
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = True
    scene.render.resolution_x = int(width)
    scene.render.resolution_y = int(height)
    scene.render.resolution_percentage = 100
    scene.render.filepath = str(output_path)
    scene.display.shading.light = "FLAT"
    scene.display.shading.color_type = "OBJECT"
    scene.display.shading.show_backface_culling = False


def reset_scene(bpy) -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_obj_with_blender_axes(bpy, obj_path: Path):
    bpy.ops.wm.obj_import(
        filepath=str(obj_path),
        forward_axis="X",
        up_axis="Z",
    )
    obj = bpy.context.selected_objects[0]
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    return obj


def set_camera_from_json(bpy, metadata: dict, manifest: dict):
    cam_data = bpy.data.cameras.new(name="Camera")
    cam_obj = bpy.data.objects.new("Camera", cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)
    bpy.context.scene.camera = cam_obj

    camera_static = metadata["camera_static"]
    cam_obj.location = tuple(float(v) for v in camera_static["location"])
    cam_obj.rotation_mode = "XYZ"
    cam_obj.rotation_euler = tuple(float(v) for v in camera_static["rotation_euler_radians"])

    override_fov_deg = manifest.get("override_fov_deg")
    if override_fov_deg is None:
        cam_data.angle = float(camera_static["fov_radians"])
    else:
        cam_data.angle = float(override_fov_deg) * 3.141592653589793 / 180.0
    if "lens_mm" in camera_static:
        cam_data.lens = float(camera_static["lens_mm"])
    if "sensor_width_mm" in camera_static:
        cam_data.sensor_width = float(camera_static["sensor_width_mm"])
    if "sensor_height_mm" in camera_static:
        cam_data.sensor_height = float(camera_static["sensor_height_mm"])
    cam_data.clip_start = float(camera_static["clip_start"])
    cam_data.clip_end = float(camera_static["clip_end"])
    return cam_obj


def apply_object_transform(bpy, obj, metadata: dict, manifest: dict, frame_idx: int) -> None:
    model_static = metadata["model_static"]
    frame = metadata["frames"][frame_idx]

    rig = bpy.data.objects.new("ModelRig", None)
    bpy.context.scene.collection.objects.link(rig)
    rig.location = tuple(float(v) for v in model_static["location"])
    rig.rotation_mode = "XYZ"

    frame_rotate_z_deg = float(frame["rotation_z_degrees"])
    rig.rotation_euler[0] = 0.0
    rig.rotation_euler[1] = 0.0
    rig.rotation_euler[2] = frame_rotate_z_deg * 3.141592653589793 / 180.0

    obj.parent = rig
    obj.location = (0.0, 0.0, 0.0)
    obj.scale = tuple(float(v) for v in model_static["scale"])
    obj.rotation_mode = "XYZ"

    base_rotate_z_deg = float(manifest.get("base_rotate_z_deg", 0.0))
    extra_rotate_x_deg = float(manifest.get("extra_rotate_x_deg", 0.0))
    extra_rotate_y_deg = float(manifest.get("extra_rotate_y_deg", 0.0))

    obj.rotation_euler[0] = extra_rotate_x_deg * 3.141592653589793 / 180.0
    obj.rotation_euler[1] = extra_rotate_y_deg * 3.141592653589793 / 180.0
    obj.rotation_euler[2] = base_rotate_z_deg * 3.141592653589793 / 180.0


def set_object_color(obj) -> None:
    if not obj.data.materials:
        import bpy

        mat = bpy.data.materials.new(name="PreviewMaterial")
        obj.data.materials.append(mat)
    else:
        mat = obj.data.materials[0]
    mat.diffuse_color = (0.18, 0.55, 0.86, 1.0)


def main() -> None:
    args = parse_args()

    manifest_path = Path(args.manifest).resolve()
    manifest = load_manifest(manifest_path)
    obj_path = expand_path(manifest["obj_path"])
    json_path = expand_path(manifest["json_path"])
    output_prefix = expand_path(manifest["output_prefix"])

    if obj_path is None or json_path is None or output_prefix is None:
        raise ValueError("Manifest must contain obj_path, json_path, and output_prefix")

    with open(json_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    frame_idx = int(manifest.get("frame_index", 0))
    frame_idx = max(0, min(frame_idx, int(metadata["video_info"]["total_frames"]) - 1))

    scale = max(0.05, float(manifest.get("resolution_scale", 1.0)))
    width = max(64, int(round(float(metadata["video_info"]["resolution_width"]) * scale)))
    height = max(64, int(round(float(metadata["video_info"]["resolution_height"]) * scale)))

    output_path = output_prefix.with_name(output_prefix.name + "_blender.png")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    import bpy

    reset_scene(bpy)
    scene = bpy.context.scene
    configure_render(scene, width=width, height=height, output_path=output_path)
    set_camera_from_json(bpy, metadata, manifest)
    obj = import_obj_with_blender_axes(bpy, obj_path)
    apply_object_transform(bpy, obj, metadata, manifest, frame_idx)
    set_object_color(obj)

    bpy.ops.render.render(write_still=True)

    report = {
        "manifest_path": str(manifest_path),
        "obj_path": str(obj_path),
        "json_path": str(json_path),
        "frame_index": int(frame_idx),
        "rendered_preview": str(output_path),
        "width": int(width),
        "height": int(height),
        "note": "Canonical Blender preview rendered from JSON + manifest overrides.",
    }
    report_path = output_prefix.with_name(output_prefix.name + "_blender.report.json")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
