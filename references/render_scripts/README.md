Reference Blender render scripts used to generate source videos and JSON camera/model metadata.

Files:
- `mamba_render_2.py`: MeshMamba render pipeline reference.
- `3dva_render_1.py`: 3DVA render pipeline reference.

Why these are stored here:
- They are the primary source for how OBJ models were imported into Blender.
- They define the bbox normalization logic that produced `model_static.scale` in JSON.
- They define camera placement, FOV, and the exported `view_matrix` / `projection_matrix`.

Key runtime facts extracted from both scripts:
- OBJ import uses `bpy.ops.wm.obj_import(..., forward_axis='X', up_axis='Z')`.
- Object origin is moved to bbox center via `origin_set(..., center='BOUNDS')`.
- Object scale is normalized to fit `BBOX_MAX_WIDTH=0.8`, `BBOX_MAX_DEPTH=0.8`, `BBOX_MAX_HEIGHT=0.7`.
- The resulting `model.scale`, `camera.location`, `camera FOV`, `view_matrix`, and `projection_matrix` are saved into JSON and should be treated as source-of-truth.

Implication for this repository:
- Preview and reprojection tools must reproduce the Blender OBJ import axis correction in addition to using JSON scale/camera data.
