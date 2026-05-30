# Blender Canonical Preview

This folder contains the canonical preview path for alignment checks.

Why this exists:
- The local Python preview renderer is useful for fast iteration, but it is not Blender.
- The original videos were generated in Blender with `bpy.ops.wm.obj_import(...)`,
  `origin_set(..., center='BOUNDS')`, dataset-specific camera placement, and Blender rasterization.
- If the goal is "render the object exactly as it was shown in the video", Blender is the correct backend.

What this script does:
- Imports the OBJ in Blender.
- Applies the same kind of object setup used by the original render scripts:
  - OBJ import through Blender
  - origin recentered to bounding-box geometry center
  - scale and location from JSON
  - frame rotation around Z from JSON
  - optional corrective rotations from the manifest (`base_rotate_z_deg`, `extra_rotate_x_deg`, `extra_rotate_y_deg`)
- Restores camera pose and intrinsics from JSON.
- Renders a PNG frame for direct comparison with the source video.

Important:
- This is intended to be the source of truth for preview validation before running metrics.
- If Blender preview still does not match the video, the remaining mismatch is not from our local rasterizer anymore.

Example:

```bash
/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
  --python "/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/blender_canonical/render_preview_from_manifest_blender.py" \
  -- \
  --manifest "/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/manifests/preview_3dva_bunny.json"
```

Then compare the rendered PNG against the original video frame with:

```bash
python3 "/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/tools/render_preview_from_manifest.py" \
  --manifest "/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/manifests/preview_3dva_bunny.json"
```

or with the overlay script in `test/overlay_alignment/`.
