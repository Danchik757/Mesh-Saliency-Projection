# test/manifests/

Per-model JSON files describing one alignment check point each.
Used by the Blender canonical check (`test/blender_canonical/`) and
the Python trimesh previewer (`test/tools/render_preview_from_manifest.py`).

## Manifest types

### Alignment check manifests (`preview_*.json`)

One file per model × dataset. Contain:

| Key | Purpose |
|-----|---------|
| `dataset` | `"MeshMamba_non_texture"`, `"MeshMamba_rgb_texture"`, `"3DVA"`, `"SAL3D"` |
| `model` | Model name (matches dataset folder) |
| `obj_path` | OBJ file via env-var placeholder |
| `json_path` | Camera + animation JSON |
| `video_path` | Source video for frame extraction |
| `frame_index` | Frame to compare against |
| `resolution_scale` | 0.5 = half-res (960×540) |
| `recenter_to_bbox_center` | Always `true` |
| `extra_rotate_x_deg` | Corrective X rotation (90° for MeshMamba/SAL3D, 0° for 3DVA-up) |
| `override_fov_deg` | Override FOV; `37.5` for MeshMamba, `null` for 3DVA/SAL3D (uses JSON) |

### Pipeline pilot manifests (`*_pilot.json`, `*_clear_pilot.json`)

Broader config files describing a full eval run for one dataset:
which scripts to use, which models to run first, parallelism settings, etc.

| File | Dataset | Notes |
|------|---------|-------|
| `3dva_pilot.json` | 3DVA (published eval) | Uses `eval_vs_gt_visual_attention.py` + original `3DModels-Simplif/` OBJ |
| `meshmamba_non_texture_pilot.json` | MeshMamba non_texture | — |
| `meshmamba_rgb_texture_pilot.json` | MeshMamba rgb_texture | — |
| `saliency3d_clear_pilot.json` | Saliency3D_clear (separate dataset) | Not the same as SAL3D |

## Validated alignment manifests

### MeshMamba — recipe: `rotX=90°`, `FOV=37.5°`

**non_texture** (8 models fully validated, remainder use same recipe):

| Model | IoU | Status |
|-------|-----|--------|
| Starfruit_L3 | 0.990–0.992 | ✅ |
| Mango_L3 | 0.991–0.992 | ✅ |
| Pear_L3 | 0.987–0.988 | ✅ |
| Rubber_Duck_v1_L3 | 0.989–0.991 | ✅ |
| Penguin_V2_L3 | 0.988 | ✅ |
| Moai_v3_L3 | 0.991 | ✅ |
| SeaHorse_v2_L3 | 0.976 | ✅ |
| Rhinoceros_v1_L3 | 0.987 | ✅ |

**rgb_texture**: same 8 models, IoU 0.988–0.998 ✅

### 3DVA — recipe: `rotX=0°`, `FOV=null` (60° from JSON), `-up` OBJ

All 32 models: mean IoU = 0.946, min = 0.875, 0/32 excluded.
See [test/README.md](../README.md#3dva-corrected--up-obj-rotx0-fov-null-from-json) for full table.

### SAL3D — recipe: `rotX=90°`, `FOV=null` (60° from JSON), `forward_axis=Z`, `up_axis=Y`

All 57 models: mean IoU = 0.977, min = 0.907, 0/57 excluded.

## Adding a new manifest

1. Copy an existing manifest for the same dataset.
2. Update `model`, `obj_path`, `json_path`, `video_path`, `output_prefix`.
3. Keep `extra_rotate_x_deg` and `override_fov_deg` from the dataset recipe above.
4. Run the Blender batch check to confirm IoU ≥ 0.90:
   ```bash
   python3 test/blender_canonical/evaluate_blender_mask_batch.py \
       --manifest test/manifests/your_new_manifest.json \
       --output-dir test/output_local/your_check \
       --blender-bin /Applications/Blender.app/Contents/MacOS/Blender
   ```
